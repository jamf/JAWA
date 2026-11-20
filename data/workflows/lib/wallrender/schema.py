"""Template schema v1: validation only, no rendering.

A template is untrusted input (it is uploaded to the JAWA server), so every
field is checked and bounded before anything is drawn."""

from __future__ import annotations

import math
import re
from typing import Any

SCHEMA_VERSION = 1
MAX_SIDE = 8192
MAX_PIXELS = 40_000_000
MAX_LAYERS = 50
MAX_TEXT = 500
MAX_VALUE_CHARS = 200  # each substituted value
MAX_QR = 512
MAX_TEXT_SIZE = 0.5  # font size as a fraction of canvas height
FONTS = {"noto-sans"}
ALIGNS = {"left", "center", "right"}
SCREENS = {"lock", "home", "both"}  # which screen a template is designed for
OVERFLOWS = {"shrink", "ellipsis"}  # what a text layer does when its text is too long
LAYER_TYPES = ("text", "qr", "image", "panel")
MAX_RADIUS = 0.5  # a panel's corner radius, as a fraction of its shorter side

ASSET_ID = re.compile(r"[a-z0-9_-]{1,64}")  # always used with fullmatch
COLOR = re.compile(r"#[0-9A-Fa-f]{6}([0-9A-Fa-f]{2})?")
PLACEHOLDER = re.compile(r"\{\{(.*?)\}\}", re.DOTALL)
VARIABLE_PATH = re.compile(r"[A-Za-z][A-Za-z0-9_]*(\.[A-Za-z][A-Za-z0-9_]*)*")


class TemplateError(ValueError):
    """The template failed validation; .problems lists why."""

    def __init__(self, problems: list[str]):
        super().__init__("; ".join(problems))
        self.problems = problems


def variables_in(text: str) -> list[str]:
    return [m.strip() for m in PLACEHOLDER.findall(text)]


def _number(value: Any) -> bool:
    """A real, finite number (bools and NaN/inf are not numbers here)."""
    return isinstance(value, (int, float)) and not isinstance(value, bool) and math.isfinite(value)


def _int(value: Any) -> bool:
    return type(value) is int


def _matches(pattern: re.Pattern, value: Any) -> bool:
    return isinstance(value, str) and pattern.fullmatch(value) is not None


def _check_box(where: str, box: Any, problems: list[str]) -> None:
    if not isinstance(box, dict) or not all(_number(box.get(k)) for k in "xywh"):
        problems.append(f"{where}: box needs numeric x, y, w, h (fractions of the canvas)")
        return
    x, y, w, h = (box[k] for k in "xywh")
    if x < 0 or y < 0 or w <= 0 or h <= 0 or x + w > 1 + 1e-9 or y + h > 1 + 1e-9:
        problems.append(f"{where}: box must lie inside the canvas (0..1), got x={x} y={y} w={w} h={h}")


def _check_color(where: str, value: Any, problems: list[str]) -> None:
    if value is not None and not _matches(COLOR, value):
        problems.append(f"{where}: color must be #RRGGBB or #RRGGBBAA, got {value!r}")


PERSON_FIELDS_ROOT = "user"


def _uses_person_fields(text: str) -> bool:
    return any(name == PERSON_FIELDS_ROOT or name.startswith(PERSON_FIELDS_ROOT + ".")
               for name in variables_in(text))


def _check_variables(where: str, text: str, problems: list[str]) -> None:
    for name in variables_in(text):
        if not VARIABLE_PATH.fullmatch(name):
            problems.append(f"{where}: invalid variable {{{{{name}}}}} (use letters, digits, _ and dots)")


def _check_flag(where: str, layer: dict, key: str, problems: list[str]) -> None:
    if key in layer and not isinstance(layer[key], bool):
        problems.append(f"{where}: {key} must be true or false")


MAX_VARIANTS = 50
MAX_VARIANT_VALUES = 20
ROLE_KEY = re.compile(r"[a-z0-9_-]{1,64}")
ROLE_VALUE_NAME = re.compile(r"[a-z][a-z0-9_]{0,31}")
VARIANT_FIELDS = {"background", "values"}


def _check_variant(where: str, variant: Any, canvas: Any, problems: list[str]) -> None:
    if not isinstance(variant, dict):
        problems.append(f"{where}: must be an object")
        return
    unknown = set(variant) - VARIANT_FIELDS
    if unknown:
        problems.append(f"{where}: unknown fields {sorted(unknown)}")
    if "background" in variant:
        bg = variant["background"]
        if not isinstance(bg, dict) or not ({"color", "asset"} & bg.keys()):
            problems.append(f"{where}: background needs a color or an asset")
        else:
            if "color" in bg and not _matches(COLOR, bg["color"]):
                problems.append(f"{where}: background color must be #RRGGBB or #RRGGBBAA")
            if "asset" in bg and not _matches(ASSET_ID, bg["asset"]):
                problems.append(f"{where}: background asset id must match {ASSET_ID.pattern}")
            if canvas is None and "asset" not in bg:
                problems.append(f"{where}: a color background needs the template's canvas")
    values = variant.get("values", {})
    if not isinstance(values, dict) or len(values) > MAX_VARIANT_VALUES:
        problems.append(f"{where}: values must be an object of at most {MAX_VARIANT_VALUES}")
        return
    for name, value in values.items():
        if name == "name":
            problems.append(f"{where}: 'name' is reserved for the role itself")
        elif not _matches(ROLE_VALUE_NAME, name):
            problems.append(f"{where}: value name {name!r} must match {ROLE_VALUE_NAME.pattern}")
        if not isinstance(value, str) or len(value) > MAX_VALUE_CHARS:
            problems.append(f"{where}: values must be strings of at most {MAX_VALUE_CHARS} characters")


def _check_roles(roles: Any, canvas: Any, problems: list[str]) -> None:
    """Role variants: background and wording chosen by the device's role."""
    if not isinstance(roles, dict):
        problems.append("roles must be an object")
        return
    unknown = set(roles) - {"attribute", "variants", "empty", "default"}
    if unknown:
        problems.append(f"roles: unknown fields {sorted(unknown)}")
    if "attribute" in roles and not (isinstance(roles["attribute"], str) and 0 < len(roles["attribute"]) <= 100):
        problems.append("roles: attribute must be the extension attribute's name (at most 100 characters)")
    variants = roles.get("variants", {})
    if not isinstance(variants, dict) or len(variants) > MAX_VARIANTS:
        problems.append(f"roles: variants must be an object of at most {MAX_VARIANTS}")
        variants = {}
    for key, variant in variants.items():
        if not _matches(ROLE_KEY, key):
            problems.append(f"roles: variant key {key!r} must be the role in lowercase without spaces "
                            f"({ROLE_KEY.pattern})")
        _check_variant(f"roles variant {key!r}", variant, canvas, problems)
    for name in ("empty", "default"):
        if name in roles:
            _check_variant(f"roles {name}", roles[name], canvas, problems)


def validate(template: Any) -> list[str]:
    """Return a list of problems; empty means the template can be rendered."""
    problems: list[str] = []
    if not isinstance(template, dict):
        return ["template must be a JSON object"]
    if not (_int(template.get("schema_version")) and template["schema_version"] == SCHEMA_VERSION):
        problems.append(f"schema_version must be {SCHEMA_VERSION}")

    canvas = template.get("canvas")
    if canvas is not None:
        w = canvas.get("width") if isinstance(canvas, dict) else None
        h = canvas.get("height") if isinstance(canvas, dict) else None
        if not (_int(w) and _int(h) and 0 < w <= MAX_SIDE and 0 < h <= MAX_SIDE and w * h <= MAX_PIXELS):
            problems.append(f"canvas must be whole pixels, at most {MAX_SIDE} per side and {MAX_PIXELS} in total")

    background = template.get("background")
    if not isinstance(background, dict) or not ({"color", "asset"} & background.keys()):
        problems.append("background needs a color or an asset")
    else:
        if "color" in background and not _matches(COLOR, background["color"]):
            problems.append("background: color must be #RRGGBB or #RRGGBBAA")
        if "asset" in background and not _matches(ASSET_ID, background["asset"]):
            problems.append(f"background: asset id must match {ASSET_ID.pattern}")
        if canvas is None and "asset" not in background:
            problems.append("canvas is required when the background is a color")

    if "roles" in template:
        _check_roles(template["roles"], canvas, problems)

    # Person fields (user.*) are opt-in per template and never in a QR code
    # (JAWA ADR-0013: what a lock screen may show).
    if "screen" in template and not (isinstance(template["screen"], str) and template["screen"] in SCREENS):
        problems.append(f"screen must be one of {sorted(SCREENS)}")

    person_fields = template.get("person_fields", False)
    if not isinstance(person_fields, bool):
        problems.append("person_fields must be true or false")

    layers = template.get("layers", [])
    if not isinstance(layers, list) or len(layers) > MAX_LAYERS:
        problems.append(f"layers must be a list of at most {MAX_LAYERS}")
        return problems
    for i, layer in enumerate(layers):
        where = f"layer {i}"
        if not isinstance(layer, dict):
            problems.append(f"{where}: must be an object")
            continue
        kind = layer.get("type")
        if kind not in LAYER_TYPES:
            problems.append(f"{where}: unknown layer type {kind!r}")
            continue
        _check_box(where, layer.get("box"), problems)
        if kind == "text":
            text = layer.get("text")
            if not isinstance(text, str) or len(text) > MAX_TEXT:
                problems.append(f"{where}: text must be a string of at most {MAX_TEXT} characters")
            else:
                _check_variables(where, text, problems)
                if _uses_person_fields(text) and person_fields is not True:
                    problems.append(f"{where}: uses user.* fields, so the template must set "
                                    "person_fields to true")
            size = layer.get("size")
            if not (_number(size) and 0 < size <= MAX_TEXT_SIZE):
                problems.append(f"{where}: size must be a fraction of canvas height in (0, {MAX_TEXT_SIZE}]")
            _check_color(where, layer.get("color"), problems)
            if not (isinstance(layer.get("align", "center"), str) and layer.get("align", "center") in ALIGNS):
                problems.append(f"{where}: align must be one of {sorted(ALIGNS)}")
            if not (isinstance(layer.get("font", "noto-sans"), str) and layer.get("font", "noto-sans") in FONTS):
                problems.append(f"{where}: font must be one of {sorted(FONTS)}")
            overflow = layer.get("overflow", "shrink")
            if not (isinstance(overflow, str) and overflow in OVERFLOWS):
                problems.append(f"{where}: overflow must be one of {sorted(OVERFLOWS)}")
            if "min_size" in layer:
                floor = layer["min_size"]
                top = size if _number(size) else MAX_TEXT_SIZE
                if not (_number(floor) and 0 < floor <= top):
                    problems.append(f"{where}: min_size must be a fraction of canvas height in (0, size]")
            _check_flag(where, layer, "hide_if_empty", problems)
        elif kind == "qr":
            data = layer.get("data")
            if not isinstance(data, str) or not data or len(data) > MAX_QR:
                problems.append(f"{where}: qr data must be a non-empty string of at most {MAX_QR} characters")
            else:
                _check_variables(where, data, problems)
                if _uses_person_fields(data):
                    problems.append(f"{where}: QR codes may not carry user.* fields; anyone can scan them")
            _check_color(where, layer.get("color"), problems)
            _check_color(where, layer.get("background"), problems)
            _check_flag(where, layer, "hide_if_empty", problems)
        elif kind == "image":
            if not _matches(ASSET_ID, layer.get("asset")):
                problems.append(f"{where}: asset id must match {ASSET_ID.pattern}")
        elif kind == "panel":
            _check_color(where, layer.get("color"), problems)
            opacity = layer.get("opacity", 1)
            if not (_number(opacity) and 0 <= opacity <= 1):
                problems.append(f"{where}: opacity must be a number from 0 to 1")
            radius = layer.get("radius", 0)
            if not (_number(radius) and 0 <= radius <= MAX_RADIUS):
                problems.append(f"{where}: radius must be a fraction of the shorter side from 0 to {MAX_RADIUS}")
    return problems
