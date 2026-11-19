"""Draw a validated template. Pure: no network, no Flask, no Jamf.

The same function runs in EWOK's preview and in JAWA Brander, so what is
designed is what the device receives. Templates and values are untrusted
(this runs on the JAWA server), so every step is bounded in CPU and memory,
and any failure surfaces as TemplateError."""

from __future__ import annotations

import io
import logging
import math
import warnings
from importlib import resources
from typing import Any, Callable, Union

import qrcode
import qrcode.exceptions
from PIL import Image, ImageDraw, ImageFont, ImageOps, ImageStat, UnidentifiedImageError

from .roles import choose, resolve
from .schema import MAX_PIXELS, MAX_QR, MAX_SIDE, MAX_TEXT, TemplateError, validate
from .variables import substitute

logger = logging.getLogger("wallrender")

AssetData = Union[bytes, Image.Image]
AssetResolver = Callable[[str], AssetData]

MIN_FONT_PX = 6
MAX_ASPECT = 50  # assets thinner than 1:50 would force enormous resizes
ASSET_FORMATS = ["PNG", "JPEG"]  # never EPS/PS (Ghostscript) or other exotic decoders


def _font_bytes() -> bytes:
    return (resources.files("wallrender") / "fonts" / "NotoSans.ttf").read_bytes()


_FONT_BYTES = _font_bytes()  # read-only and shared; FreeTypeFont objects are per render


class _Session:
    """Per-render caches: fonts (FreeTypeFont is not documented as thread-safe)
    and decoded assets (so a logo used in several layers is decoded once)."""

    def __init__(self, assets: AssetResolver):
        self._resolve = assets
        self._fonts: dict[int, ImageFont.FreeTypeFont] = {}
        self._assets: dict[str, Image.Image] = {}

    def font(self, px: int) -> ImageFont.FreeTypeFont:
        if px not in self._fonts:
            # BASIC layout keeps output identical across hosts (no Raqm);
            # the variable font is pinned to its Regular instance.
            f = ImageFont.truetype(io.BytesIO(_FONT_BYTES), px, layout_engine=ImageFont.Layout.BASIC)
            try:
                f.set_variation_by_name("Regular")
            except (OSError, ValueError):
                pass
            self._fonts[px] = f
        return self._fonts[px]

    def asset(self, asset_id: str) -> Image.Image:
        if asset_id not in self._assets:
            try:
                data = self._resolve(asset_id)
            except KeyError as e:
                raise TemplateError([f"asset {asset_id!r} not found"]) from e
            self._assets[asset_id] = _open(asset_id, data)
        return self._assets[asset_id]


def _check_size(asset_id: str, width: int, height: int) -> None:
    if width > MAX_SIDE or height > MAX_SIDE or width * height > MAX_PIXELS:
        raise TemplateError([f"asset {asset_id!r} is too large ({width}x{height}; "
                             f"at most {MAX_SIDE} per side and {MAX_PIXELS} pixels)"])
    if max(width, height) > MAX_ASPECT * min(width, height):
        raise TemplateError([f"asset {asset_id!r} has an extreme aspect ratio ({width}x{height})"])


def _open(asset_id: str, data: AssetData) -> Image.Image:
    # _check_size is the real bound; Pillow's global bomb check is only a
    # backstop, and its warning or error must not escape as a raw exception.
    with warnings.catch_warnings():
        warnings.simplefilter("ignore", Image.DecompressionBombWarning)
        if isinstance(data, Image.Image):
            img = data
        else:
            try:
                img = Image.open(io.BytesIO(data), formats=ASSET_FORMATS)
            except Image.DecompressionBombError as e:
                raise TemplateError([f"asset {asset_id!r} is too large"]) from e
            except (UnidentifiedImageError, OSError, TypeError) as e:
                raise TemplateError([f"asset {asset_id!r} must be a PNG or JPEG image"]) from e
        _check_size(asset_id, *img.size)  # before load(): nothing is decoded yet
        try:
            img.load()
        except Image.DecompressionBombError as e:
            raise TemplateError([f"asset {asset_id!r} is too large"]) from e
    img = ImageOps.exif_transpose(img)
    return img.convert("RGBA")


def _rgba(hex_color: str | None, default: tuple[int, int, int, int]) -> tuple[int, int, int, int]:
    if not hex_color:
        return default
    h = hex_color.lstrip("#")
    r, g, b = (int(h[i:i + 2], 16) for i in (0, 2, 4))
    a = int(h[6:8], 16) if len(h) == 8 else 255
    return (r, g, b, a)


def _box_px(box: dict[str, float], size: tuple[int, int]) -> tuple[int, int, int, int]:
    w, h = size
    return (round(box["x"] * w), round(box["y"] * h), max(1, round(box["w"] * w)), max(1, round(box["h"] * h)))


def _canvas(template: dict[str, Any], session: _Session) -> Image.Image:
    background = template["background"]
    canvas = template.get("canvas")
    if "asset" in background:
        bg = session.asset(background["asset"])
        if canvas:
            # fit() crops in source space before resizing, so no intermediate
            # is ever larger than the canvas.
            bg = ImageOps.fit(bg, (canvas["width"], canvas["height"]), Image.Resampling.LANCZOS)
        return bg.copy()
    return Image.new("RGBA", (canvas["width"], canvas["height"]), _rgba(background["color"], (0, 0, 0, 255)))


def _fit_font(session: _Session, text: str, px: int, bw: int, bh: int, floor: int = MIN_FONT_PX,
              align: str = "left"):
    """Largest size in [floor, px] whose text fits the box: one measurement plus
    a few checks, never a pixel-by-pixel walk down from a huge size."""
    probe = ImageDraw.Draw(Image.new("L", (1, 1)))
    for _ in range(4):
        f = session.font(px)
        left, top, right, bottom = probe.textbbox((0, 0), text, font=f, align=align)
        width, height = right - left, bottom - top
        if (width <= bw and height <= bh) or px <= floor:
            return f, (left, top, width, height)
        scale = min(bw / max(width, 1), bh / max(height, 1))
        px = max(floor, min(px - 1, math.floor(px * scale)))
    f = session.font(px)
    left, top, right, bottom = probe.textbbox((0, 0), text, font=f, align=align)
    return f, (left, top, right - left, bottom - top)


ELLIPSIS = "\u2026"


class _TextFit:
    """How one text layer came out, for lint: never affects the pixels."""

    def __init__(self, index: int, requested: int, used: int, clipped: bool,
                 behind: tuple[int, int, int], color: tuple[int, int, int, int],
                 shortened: bool = False):
        self.index, self.requested, self.used, self.clipped = index, requested, used, clipped
        self.behind, self.color, self.shortened = behind, color, shortened


def _ellipsize(text: str, font, bw: int) -> str:
    """Longest prefix of text, plus an ellipsis, whose width fits bw (binary
    search: about log2(500) measurements, never one per character)."""
    probe = ImageDraw.Draw(Image.new("L", (1, 1)))

    def fits(n: int) -> bool:
        left, _, right, _ = probe.textbbox((0, 0), text[:n].rstrip() + ELLIPSIS, font=font)
        return right - left <= bw

    lo, hi = 0, len(text)
    while lo < hi:
        mid = (lo + hi + 1) // 2
        if fits(mid):
            lo = mid
        else:
            hi = mid - 1
    return text[:lo].rstrip() + ELLIPSIS


MAX_ELLIPSIS_LINES = 50


def _ellipsize_block(text: str, font, bw: int, bh: int, align: str) -> str:
    """Fit a (possibly multi-line) text in the box: shorten each line that is
    too wide, then drop lines from the end until the block is short enough,
    marking the last kept line with an ellipsis. Bounded: at most
    MAX_ELLIPSIS_LINES lines, each shortened by binary search."""
    probe = ImageDraw.Draw(Image.new("L", (1, 1)))
    lines = text.split("\n")[:MAX_ELLIPSIS_LINES]

    def width(line: str) -> int:
        left, _, right, _ = probe.textbbox((0, 0), line, font=font)
        return right - left

    lines = [line if width(line) <= bw else _ellipsize(line, font, bw) for line in lines]

    def height(block: list[str]) -> int:
        _, top, _, bottom = probe.textbbox((0, 0), "\n".join(block), font=font, align=align)
        return bottom - top

    if height(lines) > bh:
        while len(lines) > 1 and height(lines) > bh:
            lines.pop()
        last = lines[-1]
        if not last.endswith(ELLIPSIS):
            last = last.rstrip() + ELLIPSIS
            lines[-1] = last if width(last) <= bw else _ellipsize(last[:-1], font, bw)
    return "\n".join(lines)


def _floor_px(layer: dict[str, Any], px: int, height: int) -> int:
    if "min_size" in layer:
        return max(MIN_FONT_PX, min(px, round(layer["min_size"] * height)))
    # Ellipsis without a floor keeps the set size; shrink goes as small as it must.
    return px if layer.get("overflow") == "ellipsis" else MIN_FONT_PX


def _layer_text(layer: dict[str, Any], key: str, values: dict[str, Any], missing: list[str],
                hidden: list[tuple[int, list[str]]] | None, index: int, limit) -> str | None:
    """The substituted text, or None if the layer hides itself because a
    variable in it is empty (hide_if_empty)."""
    empty: list[str] = []
    text = substitute(layer[key], values, empty, limit=limit)
    missing.extend(empty)
    if empty and layer.get("hide_if_empty"):
        if hidden is not None:
            hidden.append((index, empty))
        return None
    return text


def _draw_text(img: Image.Image, session: _Session, layer: dict[str, Any],
               values: dict[str, Any], missing: list[str],
               fits: list[_TextFit] | None = None, index: int = 0,
               hidden: list[tuple[int, list[str]]] | None = None) -> None:
    text = _layer_text(layer, "text", values, missing, hidden, index, MAX_TEXT)
    if text is None or not text.strip():
        return
    bx, by, bw, bh = _box_px(layer["box"], img.size)
    px = max(MIN_FONT_PX, round(layer["size"] * img.height))
    align = layer.get("align", "center")
    f, (left, top, width, height) = _fit_font(session, text, px, bw, bh,
                                              _floor_px(layer, px, img.height), align)
    shortened = False
    if layer.get("overflow") == "ellipsis" and (width > bw or height > bh):
        text, shortened = _ellipsize_block(text, f, bw, bh, align), True
        left, top, right, bottom = ImageDraw.Draw(Image.new("L", (1, 1))).textbbox(
            (0, 0), text, font=f, align=align)
        width, height = right - left, bottom - top
    color = _rgba(layer.get("color"), (255, 255, 255, 255))
    if fits is not None:
        # A 16x16 box-filtered sample: the mean colour behind the text at a
        # fraction of the cost of converting the whole box.
        sample = img.crop((bx, by, bx + bw, by + bh)).resize((16, 16), Image.Resampling.BOX)
        behind = ImageStat.Stat(sample.convert("RGB")).mean
        fits.append(_TextFit(index, px, round(f.size), width > bw or height > bh,
                             tuple(round(c) for c in behind), color, shortened))
    x = 0 if align == "left" else bw - width if align == "right" else (bw - width) // 2
    y = (bh - height) // 2
    # Draw into a box-sized layer: bounded memory, and nothing spills outside the box.
    box_layer = Image.new("RGBA", (bw, bh), (0, 0, 0, 0))
    # align applies line by line inside a multi-line block (Pillow's
    # default is left); x above places the block itself.
    ImageDraw.Draw(box_layer).text((x - left, y - top), text, font=f, fill=color, align=align)
    img.alpha_composite(box_layer, (bx, by))


def _draw_qr(img: Image.Image, layer: dict[str, Any], values: dict[str, Any], missing: list[str],
             index: int = 0, hidden: list[tuple[int, list[str]]] | None = None) -> None:
    data = _layer_text(layer, "data", values, missing, hidden, index, None)
    if not data:
        return
    if len(data) > MAX_QR:
        # Never truncate: a shortened QR code would silently point somewhere else.
        raise TemplateError([f"qr data is {len(data)} characters after substitution; the limit is {MAX_QR}"])
    qr = qrcode.QRCode(error_correction=qrcode.constants.ERROR_CORRECT_M, box_size=1, border=2)
    qr.add_data(data.encode("utf-8", "replace"))
    try:
        qr.make(fit=True)
    except (qrcode.exceptions.DataOverflowError, ValueError) as e:
        raise TemplateError([f"qr data is too long to encode ({len(data)} characters)"]) from e
    dark = _rgba(layer.get("color"), (0, 0, 0, 255))
    light = _rgba(layer.get("background"), (255, 255, 255, 255))
    matrix = qr.get_matrix()  # includes the quiet-zone border, which scanners need
    modules = len(matrix)
    bx, by, bw, bh = _box_px(layer["box"], img.size)
    side = min(bw, bh) // modules * modules  # whole pixels per module keeps edges crisp
    if side <= 0:
        return
    code = Image.new("RGBA", (modules, modules), light)
    code.putdata([dark if cell else light for row in matrix for cell in row])
    code = code.resize((side, side), Image.Resampling.NEAREST)
    img.alpha_composite(code, (bx + (bw - side) // 2, by + (bh - side) // 2))


def _draw_image(img: Image.Image, session: _Session, layer: dict[str, Any]) -> None:
    src = session.asset(layer["asset"])
    bx, by, bw, bh = _box_px(layer["box"], img.size)
    scale = min(bw / src.width, bh / src.height)
    size = (max(1, round(src.width * scale)), max(1, round(src.height * scale)))
    fitted = src.resize(size, Image.Resampling.LANCZOS)
    img.alpha_composite(fitted, (bx + (bw - fitted.width) // 2, by + (bh - fitted.height) // 2))


def _draw_panel(img: Image.Image, layer: dict[str, Any]) -> None:
    """A filled, optionally rounded and translucent rectangle: a backdrop that
    keeps text readable over a busy background."""
    bx, by, bw, bh = _box_px(layer["box"], img.size)
    r, g, b, a = _rgba(layer.get("color"), (0, 0, 0, 255))
    a = round(a * layer.get("opacity", 1))
    if a == 0:
        return
    shape = Image.new("RGBA", (bw, bh), (0, 0, 0, 0))
    radius = round(min(bw, bh) * layer.get("radius", 0))
    ImageDraw.Draw(shape).rounded_rectangle((0, 0, bw - 1, bh - 1), radius=radius, fill=(r, g, b, a))
    img.alpha_composite(shape, (bx, by))


def _flatten(img: Image.Image) -> Image.Image:
    """Transparent areas render black: a defined result for the delivered PNG."""
    base = Image.new("RGBA", img.size, (0, 0, 0, 255))
    base.alpha_composite(img)
    return base.convert("RGB")


def render_with_report(template: dict[str, Any], values: dict[str, Any],
                       assets: AssetResolver) -> tuple[Image.Image, list[str]]:
    """Render and also return the variable paths that had no printable value.

    Raises only TemplateError, whatever the template, values or assets contain."""
    img, missing, _, _ = _render(template, values, assets)
    return img, missing


def _render(template: dict[str, Any], values: dict[str, Any], assets: AssetResolver,
            fits: list[_TextFit] | None = None, hidden: list[tuple[int, list[str]]] | None = None):
    problems = validate(template)
    if problems:
        raise TemplateError(problems)
    template, values = resolve(template, values)
    session = _Session(assets)
    missing: list[str] = []
    try:
        img = _canvas(template, session)
        for index, layer in enumerate(template.get("layers", [])):
            kind = layer["type"]
            if kind == "text":
                _draw_text(img, session, layer, values, missing, fits, index, hidden)
            elif kind == "qr":
                _draw_qr(img, layer, values, missing, index, hidden)
            elif kind == "panel":
                _draw_panel(img, layer)
            else:
                _draw_image(img, session, layer)
        return _flatten(img), missing, fits or [], hidden or []
    except TemplateError:
        raise
    except (ValueError, TypeError, OverflowError, UnicodeError, OSError, MemoryError, RecursionError) as e:
        # Logged with its traceback so a genuine bug is not disguised as bad input.
        logger.exception("wallrender: render failed")
        raise TemplateError([f"render failed: {type(e).__name__}: {e}"]) from e


def render(template: dict[str, Any], values: dict[str, Any], assets: AssetResolver) -> Image.Image:
    """Render a template with device values into an RGB image ready to deliver."""
    return render_with_report(template, values, assets)[0]


def _missing_glyphs(session: _Session, text: str, notdef: bytes) -> list[str]:
    def pixels(ch: str) -> bytes:
        img = Image.new("L", (96, 96), 0)
        ImageDraw.Draw(img).text((16, 16), ch, font=session.font(48), fill=255)
        return img.tobytes()

    return sorted({ch for ch in set(text) if not ch.isspace() and pixels(ch) == notdef})


SHRINK_WARNING = 0.5  # warn when text had to drop below half its set size
LARGE_TEXT = 0.03  # of canvas height: WCAG's large-text threshold applies


def _luminance(rgb: tuple[int, int, int]) -> float:
    def channel(c: int) -> float:
        c = c / 255
        return c / 12.92 if c <= 0.04045 else ((c + 0.055) / 1.055) ** 2.4

    r, g, b = (channel(c) for c in rgb[:3])
    return 0.2126 * r + 0.7152 * g + 0.0722 * b


def contrast_ratio(a: tuple[int, int, int], b: tuple[int, int, int]) -> float:
    """WCAG 2 contrast ratio, 1 to 21."""
    la, lb = sorted((_luminance(a), _luminance(b)), reverse=True)
    return (la + 0.05) / (lb + 0.05)


def _over(fg: tuple[int, int, int, int], bg: tuple[int, int, int]) -> tuple[int, int, int]:
    alpha = fg[3] / 255
    return tuple(round(f * alpha + b * (1 - alpha)) for f, b in zip(fg[:3], bg))


def _fit_warnings(fits: list[_TextFit], height: int) -> list[str]:
    warnings = []
    for fit in fits:
        where = f"layer {fit.index}"
        if fit.clipped:
            warnings.append(f"{where}: text does not fit its box even at {fit.used}px; it is cut off")
        elif fit.shortened:
            warnings.append(f"{where}: text shortened with \u2026 to fit its box")
        elif fit.used < fit.requested * SHRINK_WARNING:
            warnings.append(f"{where}: text shrank from {fit.requested}px to {fit.used}px to fit its box")
        ratio = contrast_ratio(_over(fit.color, fit.behind), fit.behind)
        needed = 3.0 if fit.used >= LARGE_TEXT * height else 4.5
        if ratio < needed:
            warnings.append(f"{where}: low contrast {ratio:.1f}:1 against what is behind it "
                            f"(WCAG asks for {needed:g}:1)")
    return warnings


def render_with_lint(template: dict[str, Any], values: dict[str, Any],
                     assets: AssetResolver) -> tuple[Image.Image, list[str]]:
    """The rendered image and lint's warnings from one render, for callers
    that want both (raises TemplateError like render)."""
    img, missing, fits, hidden = _render(template, values, assets, fits=[], hidden=[])
    return img, _lint_warnings(template, values, assets, img, missing, fits, hidden)


def lint(template: dict[str, Any], values: dict[str, Any], assets: AssetResolver) -> list[str]:
    """Warnings a designer should see: invalid template, missing values, missing
    glyphs, text that shrank or is cut off, and low text contrast (WCAG)."""
    problems = validate(template)
    if problems:
        return problems
    try:
        img, missing, fits, hidden = _render(template, values, assets, fits=[], hidden=[])
    except TemplateError as e:
        return e.problems
    return _lint_warnings(template, values, assets, img, missing, fits, hidden)


def _lint_warnings(template, values, assets, img, missing, fits, hidden) -> list[str]:
    warnings: list[str] = []
    if "roles" in template:
        variant, _ = choose(template, values)
        raw = values.get("role")
        if variant == "default":
            warnings.append(f"role {str(raw)!r} has no variant of its own; it uses the default")
        elif variant == "empty":
            warnings.append("no role value; the empty variant is used")
    hidden_paths = {path for _, paths in hidden for path in paths}
    for index, paths in hidden:
        names = ", ".join(f"{{{{{p}}}}}" for p in dict.fromkeys(paths))
        warnings.append(f"layer {index}: hidden because {names} has no value")
    for path in sorted(set(missing) - hidden_paths):
        warnings.append(f"no value for {{{{{path}}}}}; it renders empty")
    warnings.extend(_fit_warnings(fits, img.height))
    session = _Session(assets)
    notdef_img = Image.new("L", (96, 96), 0)
    ImageDraw.Draw(notdef_img).text((16, 16), "\U0010FFFD", font=session.font(48), fill=255)
    notdef = notdef_img.tobytes()  # the fallback box: a code point no font covers
    _, resolved = resolve(template, values)  # role.* text comes from the variant
    for i, layer in enumerate(template.get("layers", [])):
        if layer["type"] == "text":
            for ch in _missing_glyphs(session, substitute(layer["text"], resolved), notdef):
                warnings.append(f"layer {i}: the font has no glyph for {ch!r} ({ch}); it will show as a box")
    return warnings
