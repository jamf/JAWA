# # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # #
#
# Copyright (c) 2026 Jamf.  All rights reserved.
#
#       Redistribution and use in source and binary forms, with or without
#       modification, are permitted provided that the following conditions are met:
#               * Redistributions of source code must retain the above copyright
#                 notice, this list of conditions and the following disclaimer.
#               * Redistributions in binary form must reproduce the above copyright
#                 notice, this list of conditions and the following disclaimer in the
#                 documentation and/or other materials provided with the distribution.
#               * Neither the name of the Jamf nor the names of its contributors may be
#                 used to endorse or promote products derived from this software without
#                 specific prior written permission.
#
#       THIS SOFTWARE IS PROVIDED BY JAMF SOFTWARE, LLC "AS IS" AND ANY
#       EXPRESS OR IMPLIED WARRANTIES, INCLUDING, BUT NOT LIMITED TO, THE IMPLIED
#       WARRANTIES OF MERCHANTABILITY AND FITNESS FOR A PARTICULAR PURPOSE ARE
#       DISCLAIMED. IN NO EVENT SHALL JAMF SOFTWARE, LLC BE LIABLE FOR ANY
#       DIRECT, INDIRECT, INCIDENTAL, SPECIAL, EXEMPLARY, OR CONSEQUENTIAL DAMAGES
#       (INCLUDING, BUT NOT LIMITED TO, PROCUREMENT OF SUBSTITUTE GOODS OR SERVICES;
#       LOSS OF USE, DATA, OR PROFITS; OR BUSINESS INTERRUPTION) HOWEVER CAUSED AND
#       ON ANY THEORY OF LIABILITY, WHETHER IN CONTRACT, STRICT LIABILITY, OR TORT
#       (INCLUDING NEGLIGENCE OR OTHERWISE) ARISING IN ANY WAY OUT OF THE USE OF THIS
#       SOFTWARE, EVEN IF ADVISED OF THE POSSIBILITY OF SUCH DAMAGE.
#
# # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # #

"""Tap action automations: triggered by a person tapping a web clip on
the managed device. See README.md, "Tap action automations", and the
device-facing receiver in webhook/tap_receiver.py.
"""

import base64
import functools
import io
import os
import plistlib
import re
import secrets
import time
import uuid
from typing import Any, Dict, List, Mapping, Optional, Tuple

import requests
from PIL import Image, UnidentifiedImageError

from bin import brander_settings, logger
from bin.data_store import (
    get_jawa_address,
    retire_script,
    save_all_webhooks,
    save_script,
)
from bin.tokens import SessionEnded, fresh_token
from views._type_handlers.base import AutomationError, AutomationHandler
from views._type_handlers.jamf_handler import (
    USER_AGENT_STRING,
    VERIFY_SSL,
    XML,
    validate_webhook_name,
    xml_escape,
)

logthis = logger.setup_child_logger("jawa", "tap_handler")

PAGE_FIELDS = (
    "page_title",
    "page_description",
    "confirm_label",
    "success_message",
    "failure_message",
)
PAGE_FIELD_LABELS = {
    "page_title": "Page title",
    "page_description": "Page description",
    "confirm_label": "Confirm button label",
    "success_message": "Success message",
    "failure_message": "Failure message",
}
DEVICE_FAMILIES = ("mobile", "computer")

# Display variables Jamf Pro fills into the web clip URL. The admin can
# add more in Jamf Pro; these two give the default page strings
# something to show.
DISPLAY_VARIABLES = ("DEVICENAME", "SERIALNUMBER")


def mint_token() -> str:
    return secrets.token_urlsafe(32)


def service_url(jawa_address: str, name: str, token: str) -> str:
    """The URL to paste into the Web Clip payload.

    ``$JSSID`` etc. are Jamf Pro payload variables, substituted per
    device when the profile installs. Parameters are joined with ';'
    rather than '&': Jamf Pro refuses to store a web clip profile
    whose URL contains an ampersand in any encoding (409 "Unable to
    update the database"). The receiver splits on either separator.
    Reserved parameters come first so a display value carrying a
    separator cannot disturb them.
    """
    display = ";".join(f"{v}=${v}" for v in DISPLAY_VARIABLES)
    return (
        f"{jawa_address.rstrip('/')}/tap/{name}"
        f"?token={token};id=$JSSID;udid=$UDID;{display}"
    )


_PLACEHOLDER_RE = re.compile(r"\s*\{[A-Za-z0-9_]+\}\s*")
_PRE_PUNCT_RE = re.compile(r"\s+([?!.,:;])")
PROFILE_PREFIX = "JAWA Tap Action: "
PROFILE_ENDPOINT = "/JSSResource/mobiledeviceconfigurationprofiles"


MAX_LABEL_LENGTH = 20
ICON_SIZE = 180


def _label(entry: Dict[str, Any]) -> str:
    """The home-screen label: the admin's own, else the page title."""
    custom = str(entry.get("webclip_label") or "").strip()
    if custom:
        return custom
    text = _PLACEHOLDER_RE.sub(" ", entry.get("page_title", ""))
    text = _PRE_PUNCT_RE.sub(r"\1", text)
    text = " ".join(text.split())
    return text or entry.get("name", "Tap Action")


def _display_name(entry: Dict[str, Any]) -> str:
    """The profile's display name in Jamf Pro.

    Jamf Pro profile names must be unique, and _label() alone is
    derived only from page_title, so two services created from the
    same template with the default title would collide (HTTP 409).
    The service name disambiguates them.
    """
    return f"{PROFILE_PREFIX}{_label(entry)} ({entry['name']})"


def _payload_uuids(entry: Dict[str, Any]) -> Tuple[str, str]:
    """(profile UUID, web clip payload UUID) for this service.

    Minted once at create time and stored on the record, so edit and
    retire rebuild the same profile. Random, never derived from the
    name: Jamf keeps a retired profile (renamed, unscoped), so a
    service deleted and re-created under the same name must not reuse
    its UUIDs -- Jamf answers 409 "Duplicate payload uuid".
    """
    return (
        str(entry.get("profile_uuid") or uuid.uuid4()).upper(),
        str(entry.get("clip_uuid") or uuid.uuid4()).upper(),
    )


_REPO_ROOT = os.path.dirname(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
)
WEBCLIP_ICON = os.path.join(_REPO_ROOT, "static", "img", "webclip-icon.png")


ICON_DIR = os.path.join(_REPO_ROOT, "data", "tap_icons")


@functools.lru_cache(maxsize=1)
def _default_icon() -> bytes:
    """The JAWA logo, 180x180 and precomposed."""
    with open(WEBCLIP_ICON, "rb") as handle:
        return handle.read()


def _icon_path(name: str) -> str:
    return os.path.join(ICON_DIR, f"{name}.png")


def _webclip_icon(entry: Dict[str, Any]) -> bytes:
    """The home-screen icon: the service's own, else the JAWA logo."""
    try:
        with open(_icon_path(entry["name"]), "rb") as handle:
            return handle.read()
    except (OSError, KeyError):
        return _default_icon()


def webclip_preview(entry: Dict[str, Any]) -> Dict[str, str]:
    """Label and icon (as a data URI) for the detail page."""
    icon = base64.b64encode(_webclip_icon(entry)).decode("ascii")
    return {"label": _label(entry), "icon": f"data:image/png;base64,{icon}"}


def _read_icon(files: Any) -> Optional[bytes]:
    """Validate an uploaded icon; return it as a 180x180 PNG.

    Returns None when no file was sent. Raises AutomationError for a
    file that is not an image or is smaller than the icon size. A
    non-square image is cropped to its centre square.
    """
    upload = files.get("webclip_icon") if files else None
    if not upload or not upload.filename:
        return None
    try:
        with Image.open(upload.stream, formats=["PNG", "JPEG"]) as source:
            source.load()
            image = source.convert("RGBA")
    except (UnidentifiedImageError, OSError, ValueError) as err:
        raise AutomationError(
            "Error", "The icon must be a PNG image."
        ) from err
    width, height = image.size
    if min(width, height) < ICON_SIZE:
        raise AutomationError(
            "Error",
            f"The icon must be at least {ICON_SIZE}x{ICON_SIZE} pixels.",
        )
    side = min(width, height)
    left, top = (width - side) // 2, (height - side) // 2
    image = image.crop((left, top, left + side, top + side)).resize(
        (ICON_SIZE, ICON_SIZE), Image.LANCZOS
    )
    out = io.BytesIO()
    image.save(out, format="PNG")
    return out.getvalue()


def _store_icon(name: str, png: bytes) -> None:
    os.makedirs(ICON_DIR, exist_ok=True)
    with open(_icon_path(name), "wb") as handle:
        handle.write(png)


def _remove_icon(name: str) -> None:
    try:
        os.remove(_icon_path(name))
    except OSError:
        pass


def _require_webclip_label(form: Mapping[str, Any]) -> str:
    label = str(form.get("webclip_label") or "").strip()
    if len(label) > MAX_LABEL_LENGTH:
        raise AutomationError(
            "Error",
            f"The home screen label can be at most {MAX_LABEL_LENGTH} "
            "characters.",
        )
    return label


def build_webclip_plist(entry: Dict[str, Any], url: str) -> str:
    name = entry["name"]
    profile_uuid, clip_uuid = _payload_uuids(entry)
    base_id = f"com.jamf.jawa.tap.{name}"
    payload = {
        "PayloadContent": [
            {
                "FullScreen": True,
                "Icon": _webclip_icon(entry),
                "IsRemovable": False,
                "Label": _label(entry),
                "PayloadDescription": (
                    "Configures a JAWA Tap Action web clip"
                ),
                "PayloadDisplayName": "Web Clip",
                "PayloadIdentifier": f"{base_id}.webclip",
                "PayloadType": "com.apple.webClip.managed",
                "PayloadUUID": clip_uuid,
                "PayloadVersion": 1,
                "Precomposed": True,
                "URL": url,
            }
        ],
        "PayloadDisplayName": _display_name(entry),
        "PayloadIdentifier": base_id,
        "PayloadOrganization": "JAWA",
        "PayloadRemovalDisallowed": True,
        "PayloadScope": "System",
        "PayloadType": "Configuration",
        "PayloadUUID": profile_uuid,
        "PayloadVersion": 1,
    }
    return plistlib.dumps(payload, fmt=plistlib.FMT_XML).decode("utf-8")


def build_profile_xml(entry: Dict[str, Any], url: str) -> str:
    """Classic API body. The plist rides inside <payloads> as escaped
    text, which is how Jamf Pro's Classic API takes custom profiles."""
    name = xml_escape(_display_name(entry))
    description = xml_escape(
        f"Created by JAWA for the Tap Action automation "
        f'"{entry["name"]}". Scope it to the devices that should show '
        "the web clip."
    )
    plist = xml_escape(build_webclip_plist(entry, url))
    return (
        "<configuration_profile><general>"
        f"<name>{name}</name><description>{description}</description>"
        "<deployment_method>Install Automatically</deployment_method>"
        "<redeploy_on_update>All</redeploy_on_update>"
        f"<payloads>{plist}</payloads></general>"
        "<scope><all_mobile_devices>false</all_mobile_devices></scope>"
        "</configuration_profile>"
    )


def _headers(session_data: Dict[str, Any]) -> Dict[str, str]:
    return {
        "Content-Type": XML,
        "Authorization": f"Bearer {session_data.get('token')}",
        "User-Agent": USER_AGENT_STRING,
    }


def create_webclip_profile(
    entry: Dict[str, Any], url: str, session_data: Dict[str, Any]
) -> Optional[str]:
    """POST the profile; return its Jamf id, or None on any failure.

    Never raises: the service is still useful without the profile (the
    detail page shows the URL for manual creation), so a Jamf error
    degrades to profile_status "failed" rather than aborting create.
    """
    full_url = f"{session_data['url']}{PROFILE_ENDPOINT}/id/0"
    try:
        fresh_token(session_data)
        resp = requests.post(
            full_url,
            headers=_headers(session_data),
            data=build_profile_xml(entry, url),
            verify=VERIFY_SSL,
            timeout=30,
        )
    except SessionEnded:
        raise
    except Exception as err:
        logthis.error(
            f"Could not create the web clip profile for {entry['name']}: {err}"
        )
        return None
    if resp.status_code >= 400:
        logthis.error(
            f"Jamf Pro refused the web clip profile for {entry['name']}: "
            f"HTTP {resp.status_code} - {resp.text}"
        )
        return None
    match = re.search(r"<id>(\d+)</id>", resp.text or "")
    if not match:
        logthis.error(
            f"Jamf Pro answered {resp.status_code} for the web clip "
            f"profile of {entry['name']} but returned no id."
        )
        return None
    return match.group(1)


def update_webclip_profile(
    entry: Dict[str, Any], url: str, session_data: Dict[str, Any]
) -> bool:
    if not entry.get("jamf_id"):
        return False
    full_url = f"{session_data['url']}{PROFILE_ENDPOINT}/id/{entry['jamf_id']}"
    try:
        fresh_token(session_data)
        resp = requests.put(
            full_url,
            headers=_headers(session_data),
            data=build_profile_xml(entry, url),
            verify=VERIFY_SSL,
            timeout=30,
        )
    except SessionEnded:
        raise
    except Exception as err:
        logthis.error(f"Could not update profile {entry['jamf_id']}: {err}")
        return False
    if resp.status_code >= 400:
        logthis.error(
            f"Jamf Pro refused the profile update for {entry['name']}: "
            f"HTTP {resp.status_code}"
        )
        return False
    return True


def retire_webclip_profile(
    entry: Dict[str, Any], session_data: Dict[str, Any]
) -> None:
    """Rename and unscope rather than delete, mirroring webhook delete."""
    if not entry.get("jamf_id"):
        return
    name = xml_escape(f"{_display_name(entry)}.old.{time.time()}")
    body = (
        "<configuration_profile>"
        f"<general><name>{name}</name></general>"
        "<scope><all_mobile_devices>false</all_mobile_devices>"
        "<mobile_devices/><mobile_device_groups/><buildings/>"
        "<departments/></scope>"
        "</configuration_profile>"
    )
    full_url = f"{session_data['url']}{PROFILE_ENDPOINT}/id/{entry['jamf_id']}"
    try:
        fresh_token(session_data)
        resp = requests.put(
            full_url,
            headers=_headers(session_data),
            data=body,
            verify=VERIFY_SSL,
            timeout=30,
        )
        if resp.status_code >= 400:
            logthis.error(
                f"Error retiring profile {entry['jamf_id']}: "
                f"HTTP {resp.status_code}"
            )
    except SessionEnded:
        raise
    except Exception as err:
        logthis.error(f"Failed to retire profile {entry['jamf_id']}: {err}")


def register_profile(
    entry: Dict[str, Any], session_data: Dict[str, Any], wanted: bool
) -> None:
    """Fill jamf_id/profile_status on a freshly built entry.

    Web Clips are a mobile device management profile payload; Jamf Pro
    has no equivalent for computers, so a computer-family service is
    always skipped regardless of the checkbox.
    """
    entry.setdefault("profile_uuid", str(uuid.uuid4()).upper())
    entry.setdefault("clip_uuid", str(uuid.uuid4()).upper())
    if not wanted or entry.get("device_family") != "mobile":
        entry["jamf_id"] = None
        entry["profile_status"] = "skipped"
        return
    url = service_url(get_jawa_address() or "", entry["name"], entry["token"])
    jamf_id = create_webclip_profile(entry, url, session_data)
    entry["jamf_id"] = jamf_id
    entry["profile_status"] = "created" if jamf_id else "failed"


def _require_page_strings(form: Mapping[str, Any]) -> Dict[str, str]:
    strings = {}
    missing = []
    for key in PAGE_FIELDS:
        value = (form.get(key) or "").strip()
        if not value:
            missing.append(PAGE_FIELD_LABELS[key])
        strings[key] = value
    if missing:
        raise AutomationError(
            "Missing page text",
            "Fill in every page field. Missing: " + ", ".join(missing),
        )
    return strings


def _require_device_family(form: Mapping[str, Any]) -> str:
    family = (form.get("device_family") or "").strip()
    if family not in DEVICE_FAMILIES:
        raise AutomationError(
            "Error", "Device family must be mobile or computer."
        )
    return family


MAX_COOLDOWN_MINUTES = 1440


def _require_cooldown(form: Mapping[str, Any]) -> int:
    """Minutes before a device may run the service again; 0 = no limit."""
    text = str(form.get("cooldown_minutes") or "0").strip()
    if not text.isdigit() or int(text) > MAX_COOLDOWN_MINUTES:
        raise AutomationError(
            "Error",
            "Cooldown must be a whole number of minutes from 0 to "
            f"{MAX_COOLDOWN_MINUTES}.",
        )
    return int(text)


def build_service_entry(
    name: str,
    script_path: str,
    form: Mapping[str, Any],
    session_data: Dict[str, Any],
    description: str = "",
) -> Dict[str, Any]:
    """The full Tap Action record, validated, with a fresh token and no
    Jamf Pro profile yet (Task 4 fills jamf_id/profile_status)."""
    validate_webhook_name(name)
    family = _require_device_family(form)
    strings = _require_page_strings(form)
    cooldown = _require_cooldown(form)
    label = _require_webclip_label(form)
    entry = {
        "name": name,
        "tag": "tap",
        "url": str(session_data.get("url", "")),
        "jawa_admin": str(session_data.get("username", "")),
        "script": script_path,
        "description": description or form.get("description", ""),
        "token": mint_token(),
        "device_family": family,
        "cooldown_minutes": cooldown,
        "jamf_id": None,
        "profile_status": "skipped",
        "webhook_username": "null",
        "webhook_password": "null",
        "api_key": "null",
    }
    entry.update(strings)
    if label:
        entry["webclip_label"] = label
    return entry


def _cooldown_label(automation: Dict[str, Any]) -> str:
    minutes = int(automation.get("cooldown_minutes") or 0)
    if not minutes:
        return "None"
    return f"{minutes} minute{'s' if minutes != 1 else ''} per device"


BRANDER_SOURCE = os.path.join(
    _REPO_ROOT, "data", "workflows", "scripts", "tap_brander.py"
)


def _apply_brander_settings(script: str, form: Mapping[str, Any]) -> str:
    """Apply the edit form's Brander settings (and an optional script
    update) to a Brander's deployed script. Returns a note for the
    success message; raises AutomationError with every problem."""
    if not brander_settings.is_brander_script(script):
        return ""
    note = ""
    try:
        updates = {
            key: form.get(f"brander_{key}")
            for key in brander_settings.SETTINGS
            if form.get(f"brander_{key}") is not None
        }
        # Check every setting before touching the script, so a bad value
        # never leaves a half-applied edit (for example a refreshed script).
        brander_settings.validate(updates)
        if form.get("brander_refresh") == "on":
            brander_settings.refresh_script(script, BRANDER_SOURCE)
            note = " Updated to the latest Brander script."
        if updates:
            brander_settings.write_settings(script, updates)
    except brander_settings.SettingsError as err:
        raise AutomationError(
            "Brander settings", " ".join(err.problems)
        ) from err
    return note


class TapActionHandler(AutomationHandler):
    tag = "tap"
    display_name = "Tap Action"
    summary = (
        "Puts a button on managed iPads and iPhones that runs a script for "
        "that device."
    )
    badge_class = "badge-provisioning"
    icon = "webhook.png"
    supports_edit = True
    supports_auth = False
    copyable_labels = ("Script path", "Web clip URL")

    def get_create_context(self, session_data: Dict) -> Dict[str, Any]:
        return {
            "device_families": DEVICE_FAMILIES,
            "page_fields": PAGE_FIELDS,
        }

    def process_create(
        self, form: Any, files: Any, session_data: Dict
    ) -> Dict[str, Any]:
        name = (form.get("service_name") or "").strip()
        validate_webhook_name(name)
        jawa_address = get_jawa_address()
        if not jawa_address:
            raise AutomationError(
                "Setup Required",
                "Configure your JAWA address before creating a "
                "Tap Action automation.",
                link="/setup",
                link_text="Go to Setup",
            )
        new_file = files.get("new_file")
        if not new_file or not new_file.filename:
            raise AutomationError("Error", "A script file is required.")
        # Validate the form before touching disk so a bad field does not
        # leave an orphaned script behind.
        _require_device_family(form)
        _require_page_strings(form)
        _require_cooldown(form)
        _require_webclip_label(form)
        icon = _read_icon(files)
        script_path = save_script(new_file, name)
        if icon:
            _store_icon(name, icon)
        entry = build_service_entry(name, script_path, form, session_data)
        wanted_profile = form.get("create_profile") == "on"
        register_profile(entry, session_data, wanted_profile)
        url = service_url(jawa_address, name, entry["token"])
        logthis.info(
            f"{session_data.get('username')} created Tap Action "
            f"automation {name}."
        )
        extra_notice = "Web clip URL for the configuration profile:"
        if wanted_profile and entry["device_family"] != "mobile":
            extra_notice = (
                "Web clip profiles are created automatically for "
                "mobile services only; create the profile by hand "
                "with this URL:"
            )
        elif entry["profile_status"] == "failed":
            extra_notice = (
                "Jamf Pro did not accept the web clip profile; create "
                "it by hand with this URL:"
            )
        return {
            "entry": entry,
            "success_msg": "New Tap Action automation created:",
            "new_here": name,
            "new_link": f"/automations/tap/{name}",
            "extra_notice": extra_notice,
            "custom_header": {"URL": url},
        }

    def get_edit_context(self, automation: Dict) -> Dict[str, Any]:
        script = automation.get("script", "")
        if not brander_settings.is_brander_script(script):
            return {}
        from views.template_view import _template_path_options

        return {
            "brander_settings": brander_settings.read_settings(script),
            "brander_template_options": _template_path_options(),
        }

    def process_edit(
        self,
        form: Any,
        files: Any,
        session_data: Dict,
        existing: Dict,
        all_items: Any,
    ) -> Dict[str, Any]:
        strings = _require_page_strings(form)
        family = _require_device_family(form)
        cooldown = _require_cooldown(form)
        label = _require_webclip_label(form)
        icon = _read_icon(files)
        existing.update(strings)
        existing["device_family"] = family
        existing["cooldown_minutes"] = cooldown
        if label:
            existing["webclip_label"] = label
        else:
            existing.pop("webclip_label", None)
        if icon:
            _store_icon(existing["name"], icon)
        rotated = form.get("rotate_token") == "on"
        if rotated:
            existing["token"] = mint_token()
            logthis.info(
                f"{session_data.get('username')} replaced the link token "
                f"of Tap Action automation {existing['name']}."
            )
        if form.get("description"):
            existing["description"] = form.get("description")
        if files.get("new_file") and files["new_file"].filename:
            existing["script"] = save_script(
                files["new_file"], existing["name"]
            )
        brander_note = _apply_brander_settings(existing["script"], form)
        if rotated:
            brander_note += (
                " The link token was replaced; old web clip links stop "
                "working."
            )

        extra_notice = None
        custom_header = None
        if existing.get("jamf_id"):
            profile_url = service_url(
                get_jawa_address() or "",
                existing["name"],
                existing["token"],
            )
            if update_webclip_profile(existing, profile_url, session_data):
                existing["profile_status"] = "created"
            else:
                existing["profile_status"] = "failed"
                extra_notice = (
                    "Jamf Pro did not accept the profile update; "
                    "update it by hand with this URL:"
                )
                custom_header = {"URL": profile_url}
        elif family == "mobile" and form.get("create_profile") == "on":
            # The profile failed or was skipped at create time; after the
            # cause is fixed, one save creates it instead of a hand build.
            register_profile(existing, session_data, True)
            if existing["profile_status"] == "failed":
                extra_notice = (
                    "Jamf Pro did not accept the web clip profile; create "
                    "it by hand with this URL:"
                )
                custom_header = {
                    "URL": service_url(
                        get_jawa_address() or "",
                        existing["name"],
                        existing["token"],
                    )
                }

        save_all_webhooks(all_items)
        logthis.info(
            f"{session_data.get('username')} edited Tap Action "
            f"automation {existing['name']}."
        )
        result = {
            "success_msg": (
                f"Edited Tap Action automation {existing['name']}.{brander_note}"
            )
        }
        if extra_notice:
            result["extra_notice"] = extra_notice
            result["custom_header"] = custom_header
        return result

    def process_delete(
        self, automation: Dict, session_data: Dict
    ) -> Optional[str]:
        retire_webclip_profile(automation, session_data)
        retire_script(automation.get("script", ""))
        _remove_icon(automation.get("name", ""))
        return None

    def get_detail_fields(self, automation: Dict) -> List[Tuple[str, str]]:
        jawa_address = get_jawa_address() or ""
        fields = [
            ("Service name", automation.get("name", "")),
            (
                "Web clip URL",
                service_url(
                    jawa_address,
                    automation.get("name", ""),
                    automation.get("token", ""),
                ),
            ),
            ("Device family", automation.get("device_family", "")),
            ("Cooldown", _cooldown_label(automation)),
            ("Script path", automation.get("script", "")),
            ("Description", automation.get("description", "")),
            ("Created by", automation.get("jawa_admin", "")),
            ("Jamf Pro profile", automation.get("profile_status", "")),
        ]
        for key in PAGE_FIELDS:
            fields.append((PAGE_FIELD_LABELS[key], automation.get(key, "")))
        if automation.get("jamf_id"):
            fields.append(("Jamf Pro profile ID", str(automation["jamf_id"])))
        return fields
