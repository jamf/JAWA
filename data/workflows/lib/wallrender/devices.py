"""Device profiles: how iOS crops a wallpaper on each device class, and which
parts of the screen the clock, controls and dock cover.

iOS scales a wallpaper to fill the screen ("cover") and centers it, so a
template whose shape differs from the screen loses its edges. Regions here
are (x0, y0, x1, y1) fractions: of the screen for zones, of the template
canvas for what this module returns.
"""

from __future__ import annotations

import json
from functools import lru_cache
from importlib import resources
from typing import Any

Region = tuple[float, float, float, float]
MAX_DEVICE_IDS = 20


@lru_cache(maxsize=1)
def _data() -> dict[str, Any]:
    return json.loads((resources.files("wallrender") / "device_profiles.json").read_text("utf-8"))


def device_profiles() -> list[dict[str, Any]]:
    return _data()["profiles"]


def orientations(profile: dict[str, Any]) -> list[tuple[str, tuple[int, int]]]:
    w, h = profile["screen"]
    found = [("portrait", (w, h))]
    if profile["rotates"]:
        found.append(("landscape", (h, w)))
    return found


def visible_region(canvas: tuple[int, int], screen: tuple[int, int]) -> Region:
    """The part of the canvas a screen shows after cover-scaling and centering."""
    cw, ch = canvas
    sw, sh = screen
    scale = max(sw / cw, sh / ch)
    vw = min(1.0, sw / scale / cw)
    vh = min(1.0, sh / scale / ch)
    x0 = (1 - vw) / 2
    y0 = (1 - vh) / 2
    return (round(x0, 6), round(y0, 6), round(x0 + vw, 6), round(y0 + vh, 6))


def zones_on_canvas(profile: dict[str, Any], orientation: str, screen_kind: str,
                    canvas: tuple[int, int]) -> list[tuple[str, Region]]:
    """The profile's covered areas, mapped into canvas fractions."""
    size = dict(orientations(profile))[orientation]
    vx0, vy0, vx1, vy1 = visible_region(canvas, size)
    out = []
    for zone in profile["zones"][orientation][screen_kind]:
        x0, y0, x1, y1 = zone["box"]
        out.append((zone["label"], (vx0 + x0 * (vx1 - vx0), vy0 + y0 * (vy1 - vy0),
                                    vx0 + x1 * (vx1 - vx0), vy0 + y1 * (vy1 - vy0))))
    return out


def _overlaps(a: Region, b: Region) -> bool:
    return a[0] < b[2] and b[0] < a[2] and a[1] < b[3] and b[1] < a[3]


def fit_warnings(template: dict[str, Any], canvas: tuple[int, int], device_ids: list[str],
                 screen_kind: str = "lock") -> list[str]:
    """Layers that a device crops off, or that sit under its clock, controls
    or dock. `canvas` is the rendered size (the template may omit it)."""
    eps = 1e-6
    warnings = []
    profiles = {p["id"]: p for p in device_profiles()}
    # Each distinct id once, and at most MAX_DEVICE_IDS of them.
    for device_id in list(dict.fromkeys(device_ids))[:MAX_DEVICE_IDS]:
        profile = profiles.get(device_id)
        if not profile:
            continue
        for orientation, size in orientations(profile):
            where = profile["name"] + (f" ({orientation})" if profile["rotates"] else "")
            seen = visible_region(canvas, size)
            zones = zones_on_canvas(profile, orientation, screen_kind, canvas)
            for i, layer in enumerate(template.get("layers", [])):
                b = layer["box"]
                box = (b["x"], b["y"], b["x"] + b["w"], b["y"] + b["h"])
                if (box[0] < seen[0] - eps or box[1] < seen[1] - eps
                        or box[2] > seen[2] + eps or box[3] > seen[3] + eps):
                    warnings.append(f"layer {i}: cut off on {where}")
                    continue
                for label, zone in zones:
                    if _overlaps(box, zone):
                        warnings.append(f"layer {i}: under the {label} on {where}")
    return warnings
