"""Brander template store in the console (M3-4): list, upload, activate.

Scoped to the Jamf Pro tenant of the logged-in session, and audited with
the logged-in admin's name. Packages are .brander.json files exported
as .brander.json packages; see bin/brander_store.py for the format and the checks.
"""

import base64
import io
import json
import os
import time
from typing import Any, Dict, List, Optional, Tuple, Union

import requests

from flask import (
    Blueprint,
    Response,
    redirect,
    render_template,
    request,
    send_file,
    session,
    url_for,
)

from bin import brander_settings, brander_store, brander_values, logger
from bin.auth import login_required
from bin.data_store import get_webhooks_by_tag

logthis = logger.setup_child_logger("jawa", "brander_view")

blueprint = Blueprint("brander", __name__)

MAX_UPLOAD_BYTES = brander_store.MAX_PACKAGE_BYTES


@blueprint.app_template_filter("timestamp_to_text")
def timestamp_to_text(seconds: int) -> str:
    return time.strftime("%Y-%m-%d %H:%M UTC", time.gmtime(seconds))


def _brander_templates() -> List[Tuple[str, str]]:
    """(name, template setting) for this tenant's Tap Action Branders."""
    found = []
    tenant = brander_store.tenant_key(session.get("url", ""))
    for entry in get_webhooks_by_tag("tap"):
        if brander_store.tenant_key(entry.get("url", "")) != tenant:
            continue  # another tenant's automation: never shown here
        script = entry.get("script", "")
        if brander_settings.is_brander_script(script):
            path = str(
                brander_settings.read_settings(script).get("template_path")
                or ""
            )
            found.append((entry.get("name", ""), path))
    return found


def used_by() -> dict:
    """slug -> names of the Tap Action Branders whose template setting names
    it, alone (store:<slug>) or in a store set."""
    found: dict = {}
    for name, path in _brander_templates():
        for slug in brander_store.store_slugs(path):
            found.setdefault(slug, []).append(name)
    return found


def _fit(slug: str, version: Any) -> List[Dict[str, Any]]:
    """Which layers each family of devices cuts off or covers, for a stored
    version; [] when it cannot be read."""
    if not version:
        return []
    template = brander_store.load_version(
        session.get("url", ""), slug, version
    )
    return (
        brander_store.fit_summary(template)
        if isinstance(template, dict)
        else []
    )


def _page(status=200, **context) -> tuple:
    templates = brander_store.list_templates(session.get("url", ""))
    fits = {t["slug"]: _fit(t["slug"], t.get("active")) for t in templates}
    return render_template(
        "brander/templates.html",
        templates=templates,
        used_by=used_by(),
        fits=fits,
        **context,
    ), status


@blueprint.route("/brander/templates", methods=["GET"])
@login_required
def templates() -> Union[Response, str, tuple]:
    return _page()


@blueprint.route("/brander/templates", methods=["POST"])
@login_required
def upload() -> Union[Response, str, tuple]:
    upload_file = request.files.get("package")
    if not upload_file or not upload_file.filename:
        return _page(400, problems=["Choose a .brander.json file to upload."])
    raw = upload_file.read(MAX_UPLOAD_BYTES + 1)
    try:
        result = brander_store.save_version(
            session.get("url", ""), raw, session.get("username", "unknown")
        )
    except brander_store.StoreError as err:
        logthis.info(
            f"{session.get('username')} uploaded a Brander template that "
            f"was refused: {err.problems[:3]}"
        )
        return _page(400, problems=err.problems, filename=upload_file.filename)
    logthis.info(
        f"{session.get('username')} uploaded Brander template "
        f"{result['slug']} v{result['version']} (sha256 {result['sha256'][:12]})."
    )
    names = {
        t["slug"]: t["name"]
        for t in brander_store.list_templates(session.get("url", ""))
    }
    return _page(
        uploaded=dict(
            result,
            name=names.get(result["slug"], result["slug"]),
            fit=_fit(result["slug"], result["version"]),
        )
    )


# A built-in sample device for store thumbnails: made-up values, so a
# thumbnail never shows a real device's record.
SAMPLE_DEVICE = {
    "general": {
        "id": 1,
        "device_name": "Sample iPad",
        "serial_number": "XXXX0000",
        "asset_tag": "A-0001",
        "model_identifier": "iPad13,18",
    },
    "location": {"building": "Main building"},
}
THUMBNAIL_PX = 240


@blueprint.route("/brander/templates/<slug>/thumbnail.png")
@login_required
def thumbnail(slug: str) -> Union[Response, tuple]:
    """The active version rendered for the sample device, at most
    THUMBNAIL_PX on its long side. 404 when there is nothing to show."""
    path = brander_store.active_template_path(session.get("url", ""), slug)
    if not path:
        return "No active version.", 404
    try:
        with open(path, encoding="utf-8") as handle:
            template = json.load(handle)
        wallrender = brander_store._wallrender()
        values = brander_values.build_values(SAMPLE_DEVICE, template)
        image = wallrender.render(
            template,
            values,
            _folder_assets([os.path.dirname(path), BRANDER_ASSETS_DIR]),
        )
    except Exception as err:  # noqa: BLE001 -- a bad stored template must not 500 the page
        logthis.info(
            f"Thumbnail for Brander template {slug} failed: {type(err).__name__}"
        )
        return "The template could not be rendered.", 422
    image.thumbnail((THUMBNAIL_PX, THUMBNAIL_PX))
    buffer = io.BytesIO()
    image.save(buffer, "PNG")
    buffer.seek(0)
    resp = send_file(buffer, mimetype="image/png")
    resp.headers["Cache-Control"] = "private, max-age=300"
    return resp


@blueprint.route("/brander/templates/<slug>/activate", methods=["POST"])
@login_required
def activate(slug: str) -> Union[Response, str, tuple]:
    text = (request.form.get("version") or "").strip()
    if not text.isdigit():
        return _page(400, problems=["Choose a version to activate."])
    try:
        brander_store.activate(
            session.get("url", ""),
            slug,
            int(text),
            session.get("username", "unknown"),
        )
    except brander_store.StoreError as err:
        return _page(400, problems=err.problems)
    logthis.info(
        f"{session.get('username')} activated Brander template {slug} v{text}."
    )
    return redirect(url_for("brander.templates"))


# --- Preview a template on a real device, sending nothing (M3-5) ----------

_base_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
BRANDER_ASSETS_DIR = os.path.join(
    _base_dir, "data", "workflows", "assets", "brander"
)
USER_AGENT = "JAWA Brander preview"


def _jamf_get(path: str) -> requests.Response:
    """A read-only Classic API call with the admin's session token."""
    from bin.tokens import fresh_token

    session_data = {
        "token": session.get("token"),
        "expires": session.get("expires"),
    }
    fresh_token(session_data)
    return requests.get(
        f"{session.get('url', '').rstrip('/')}/JSSResource/{path}",
        headers={
            "Authorization": f"Bearer {session_data['token']}",
            "Accept": "application/json",
            "User-Agent": USER_AGENT,
        },
        timeout=30,
    )


def preview_options() -> List[Tuple[str, str]]:
    """(value, label) for the preview's template picker: stored templates
    and shipped files by their display name, store sets by their parts."""
    stored = brander_store.list_templates(session.get("url", ""))
    names = {t["slug"]: t.get("name") or t["slug"] for t in stored}
    options = [
        (f"store:{t['slug']}", f"{names[t['slug']]} (store)") for t in stored
    ]
    sets = sorted(
        {
            path.strip()
            for _, path in _brander_templates()
            if path.strip().startswith("store:") and "=" in path
        }
    )
    for spec in sets:
        try:
            entries = brander_store.store_set(spec[len("store:") :]) or {}
        except brander_store.StoreError:
            entries = {}
        parts = ", ".join(
            f"{key}: {names.get(slug, slug)}" for key, slug in entries.items()
        )
        options.append((spec, f"Store set: {parts}" if parts else spec))
    shipped = (
        sorted(
            name
            for name in os.listdir(BRANDER_ASSETS_DIR)
            if name.endswith(".json")
        )
        if os.path.isdir(BRANDER_ASSETS_DIR)
        else []
    )
    for name in shipped:
        options.append((name, f"{_shipped_label(name)} (shipped)"))
    return options


def _shipped_label(name: str) -> str:
    """A shipped file's template name, or its file name when it has none."""
    try:
        with open(
            os.path.join(BRANDER_ASSETS_DIR, name), encoding="utf-8"
        ) as handle:
            data = json.load(handle)
    except (OSError, ValueError):
        return name
    if (
        isinstance(data, dict)
        and isinstance(data.get("name"), str)
        and data["name"].strip()
    ):
        return data["name"].strip()
    if isinstance(data, dict) and "templates" in data:
        return f"Template set {name.rsplit('.', 1)[0]}"
    return name


def preview_choices() -> List[str]:
    return [value for value, _ in preview_options()]


def _template_file(
    choice: str, device: Dict[str, Any]
) -> Tuple[Optional[str], str]:
    """(path of the template to render, note on how it was chosen)."""
    if choice.startswith("store:"):
        spec = choice[len("store:") :]
        try:
            entries = brander_store.store_set(spec)
        except brander_store.StoreError:
            return None, f"{choice} is not a valid store set"
        if entries is None:
            return brander_store.active_template_path(
                session.get("url", ""), spec
            ), choice
        # Same rule as the script: model identifier, family, then default.
        slug = brander_store.set_choice(
            entries, device.get("general", {}).get("model_identifier")
        )
        if not slug:
            return (
                None,
                f"{choice} has no template for this device and no default",
            )
        return (
            brander_store.active_template_path(session.get("url", ""), slug),
            f"{choice} picked store:{slug}",
        )
    path = os.path.join(BRANDER_ASSETS_DIR, choice)
    with open(path, encoding="utf-8") as handle:
        data = json.load(handle)
    if (
        isinstance(data, dict)
        and "templates" in data
        and "schema_version" not in data
    ):
        entry = brander_values.set_entry(data, device)
        if not isinstance(entry, str) or not entry:
            return None, f"{choice} has no usable entry for this device"
        # Same rule as the script: entries are relative to the set file.
        resolved = os.path.realpath(os.path.join(BRANDER_ASSETS_DIR, entry))
        if not resolved.startswith(
            os.path.realpath(BRANDER_ASSETS_DIR) + os.sep
        ):
            return None, f"{choice} points outside the Brander assets folder"
        return resolved, f"{choice} picked {entry}"
    return path, choice


def _folder_assets(folders: List[str]):
    def resolve(asset_id: str) -> bytes:
        wallrender = brander_store._wallrender()
        if wallrender.schema.ASSET_ID.fullmatch(asset_id):
            for folder in folders:
                root = os.path.realpath(folder)
                for ext in ("png", "jpg", "jpeg"):
                    path = os.path.realpath(
                        os.path.join(root, f"{asset_id}.{ext}")
                    )
                    if path.startswith(root + os.sep) and os.path.isfile(path):
                        with open(path, "rb") as handle:
                            return handle.read()
        raise KeyError(asset_id)

    return resolve


def _device_fit(
    wallrender, template, size, model_identifier
) -> Dict[str, Any]:
    """Layers cut off or covered on the device's family of screens (every
    iPhone or iPad profile), for the template's screen (both: lock)."""
    from wallrender import devices

    family = brander_values.device_family(model_identifier)
    profiles = [
        p for p in devices.device_profiles() if p["family"] == family
    ] or devices.device_profiles()
    screen = "home" if template.get("screen") == "home" else "lock"
    return {
        "devices": [p["name"] for p in profiles],
        "screen": screen,
        "warnings": devices.fit_warnings(
            template, size, [p["id"] for p in profiles], screen
        ),
    }


def _preview_page(status=200, **context) -> tuple:
    return render_template(
        "brander/preview.html", choices=preview_options(), **context
    ), status


@blueprint.route("/brander/preview", methods=["GET"])
@login_required
def preview_form() -> Union[Response, str, tuple]:
    return _preview_page()


@blueprint.route("/brander/preview", methods=["POST"])
@login_required
def preview() -> Union[Response, str, tuple]:
    choice = (request.form.get("template") or "").strip()
    jss_text = (request.form.get("jss_id") or "").strip()
    allow = request.form.get("allow_person_fields") == "on"
    form = {"template": choice, "jss_id": jss_text, "allow": allow}
    if choice not in preview_choices():
        return _preview_page(
            400, form=form, problems=["Choose a template from the list."]
        )
    if not jss_text.isdigit():
        return _preview_page(
            400,
            form=form,
            problems=["Enter the device's Jamf Pro ID (a number)."],
        )
    try:
        resp = _jamf_get(f"mobiledevices/id/{int(jss_text)}")
    except requests.RequestException as err:
        return _preview_page(
            502,
            form=form,
            problems=[f"Could not reach Jamf Pro ({type(err).__name__})."],
        )
    if resp.status_code == 404:
        return _preview_page(
            404,
            form=form,
            problems=[f"No mobile device with Jamf ID {jss_text}."],
        )
    if resp.status_code >= 400:
        return _preview_page(
            502,
            form=form,
            problems=[
                f"Jamf Pro refused the lookup (HTTP {resp.status_code})."
            ],
        )
    try:
        device = resp.json().get("mobile_device", {})
    except (ValueError, AttributeError):
        return _preview_page(
            502,
            form=form,
            problems=["Jamf Pro's device lookup did not return JSON."],
        )
    try:
        path, chosen = _template_file(choice, device)
    except (OSError, ValueError):
        return _preview_page(
            400, form=form, problems=[f"{choice} could not be read."]
        )
    if not path or not os.path.isfile(path):
        return _preview_page(
            400, form=form, problems=[f"No template to render: {chosen}."]
        )
    try:
        with open(path, encoding="utf-8") as handle:
            template = json.load(handle)
    except (OSError, ValueError, RecursionError):
        return _preview_page(
            400, form=form, problems=[f"{chosen} is not valid JSON."]
        )
    wallrender = brander_store._wallrender()
    try:
        problems = wallrender.validate(template)
    except Exception as err:  # noqa: BLE001 -- a crafted template must not 500 the page
        problems = [f"validation failed ({type(err).__name__})"]
    if problems:
        return _preview_page(422, form=form, problems=problems)
    values = brander_values.build_values(device, template, allow)
    assets = _folder_assets([os.path.dirname(path), BRANDER_ASSETS_DIR])
    try:
        image = wallrender.render(template, values, assets)
        warnings = wallrender.lint(template, values, assets)
    except wallrender.TemplateError as err:
        return _preview_page(422, form=form, problems=err.problems)
    buffer = io.BytesIO()
    image.save(buffer, "PNG")
    general = device.get("general", {})
    fit = _device_fit(
        wallrender, template, image.size, general.get("model_identifier", "")
    )
    logthis.info(
        f"{session.get('username')} previewed {chosen} for device {jss_text} (nothing sent)."
    )
    return _preview_page(
        form=form,
        chosen=chosen,
        warnings=warnings,
        fit=fit,
        image=base64.b64encode(buffer.getvalue()).decode("ascii"),
        size=image.size,
        device={
            "name": general.get("device_name", ""),
            "model": general.get("model_identifier", ""),
            "supervised": general.get("supervised"),
            "os_type": general.get("os_type", ""),
        },
    )


@blueprint.route("/brander/ea-names.json")
@login_required
def ea_names() -> Union[Response, tuple]:
    """The tenant's mobile device extension attribute names (names only,
    never values) for choosing a template's role attribute."""
    try:
        resp = _jamf_get("mobiledeviceextensionattributes")
        if resp.status_code >= 400:
            return {
                "error": f"Jamf Pro refused the lookup (HTTP {resp.status_code})."
            }, 502
        items = resp.json().get("mobile_device_extension_attributes", [])
    except (requests.RequestException, ValueError, AttributeError) as err:
        return {
            "error": f"Could not read the attribute names from Jamf Pro ({type(err).__name__})."
        }, 502
    names = sorted(
        {str(item.get("name", "")) for item in items if item.get("name")}
    )
    payload = json.dumps(
        {"kind": "jamf-ea-names", "format": 1, "names": names}, indent=1
    )
    return send_file(
        io.BytesIO(payload.encode()),
        mimetype="application/json",
        as_attachment=True,
        download_name="jamf-ea-names.json",
    )
