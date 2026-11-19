"""Role variants: one template, a different background and wording per role.

The device's role comes in as values["role"], a plain string (JAWA Brander
reads it from the extension attribute the template names in roles.attribute).
It is normalised the way Brander matches role images ("Video Conferencing"
-> "videoconferencing") and picks a variant: the matching one, "empty" when
there is no role, otherwise "default". The variant may replace the
background, and its values print as {{role.<name>}}; {{role.name}} is the
role as given.
"""

from __future__ import annotations

from typing import Any


def normalize_role(raw: Any) -> str:
    if isinstance(raw, bool) or not isinstance(raw, (str, int)):
        return ""
    return "".join(str(raw).split()).lower()


def choose(template: dict[str, Any], values: dict[str, Any]) -> tuple[str, dict[str, Any]]:
    """(which variant, the variant) for these values: a variant key,
    'empty' or 'default'. Assumes the template has validated."""
    roles = template["roles"]
    key = normalize_role(values.get("role"))
    if not key:
        return "empty", roles.get("empty", {})
    variants = roles.get("variants", {})
    if key in variants:
        return key, variants[key]
    return "default", roles.get("default", {})


def resolve(template: dict[str, Any], values: dict[str, Any]) -> tuple[dict[str, Any], dict[str, Any]]:
    """The template and values to render: with no roles block, unchanged."""
    if "roles" not in template:
        return template, values
    _, variant = choose(template, values)
    resolved = dict(template)
    if variant.get("background"):
        resolved["background"] = variant["background"]
    raw = values.get("role")
    name = str(raw) if normalize_role(raw) else ""
    out = dict(values)
    out["role"] = {**variant.get("values", {}), "name": name}
    return resolved, out
