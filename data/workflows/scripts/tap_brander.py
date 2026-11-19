#!/usr/bin/env python3
"""Brander, started from the device itself.

Trigger: JAWA Tap Action (a web clip on the device). Generates a
wallpaper carrying the device's identifying details and a QR code of
its Jamf Pro id, then sets it on that device with the Wallpaper MDM
command. The payload names ONE device by id and UDID; the UDID must
match Jamf Pro's record before anything is sent (ADR-0012).

Originally written for webhook events by ball42 (2021), with
updates by David Raabe and Tim Knox.

With a template configured, the wallpaper is rendered by wallrender
(EWOK's renderer, vendored and hash-pinned in data/workflows/lib) from
an allowlist of the verified record's fields. With none, or "legacy",
the original layout is drawn exactly as before.

Exit codes: 0 set; 12 bad payload; 20 UDID mismatch; 21 device not
found; 22 Jamf refused the device lookup; 24 wallpaper command refused;
25 device not supervised; 26 device is not iOS or iPadOS; 30 template
missing or invalid;
31 renderer missing, edited or on an unsupported Pillow; 32 template
failed to render; 33 render timed out; 34 wallpaper over the size
budget; 42 Brander EA is Off.
"""

import base64
import hashlib
import io
import json
import os
import re
import signal
import sys
import time
from urllib.parse import urlparse

import qrcode
import requests
from PIL import Image, ImageDraw, ImageFont

# --- JAWA canonical Jamf API block (keep identical across templates) ---

token_cache = {"access_token": None, "expires_in": 0, "timestamp": 0}


class Config:
    def __init__(self):
        self.server_url = "__JAWA_SERVER_URL__"
        self.token_url = f"{self.server_url}/api/oauth/token"
        self.client_id = "__JAWA_CLIENT_ID__"
        self.client_secret = "__JAWA_CLIENT_SECRET__"
        self.scope = ""


def get_oauth_token():
    """Fetch (and cache) an OAuth access token from Jamf Pro."""
    global token_cache
    config = Config()
    current_time = time.time()
    if (
        token_cache["access_token"]
        and (current_time - token_cache["timestamp"])
        < token_cache["expires_in"]
    ):
        return token_cache["access_token"]
    data = {
        "client_id": config.client_id,
        "grant_type": "client_credentials",
        "client_secret": config.client_secret,
    }
    if config.scope:
        data["scope"] = config.scope
    response = requests.post(
        config.token_url,
        headers={"Content-Type": "application/x-www-form-urlencoded"},
        data=data,
        timeout=30,
    )
    response.raise_for_status()
    response_data = response.json()
    token_cache = {
        "access_token": response_data["access_token"],
        "expires_in": response_data["expires_in"],
        "timestamp": current_time,
    }
    return token_cache["access_token"]


def perform_api_call(endpoint, method="GET", data=None, api="classic"):
    """Call the Jamf Pro API and return the parsed response.

    endpoint: path with no leading slash, e.g. "mobiledevices/id/42".
    api: "classic" for /JSSResource, "pro" for /api.
    Returns parsed JSON, or the raw response when the body is not JSON.
    """
    config = Config()
    token = get_oauth_token()
    prefix = "JSSResource" if api == "classic" else "api"
    url = f"{config.server_url}/{prefix}/{endpoint}"
    headers = {
        "Authorization": f"Bearer {token}",
        "Accept": "application/json",
        "Content-Type": "application/json",
    }
    response = requests.request(
        method, url, headers=headers, json=data, timeout=30
    )
    response.raise_for_status()
    try:
        return response.json()
    except ValueError:
        return response

# --- end canonical block ---


# Template settings (filled in when the template is enabled).
EA_ID = __JAWA_EA_ID__  # noqa: F821 -- Jamf Setup role EA id; 0 = unused
WALLPAPER_SETTING = __JAWA_WALLPAPER_SETTING__  # noqa: F821 -- 1/2/3
ASSETS_DIR = "__JAWA_ASSETS_DIR__"
FONT_PATH = "__JAWA_FONT_PATH__"  # "none" or blank = Pillow's built-in font
TEMPLATE_PATH = "__JAWA_TEMPLATE_PATH__"  # "legacy" = the original layout
MAX_KB = __JAWA_MAX_KB__  # noqa: F821 -- largest image sent, in KB
ALLOW_PERSON_FIELDS = "__JAWA_ALLOW_PERSON_FIELDS__"  # "yes" to allow user.*

RENDER_TIMEOUT = 20  # seconds; templates are untrusted input
MAX_TEMPLATE_BYTES = 256 * 1024


def load_font(size):
    text = FONT_PATH.strip()
    if text and text.lower() != "none":
        return ImageFont.truetype(text, size)
    return ImageFont.load_default(size=size)


def jamf_error(response):
    """A Jamf error for the log: the status and at most 200 characters of
    the body on one line, never a whole HTML page or echoed request."""
    if response is None:
        return "no response"
    body = " ".join(str(getattr(response, "text", "") or "").split())
    return f"HTTP {response.status_code}" + (f": {body[:200]}" if body else "")


def fetch_verified_device(jss_id, udid):
    """Classic mobile device record, only if the UDID matches."""
    try:
        record = perform_api_call(f"mobiledevices/id/{jss_id}")
    except requests.HTTPError as err:
        if err.response is not None and err.response.status_code == 404:
            print(f"Device {jss_id} not found in Jamf Pro.")
            sys.exit(21)
        print(f"Jamf Pro refused the device lookup: {jamf_error(err.response)}")
        sys.exit(22)
    except requests.RequestException as err:
        print(f"Could not reach Jamf Pro for the device lookup: {type(err).__name__}.")
        sys.exit(22)
    if not isinstance(record, dict):
        print("Jamf Pro's device lookup did not return JSON.")
        sys.exit(22)
    device = record.get("mobile_device", {})
    actual = str(device.get("general", {}).get("udid", "")).strip().lower()
    if not actual or actual != str(udid).strip().lower():
        print(f"UDID mismatch for device {jss_id}; refusing to brand.")
        sys.exit(20)
    return device


WALLPAPER_PLATFORMS = ("iOS", "iPadOS")


def preflight(device, jss_id):
    """Only supervised iOS and iPadOS devices accept the Wallpaper command;
    stop before rendering anything for any other device."""
    general = device.get("general", {})
    if general.get("supervised") is not True:
        print(f"Device {jss_id} is not supervised; the Wallpaper command needs supervision.")
        sys.exit(25)
    if general.get("os_type") not in WALLPAPER_PLATFORMS:
        print(f"Device {jss_id} runs {general.get('os_type') or 'an unknown OS'}; "
              "wallpapers apply to iOS and iPadOS only.")
        sys.exit(26)


def find_role(device):
    """The wallpaper role: Jamf Setup EA value, or "Brander" EA switch.

    Returns (template_basename, role_label). A "Brander" EA set to Off
    exits 42, matching the original webhook Brander.
    """
    eas = device.get("extension_attributes", [])
    role = ""
    for ea in eas:
        if ea.get("name") == "Brander":
            value = (ea.get("value") or "").strip()
            if not value or value.lower() == "off":
                print("Brander EA is Off for this device; exiting.")
                sys.exit(42)
        if EA_ID and str(ea.get("id")) == str(EA_ID):
            role = (ea.get("value") or "").strip()
    if not role:
        return "null", ""
    basename = role.replace(" ", "").lower()
    if _safe_role_image(basename):
        return basename, role
    return "lockscreen-template", role


ROLE_NAME = re.compile(r"^[a-z0-9_-]{1,64}$")


def _safe_role_image(basename):
    """True if <basename>.png is a real file inside ASSETS_DIR.

    The role is an extension attribute the device side can set, so it is
    untrusted: only plain names are allowed, and the resolved path (after
    symlinks) must stay inside the assets directory.
    """
    if not ROLE_NAME.fullmatch(basename):
        return False
    assets = os.path.realpath(ASSETS_DIR)
    candidate = os.path.realpath(os.path.join(assets, f"{basename}.png"))
    return candidate.startswith(assets + os.sep) and os.path.isfile(candidate)


def _centered(draw, font, text, img_w, y, color):
    left, top, right, bottom = draw.textbbox((0, 0), text, font=font)
    draw.text(((img_w - (right - left)) / 2, y), text, color, font=font)


def compose_legacy(assets_dir, basename, role, device):
    """Draw the original Brander layout and return the image."""
    general = device.get("general", {})
    location = device.get("location", {})
    role_line = role.title() if role else "Please open the Setup app"
    if role.lower() in ("hold", "transfer"):
        role_line = "Awaiting location assignment"
    if role.lower() == "pending":
        role_line = "Please open the Reset app"

    lines = [
        str(general.get("device_name", "")),
        str(general.get("serial_number", "")),
        str(location.get("building", "")),
        str(location.get("department", "")),
        f"{general.get('model', '')} {general.get('os_type', '')} "
        f"{general.get('os_version', '')}".strip(),
        role_line,
    ]
    img = Image.open(
        os.path.join(assets_dir, f"{basename}.png"), formats=["PNG"]
    ).convert(
        "RGB"
    )
    img_w, img_h = img.size
    draw = ImageDraw.Draw(img)
    font = load_font(max(12, img_h // 40))
    for index, line in enumerate(lines):
        _centered(draw, font, line, img_w, img_h * (0.60 + 0.05 * index),
                  (0, 0, 0))

    qr = qrcode.QRCode(
        version=1,
        error_correction=qrcode.constants.ERROR_CORRECT_L,
        box_size=4,
        border=1,
    )
    qr.add_data(str(general.get("id", "")))
    qr.make(fit=True)
    # qrcode's PilImage wrapper is not a PIL.Image.Image subclass, so
    # Image.paste cannot infer its size from a 2-tuple box; unwrap it.
    qr_img = qr.make_image(fill_color="black", back_color="white").get_image()
    img.paste(
        qr_img,
        ((img_w - qr_img.size[0]) // 2, (img_h - qr_img.size[1]) // 2),
    )
    return img


# --- wallrender templates ---


class RenderTimeout(BaseException):
    """BaseException, so no broad except inside the renderer eats it."""


def run_with_timeout(func, seconds):
    """Call func(); raise RenderTimeout if it runs past `seconds`."""
    if not hasattr(signal, "setitimer"):
        return func()

    def _expired(signum, frame):
        raise RenderTimeout()

    previous = signal.signal(signal.SIGALRM, _expired)
    try:
        signal.setitimer(signal.ITIMER_REAL, seconds)
        result = func()
        # Disarm before leaving the try, so an alarm landing just as
        # func() returns cannot discard a finished render.
        signal.setitimer(signal.ITIMER_REAL, 0)
        return result
    finally:
        signal.setitimer(signal.ITIMER_REAL, 0)
        signal.signal(signal.SIGALRM, previous)


def _lib_dirs():
    """Where the vendored renderer lives, relative to this script: the
    template copy in data/workflows/scripts, or a deployed copy in
    <JAWA>/scripts."""
    here = os.path.dirname(os.path.abspath(__file__))
    parent = os.path.dirname(here)
    return [
        os.path.join(parent, "lib"),
        os.path.join(parent, "data", "workflows", "lib"),
    ]


def _version_tuple(text):
    return tuple(int(p) for p in re.findall(r"\d+", text)[:2])


def load_renderer():
    """Import the vendored wallrender after checking it is the pinned,
    unedited copy and that this Pillow is one it is pinned against."""
    import PIL

    for lib in _lib_dirs():
        lock_path = os.path.join(lib, "wallrender.lock.json")
        if os.path.isfile(lock_path):
            break
    else:
        print("wallrender is not installed next to this script.")
        sys.exit(31)
    with open(lock_path, encoding="utf-8") as handle:
        lock = json.load(handle)
    for rel, expected in lock["files"].items():
        with open(os.path.join(lib, "wallrender", rel), "rb") as handle:
            if hashlib.sha256(handle.read()).hexdigest() != expected:
                print(f"wallrender/{rel} differs from the pinned copy.")
                sys.exit(31)
    pillow = _version_tuple(PIL.__version__)
    low, high = tuple(lock["pillow_min"]), tuple(lock["pillow_below"])
    if not low <= pillow < high:
        print(f"Pillow {PIL.__version__} is not supported by wallrender.")
        sys.exit(31)
    lib = os.path.realpath(lib)
    if lib not in sys.path:
        sys.path.insert(0, lib)
    import wallrender

    return wallrender


def load_template(path, base=None):
    """JSON from path: absolute, or relative to base (the assets dir)."""
    if not os.path.isabs(path):
        path = os.path.join(base or ASSETS_DIR, path)
    try:
        with open(path, "rb") as handle:
            raw = handle.read(MAX_TEMPLATE_BYTES + 1)
    except OSError as err:
        print(f"Template {path} could not be read: {err.strerror}.")
        sys.exit(30)
    if len(raw) > MAX_TEMPLATE_BYTES:
        print(f"Template {path} is over {MAX_TEMPLATE_BYTES} bytes.")
        sys.exit(30)
    try:
        template = json.loads(raw)
    except ValueError as err:
        print(f"Template {path} is not valid JSON: {err}.")
        sys.exit(30)
    return template, hashlib.sha256(raw).hexdigest()


def device_family(model_identifier):
    """'iPad8,5' -> 'ipad', 'iPhone15,3' -> 'iphone'."""
    match = re.match(r"[A-Za-z]+", model_identifier or "")
    return match.group(0).lower() if match else ""


def _is_template_set(data):
    return isinstance(data, dict) and "templates" in data and (
        "schema_version" not in data
    )


def resolve_template(path, device):
    """The template for this device, and the file it came from.

    path names a template, or a template set: {"templates": {key: file}}
    where key is an exact model identifier ("iPad8,5"), a family
    ("ipad", "iphone") or "default", tried in that order against the
    verified record. Set entries are relative to the set file.
    """
    data, digest = load_template(path)
    if not _is_template_set(data):
        return data, os.path.basename(path), digest
    templates = data["templates"]
    if not isinstance(templates, dict) or not all(
        isinstance(v, str) for v in templates.values()
    ):
        print("Template set must map names to template files.")
        sys.exit(30)
    model = str(device.get("general", {}).get("model_identifier") or "")
    for key in (model, device_family(model), "default"):
        if key and key in templates:
            chosen = templates[key]
            break
    else:
        print(f"Template set has no entry for {model or 'this device'} "
              "and no default.")
        sys.exit(30)
    full = path if os.path.isabs(path) else os.path.join(ASSETS_DIR, path)
    template, digest = load_template(chosen, base=os.path.dirname(full))
    if _is_template_set(template):
        print(f"Template set entry {chosen} is itself a set.")
        sys.exit(30)
    return template, os.path.basename(chosen), digest


def person_fields_allowed():
    return ALLOW_PERSON_FIELDS.strip().lower() == "yes"


def build_values(device, template=None):
    """The only device data a template can print: fields of the
    UDID-verified record, never anything from the request. A template
    with role variants also gets `role`: the value of the one extension
    attribute it names, and no other attribute. Personal fields (user.*)
    need both the template's person_fields flag and the admin's
    "Allow personal fields" setting (ADR-0013)."""
    general = device.get("general", {})
    location = device.get("location", {})
    values = {
        "device_name": general.get("device_name", ""),
        "serial_number": general.get("serial_number", ""),
        "asset_tag": general.get("asset_tag", ""),
        "jss_id": general.get("id", ""),
        "location": {"building": location.get("building", "")},
    }
    if (template or {}).get("person_fields") is True:
        if person_fields_allowed():
            values["user"] = {
                "real_name": location.get("real_name", ""),
                "username": location.get("username", ""),
                "email": location.get("email_address", ""),
            }
        else:
            print("Template asks for personal fields; personal fields withheld "
                  "(Allow personal fields is not yes for this Brander).")
    attribute = ((template or {}).get("roles") or {}).get("attribute")
    if attribute:
        for ea in device.get("extension_attributes", []):
            if ea.get("name") == attribute:
                values["role"] = str(ea.get("value") or "").strip()
                break
    return values


def read_asset(asset_id, folders=None):
    """PNG or JPEG bytes for a template asset id: from the template's own
    folder, then ASSETS_DIR, and never from anywhere else."""
    if ROLE_NAME.fullmatch(asset_id):
        for folder in folders or [ASSETS_DIR]:
            assets = os.path.realpath(folder)
            for ext in ("png", "jpg", "jpeg"):
                path = os.path.realpath(
                    os.path.join(assets, f"{asset_id}.{ext}")
                )
                if path.startswith(assets + os.sep) and os.path.isfile(path):
                    with open(path, "rb") as handle:
                        return handle.read()
    raise KeyError(asset_id)


def render_template(renderer, template, values, folders=None):
    return renderer.render(
        template, values, lambda asset_id: read_asset(asset_id, folders)
    )


# --- the template store (M3-3): template setting "store:<slug>", or a
# store set "store:iphone=<slug> ipad=<slug>" (M5) ---

STORE_DIR = None  # derived from this script's location unless set


def tenant_key(server_url):
    """Same rule as bin/brander_store.py: the tenant's host (and port)."""
    parsed = urlparse(server_url or "")
    host = (parsed.hostname or "").lower()
    port = parsed.port
    if port and port != {"https": 443, "http": 80}.get(parsed.scheme.lower()):
        host = f"{host}-{port}"
    host = re.sub(r"[^a-z0-9.-]", "-", host).strip(".-")
    return host or "default"


def _store_root():
    if STORE_DIR:
        return STORE_DIR
    parent = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    for root in (
        os.path.join(os.path.dirname(parent), "brander_templates"),  # template copy
        os.path.join(parent, "data", "brander_templates"),  # deployed copy
    ):
        if os.path.isdir(root):
            return root
    return os.path.join(parent, "data", "brander_templates")


def store_pick(spec, device):
    """The stored template for this device. spec is one name, or a store
    set of space-separated key=name pairs ("iphone=front-desk ipad=wards")
    keyed like template sets: model identifier, family, then default.
    Same rule as bin/brander_store.py."""
    spec = spec.strip()
    if "=" not in spec:
        return spec
    entries = {}
    for part in spec.split():
        key, sep, name = part.partition("=")
        if not sep or not key or not name or key in entries:
            print(f"The template setting's store set is malformed at {part!r}.")
            sys.exit(30)
        entries[key] = name
    model = str(device.get("general", {}).get("model_identifier") or "")
    for key in (model, device_family(model), "default"):
        if key and key in entries:
            return entries[key]
    print(f"The store set has no template for {model or 'this device'} and no default.")
    sys.exit(30)


def store_template(slug):
    """(path of the active version's template.json, 'store:<slug> vN')."""
    slug = re.sub(r"[^a-z0-9]+", "-", slug.lower()).strip("-")
    slug_dir = os.path.join(_store_root(), tenant_key(Config().server_url), slug)
    try:
        with open(os.path.join(slug_dir, "index.json"), encoding="utf-8") as handle:
            active = json.load(handle).get("active")
    except (OSError, ValueError):
        active = None
    path = os.path.join(slug_dir, f"v{active}", "template.json")
    if not slug or not active or not os.path.isfile(path):
        print(f"There is no active stored template {slug or '(blank)'} for this tenant.")
        sys.exit(30)
    return path, f"store:{slug} v{active}"


def template_wallpaper(path, device, max_bytes):
    """Render the device's template and encode it, inside RENDER_TIMEOUT.

    Returns (image bytes, name of the template file used).

    The timeout is checked between Python bytecodes, so a single Pillow
    call finishes before it fires; wallrender's canvas caps bound how
    long any one call can take."""
    renderer = load_renderer()
    label = None
    if path.startswith("store:"):
        path, label = store_template(store_pick(path[len("store:"):], device))
    template, source, digest = resolve_template(path, device)
    source = label or source
    full = path if os.path.isabs(path) else os.path.join(ASSETS_DIR, path)
    folders = [os.path.dirname(full), ASSETS_DIR]
    try:
        problems = renderer.validate(template)
    except Exception as err:  # noqa: BLE001 -- a crafted template must not crash the script
        problems = [f"validation failed: {type(err).__name__}"]
    if problems:
        print("Template is invalid: " + "; ".join(problems[:5]))
        sys.exit(30)
    try:
        image = run_with_timeout(
            lambda: encode_within_budget(
                render_template(renderer, template, build_values(device, template), folders),
                max_bytes,
            ),
            RENDER_TIMEOUT,
        )
        setting = TEMPLATE_SCREENS.get(template.get("screen"), WALLPAPER_SETTING)
        return image, f"{source}, sha256 {digest[:12]}", setting
    except renderer.TemplateError as err:
        print(f"Template failed to render: {err}")
        sys.exit(32)
    except RenderTimeout:
        print(f"Template took over {RENDER_TIMEOUT}s to render.")
        sys.exit(33)


def encode_within_budget(img, max_bytes):
    """PNG if it fits, else the best JPEG that does; exit 34 if none."""
    img = img.convert("RGB")
    attempts = [("PNG", {"optimize": True})] + [
        ("JPEG", {"quality": q}) for q in (90, 80, 70, 60)
    ]
    for fmt, options in attempts:
        buffer = io.BytesIO()
        img.save(buffer, fmt, **options)
        if buffer.tell() <= max_bytes:
            return buffer.getvalue()
    print(f"Wallpaper is over the {max_bytes // 1024} KB budget.")
    sys.exit(34)


# A template's own "screen" choice wins over the WALLPAPER_SETTING setting.
TEMPLATE_SCREENS = {"lock": 1, "home": 2, "both": 3}


def set_wallpaper(image_bytes, jss_id, setting=None):
    b64 = base64.b64encode(image_bytes).decode("ascii")
    body = (
        "<mobile_device_command><command>Wallpaper</command>"
        f"<wallpaper_setting>{setting or WALLPAPER_SETTING}</wallpaper_setting>"
        f"<wallpaper_content>{b64}</wallpaper_content>"
        f"<mobile_devices><mobile_device><id>{jss_id}</id></mobile_device>"
        "</mobile_devices></mobile_device_command>"
    )
    config = Config()
    try:
        resp = requests.post(
            f"{config.server_url}/JSSResource/mobiledevicecommands/command/"
            "Wallpaper",
            headers={
                "Authorization": f"Bearer {get_oauth_token()}",
                "Content-Type": "application/xml",
            },
            data=body,
            timeout=60,
        )
    except requests.RequestException as err:
        print(f"Could not send the Wallpaper command: {type(err).__name__}.")
        sys.exit(24)
    if resp.status_code >= 400:
        print(f"Wallpaper command refused: {jamf_error(resp)}")
        sys.exit(24)


def main():
    event_data = json.loads(sys.argv[1])
    event = event_data.get("event") or {}
    jss_id = event.get("jssID")
    udid = event.get("udid")
    if not isinstance(jss_id, int) or not udid:
        print("Payload did not name a device id and UDID.")
        sys.exit(12)

    device = fetch_verified_device(jss_id, udid)
    basename, role = find_role(device)
    preflight(device, jss_id)
    template = TEMPLATE_PATH.strip()
    if template and template.lower() != "legacy":
        image, source, setting = template_wallpaper(template, device, MAX_KB * 1024)
    else:
        setting = WALLPAPER_SETTING
        img = compose_legacy(ASSETS_DIR, basename, role, device)
        image = encode_within_budget(img, MAX_KB * 1024)
        source = f"legacy layout, {basename}.png"
    set_wallpaper(image, jss_id, setting)
    print(f"Device {jss_id}: wallpaper set ({source}).")


if __name__ == "__main__":
    main()
