"""Brander's value rules for the console's preview (M3-5).

Deployed Brander scripts are single files, so they carry their own copy
of these rules (build_values, the template-set choice). The console
preview uses this module; tests/test_brander_preview.py feeds the same
records to both and asserts they agree, so the preview cannot drift
from what a device would receive.
"""

import re
from typing import Any, Dict, Optional


def build_values(
    device: Dict[str, Any],
    template: Optional[Dict[str, Any]],
    allow_person_fields: bool = False,
) -> Dict[str, Any]:
    """Same allowlist as tap_brander.build_values (ADR-0013)."""
    general = device.get("general", {})
    location = device.get("location", {})
    values = {
        "device_name": general.get("device_name", ""),
        "serial_number": general.get("serial_number", ""),
        "asset_tag": general.get("asset_tag", ""),
        "jss_id": general.get("id", ""),
        "location": {"building": location.get("building", "")},
    }
    template = template or {}
    if template.get("person_fields") is True and allow_person_fields:
        values["user"] = {
            "real_name": location.get("real_name", ""),
            "username": location.get("username", ""),
            "email": location.get("email_address", ""),
        }
    attribute = (template.get("roles") or {}).get("attribute")
    if attribute:
        for ea in device.get("extension_attributes", []):
            if ea.get("name") == attribute:
                values["role"] = str(ea.get("value") or "").strip()
                break
    return values


def device_family(model_identifier: str) -> str:
    match = re.match(r"[A-Za-z]+", model_identifier or "")
    return match.group(0).lower() if match else ""


def set_entry(
    template_set: Dict[str, Any], device: Dict[str, Any]
) -> Optional[str]:
    """The file a template set picks for this device, or None."""
    templates = template_set.get("templates") or {}
    model = str(device.get("general", {}).get("model_identifier") or "")
    for key in (model, device_family(model), "default"):
        if key and key in templates:
            return templates[key]
    return None
