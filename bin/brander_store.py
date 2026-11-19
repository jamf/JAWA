"""Brander template store: validated, versioned, audited (M3-3).

A Brander template package is one JSON file, the same idea as a
.jawa.json workflow package: no archive, so nothing to unpack outside
the store.

    {"kind": "brander-template", "format": 1, "name": "Ward iPads",
     "template": {...wallrender template...},
     "assets": {"<asset id>": "<base64 PNG or JPEG>", ...}}

Packages are checked with the vendored wallrender (the copy Brander
renders with), then stored per Jamf Pro tenant as immutable numbered
versions:

    data/brander_templates/<tenant>/<slug>/index.json
    data/brander_templates/<tenant>/<slug>/v<N>/template.json, <id>.png|jpg

index.json records who uploaded each version and who activated which
version, and when. Brander renders the active version when its template
setting is store:<slug>, so activating a version takes effect on the next
tap without re-enabling anything.
"""

import base64
import binascii
import hashlib
import io
import json
import os
import re
import shutil
import sys
import tempfile
import threading
import time
from typing import Any, Dict, List, Optional, Tuple
from urllib.parse import urlparse

from PIL import Image, UnidentifiedImageError

_base_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
STORE_DIR = os.path.join(_base_dir, "data", "brander_templates")
LIB_DIR = os.path.join(_base_dir, "data", "workflows", "lib")

MAX_PACKAGE_BYTES = 20 * 1024 * 1024
MAX_ASSETS = 30
FORMATS = {"PNG": "png", "JPEG": "jpg"}

_lock = threading.Lock()


class StoreError(Exception):
    def __init__(self, problems: List[str]):
        super().__init__("; ".join(problems))
        self.problems = problems


def _wallrender():
    if LIB_DIR not in sys.path:
        sys.path.insert(0, LIB_DIR)
    import wallrender

    return wallrender


def tenant_key(server_url: str) -> str:
    """A folder name for a Jamf Pro tenant: its host (and port)."""
    parsed = urlparse(server_url or "")
    host = (parsed.hostname or "").lower()
    port = parsed.port
    if port and port != {"https": 443, "http": 80}.get(parsed.scheme.lower()):
        host = f"{host}-{port}"
    host = re.sub(r"[^a-z0-9.-]", "-", host).strip(".-")
    return host or "default"


def slugify(name: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", str(name).lower()).strip("-")[:63]


def _decode_asset(
    asset_id: str, data: Any, wallrender
) -> Tuple[Optional[Tuple[str, bytes]], Optional[str]]:
    if not wallrender.schema.ASSET_ID.fullmatch(str(asset_id)):
        return (
            None,
            f"asset id {asset_id!r} must match {wallrender.schema.ASSET_ID.pattern}",
        )
    try:
        raw = base64.b64decode(data, validate=True)
    except (binascii.Error, TypeError, ValueError):
        return None, f"asset {asset_id!r} is not valid base64"
    try:
        with Image.open(io.BytesIO(raw), formats=sorted(FORMATS)) as img:
            fmt, width, height = img.format, img.width, img.height
            img.verify()
    except UnidentifiedImageError:
        return None, f"asset {asset_id!r} is not a readable image; it must be PNG or JPEG"
    except (OSError, Image.DecompressionBombError):
        return None, f"asset {asset_id!r} is not a readable image"
    if fmt not in FORMATS:
        return None, f"asset {asset_id!r} must be PNG or JPEG"
    if (
        max(width, height) > wallrender.schema.MAX_SIDE
        or width * height > wallrender.schema.MAX_PIXELS
    ):
        return (
            None,
            f"asset {asset_id!r} is larger than {wallrender.schema.MAX_SIDE}px per side",
        )
    return (FORMATS[fmt], raw), None


def _used_assets(template: Dict[str, Any]) -> List[str]:
    ids = []
    background = template.get("background") or {}
    if background.get("asset"):
        ids.append(background["asset"])
    ids += [
        layer["asset"]
        for layer in template.get("layers", [])
        if layer.get("type") == "image"
    ]
    roles = template.get("roles") or {}
    for variant in list((roles.get("variants") or {}).values()) + [
        roles.get(k) or {} for k in ("empty", "default")
    ]:
        asset = (variant.get("background") or {}).get("asset")
        if asset:
            ids.append(asset)
    return list(dict.fromkeys(ids))


def validate_package(raw: bytes) -> Tuple[Optional[Dict[str, Any]], List[str]]:
    """(package with decoded assets, []) or (None, problems)."""
    if len(raw) > MAX_PACKAGE_BYTES:
        return None, [
            f"the package is too large (limit {MAX_PACKAGE_BYTES // (1024 * 1024)} MB)"
        ]
    try:
        package = json.loads(raw)
    except (ValueError, UnicodeDecodeError):
        return None, ["the package is not valid JSON"]
    if not isinstance(package, dict):
        return None, ["the package must be a JSON object"]
    if package.get("kind") != "brander-template" or package.get("format") != 1:
        return None, [
            'the package must have "kind": "brander-template" and "format": 1'
        ]
    problems = []
    name = package.get("name")
    if not isinstance(name, str) or not slugify(name):
        problems.append("the package needs a name with letters or digits")
    wallrender = _wallrender()
    template = package.get("template")
    try:
        problems += wallrender.validate(template)
    except Exception as err:  # noqa: BLE001 -- crafted input must not crash the upload
        problems.append(
            f"the template could not be validated ({type(err).__name__})"
        )
    assets = package.get("assets")
    if not isinstance(assets, dict):
        return None, problems + [
            "assets must be an object of id: base64 image"
        ]
    if len(assets) > MAX_ASSETS:
        problems.append(f"a package may hold at most {MAX_ASSETS} assets")
    decoded = {}
    for asset_id, data in assets.items():
        result, error = _decode_asset(asset_id, data, wallrender)
        if error:
            problems.append(error)
        else:
            decoded[asset_id] = result
    if not problems:
        missing = [a for a in _used_assets(template) if a not in decoded]
        problems += [
            f"the template uses asset {a!r}, which the package does not include"
            for a in missing
        ]
    if problems:
        return None, problems
    return {
        "name": name,
        "slug": slugify(name),
        "template": template,
        "assets": decoded,
    }, []


def _slug_dir(tenant_url: str, slug: str) -> str:
    return os.path.join(STORE_DIR, tenant_key(tenant_url), slug)


def _version_dirs(slug_dir: str) -> List[int]:
    found = []
    for name in os.listdir(slug_dir) if os.path.isdir(slug_dir) else []:
        if (
            name.startswith("v")
            and name[1:].isdigit()
            and os.path.isdir(os.path.join(slug_dir, name))
        ):
            found.append(int(name[1:]))
    return sorted(found)


def _read_index(slug_dir: str) -> Optional[Dict[str, Any]]:
    """The slug's index; if it is missing or corrupt but versions exist on
    disk, an index rebuilt from them (the audit history is lost, and the
    newest version is marked active)."""
    try:
        with open(
            os.path.join(slug_dir, "index.json"), encoding="utf-8"
        ) as handle:
            index = json.load(handle)
        if isinstance(index, dict) and isinstance(index.get("versions"), list):
            return index
    except (OSError, ValueError):
        pass
    versions = _version_dirs(slug_dir)
    if not versions:
        return None
    slug = os.path.basename(slug_dir)
    return {
        "slug": slug,
        "name": slug,
        "active": versions[-1],
        "rebuilt": True,
        "versions": [
            {
                "version": v,
                "sha256": "",
                "uploaded_by": "unknown (index rebuilt)",
                "uploaded_at": 0,
            }
            for v in versions
        ],
        "activations": [],
    }


def _write_index(slug_dir: str, index: Dict[str, Any]) -> None:
    fd, tmp = tempfile.mkstemp(dir=slug_dir, prefix=".index-")
    with os.fdopen(fd, "w", encoding="utf-8") as handle:
        json.dump(index, handle, indent=2)
    os.replace(tmp, os.path.join(slug_dir, "index.json"))


def save_version(
    tenant_url: str, raw: bytes, user: str, now: Optional[float] = None
) -> Dict[str, Any]:
    """Store a package as the next version. The first version is activated
    straight away; later ones wait for activate()."""
    package, problems = validate_package(raw)
    if problems:
        raise StoreError(problems)
    now = time.time() if now is None else now
    slug = package["slug"]
    slug_dir = _slug_dir(tenant_url, slug)
    with _lock:
        os.makedirs(slug_dir, exist_ok=True)
        index = _read_index(slug_dir) or {
            "slug": slug,
            "name": package["name"],
            "active": None,
            "versions": [],
            "activations": [],
        }
        # Never reuse a number: the index and the folders on disk must agree.
        version = (
            max(
                [v["version"] for v in index["versions"]]
                + _version_dirs(slug_dir)
                + [0]
            )
            + 1
        )
        # Build the version in a temp folder, then rename it into place,
        # so a version folder is never half-written.
        staging = tempfile.mkdtemp(dir=slug_dir, prefix=".staging-")
        try:
            template_bytes = (
                json.dumps(package["template"], indent=2) + "\n"
            ).encode()
            with open(os.path.join(staging, "template.json"), "wb") as handle:
                handle.write(template_bytes)
            for asset_id, (ext, data) in package["assets"].items():
                with open(
                    os.path.join(staging, f"{asset_id}.{ext}"), "wb"
                ) as handle:
                    handle.write(data)
            os.replace(staging, os.path.join(slug_dir, f"v{version}"))
        except BaseException:
            shutil.rmtree(staging, ignore_errors=True)
            raise
        digest = hashlib.sha256(template_bytes).hexdigest()
        index["name"] = package["name"]
        index["versions"].append(
            {
                "version": version,
                "sha256": digest,
                "uploaded_by": user,
                "uploaded_at": now,
            }
        )
        if index["active"] is None:
            index["active"] = version
            index["activations"].append(
                {"version": version, "by": user, "at": now}
            )
        _write_index(slug_dir, index)
    return {
        "slug": slug,
        "version": version,
        "active": index["active"] == version,
        "sha256": digest,
    }


def activate(
    tenant_url: str,
    slug: str,
    version: int,
    user: str,
    now: Optional[float] = None,
) -> None:
    slug_dir = _slug_dir(tenant_url, slugify(slug))
    with _lock:
        index = _read_index(slug_dir)
        if not index:
            raise StoreError([f"there is no stored template {slug!r}"])
        if not any(v["version"] == version for v in index["versions"]):
            raise StoreError([f"{slug!r} has no version {version}"])
        index["active"] = version
        index["activations"].append(
            {
                "version": version,
                "by": user,
                "at": time.time() if now is None else now,
            }
        )
        _write_index(slug_dir, index)


def list_templates(tenant_url: str) -> List[Dict[str, Any]]:
    root = os.path.join(STORE_DIR, tenant_key(tenant_url))
    if not os.path.isdir(root):
        return []
    found = []
    for slug in sorted(os.listdir(root)):
        index = _read_index(os.path.join(root, slug))
        if index:
            found.append(index)
    return found


def active_template_path(tenant_url: str, slug: str) -> Optional[str]:
    slug_dir = _slug_dir(tenant_url, slugify(slug))
    index = _read_index(slug_dir)
    if not index or not index.get("active"):
        return None
    path = os.path.join(slug_dir, f"v{index['active']}", "template.json")
    return path if os.path.isfile(path) else None


# --- Store sets: one Brander, a stored template per kind of device ---------
#
# A Brander's template setting is store:<name> for one stored template, or
# a store set of space-separated key=name pairs:
#
#     store:iphone=front-desk ipad=ward-ipads iPad8,5=ipad-pro-12 default=front-desk
#
# Keys follow template set files: an exact model identifier, a family
# ("iphone", "ipad"), or "default", tried in that order. The rule is
# repeated in the Brander script (data/workflows/scripts/tap_brander.py),
# and tests/test_brander_store_sets.py keeps the two in step.

MAX_SET_ENTRIES = 20


def store_set(spec: str) -> Optional[Dict[str, str]]:
    """key -> slug for a store set; None when spec names one template.
    spec is the text after "store:". Raises StoreError on a malformed set."""
    spec = str(spec).strip()
    if "=" not in spec:
        return None
    entries: Dict[str, str] = {}
    problems = []
    for part in spec.split():
        key, sep, name = part.partition("=")
        if not sep or not key or not slugify(name):
            problems.append(f"{part!r} is not key=name")
        elif key in entries:
            problems.append(f"{key} is listed twice")
        else:
            entries[key] = slugify(name)
    if len(entries) > MAX_SET_ENTRIES:
        problems.append(
            f"a store set may have at most {MAX_SET_ENTRIES} entries"
        )
    if problems:
        raise StoreError(problems)
    return entries


def store_slugs(setting: str) -> List[str]:
    """Every stored template a Brander template setting names, or []."""
    setting = str(setting or "").strip()
    if not setting.startswith("store:"):
        return []
    spec = setting[len("store:") :]
    try:
        entries = store_set(spec)
    except StoreError:
        return []
    if entries is None:
        return [slug] if (slug := slugify(spec)) else []
    return list(dict.fromkeys(entries.values()))


def set_choice(
    entries: Dict[str, str], model_identifier: str
) -> Optional[str]:
    """The slug a store set picks for a device, or None."""
    model = str(model_identifier or "")
    match = re.match(r"[A-Za-z]+", model)
    family = match.group(0).lower() if match else ""
    for key in (model, family, "default"):
        if key and key in entries:
            return entries[key]
    return None


def load_version(
    tenant_url: str, slug: str, version: int
) -> Optional[Dict[str, Any]]:
    """A stored version's template, or None."""
    path = os.path.join(
        _slug_dir(tenant_url, slugify(slug)),
        f"v{int(version)}",
        "template.json",
    )
    try:
        with open(path, encoding="utf-8") as handle:
            return json.load(handle)
    except (OSError, ValueError):
        return None


FAMILIES = (("iphone", "iPhone"), ("ipad", "iPad"))
LAYER_KINDS = {
    "text": "text",
    "qr": "QR code",
    "image": "image",
    "panel": "panel",
}


def _layer_names(template: Dict[str, Any], warning: str) -> str:
    """'layer 1: cut off on X' -> 'Layer 2 (QR code): cut off on X'."""
    match = re.match(r"layer (\d+): (.*)", warning)
    if not match:
        return warning
    i = int(match.group(1))
    layers = template.get("layers") or []
    kind = (
        layers[i].get("type")
        if i < len(layers) and isinstance(layers[i], dict)
        else None
    )
    label = f"Layer {i + 1}" + (
        f" ({LAYER_KINDS[kind]})" if kind in LAYER_KINDS else ""
    )
    return f"{label}: {match.group(2)}"


def fit_summary(template: Dict[str, Any]) -> List[Dict[str, Any]]:
    """Per family of devices, the layers each screen cuts off or covers:
    [{"family": "iPad", "warnings": [...]}, ...]. Geometry only, no render."""
    _wallrender()
    from wallrender import devices

    canvas = template.get("canvas") or {}
    try:
        size = (int(canvas["width"]), int(canvas["height"]))
    except (KeyError, TypeError, ValueError):
        return []
    screen = "home" if template.get("screen") == "home" else "lock"
    out = []
    for family, label in FAMILIES:
        ids = [
            p["id"] for p in devices.device_profiles() if p["family"] == family
        ]
        try:
            warnings = [
                _layer_names(template, w)
                for w in devices.fit_warnings(template, size, ids, screen)
            ]
        except (KeyError, TypeError, ValueError):
            warnings = ["the layout could not be checked"]
        out.append({"family": label, "warnings": warnings})
    return out
