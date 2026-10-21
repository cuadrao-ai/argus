#!/usr/bin/env python3
"""Builds the outlined wordmark and the mark-and-wordmark lockups in brand/.

The wordmark is "cuadrao" in Space Grotesk 700 with letter-spacing -0.085em, the
exact styling of `.wordmark` in components/business.module.css. Glyph outlines come
from the bundled variable font (app/fonts/SpaceGrotesk[wght].woff2) instanced at
wght 700; positions come from HarfBuzz shaping, which is what the browser uses.
Needs: pip install fonttools brotli uharfbuzz. Run from marketing/: python3 scripts/make-brand-assets.py
"""
import io
import re
from pathlib import Path

import uharfbuzz as hb
from fontTools.pens.boundsPen import BoundsPen
from fontTools.pens.svgPathPen import SVGPathPen
from fontTools.pens.transformPen import TransformPen
from fontTools.ttLib import TTFont
from fontTools.varLib import instancer

ROOT = Path(__file__).resolve().parent.parent
TEXT = "cuadrao"
TRACKING = -85  # -0.085em in a 1000-unit em
INK, PAPER = "#172b26", "#fafbf8"
GAP = 250  # between the mark and the wordmark, in wordmark units (1 em = 1000)
MARK_HEIGHT = 1000
# Intrinsic size of the lockups, so a tool that sizes an SVG by its root attributes (Xcode's
# asset compiler) does not rasterize it at viewBox size. The art scales freely.
LOCKUP_WIDTH = 268
WORDMARK_WIDTH = 200
# Bounds of the mark's three shapes inside its 64-unit grid (see brand/cuadrao-mark-light.svg).
MARK_X0, MARK_Y0, MARK_W, MARK_H = 3.897, 8.0, 56.203, 48.0

font = TTFont(ROOT / "app/fonts/SpaceGrotesk[wght].woff2")
font = instancer.instantiateVariableFont(font, {"wght": 700})
font.flavor = None
buffer = io.BytesIO()
font.save(buffer)
shaper = hb.Font(hb.Face(buffer.getvalue()))
text = hb.Buffer()
text.add_str(TEXT)
text.guess_segment_properties()
hb.shape(shaper, text, {"kern": True})

glyphs = font.getGlyphSet()
pen_x, parts, ink = 0.0, [], [1e9, 1e9, -1e9, -1e9]
for info, position in zip(text.glyph_infos, text.glyph_positions):
    name = font.getGlyphName(info.codepoint)
    path = SVGPathPen(glyphs, ntos=lambda v: f"{v:.1f}".rstrip("0").rstrip("."))
    glyphs[name].draw(TransformPen(path, (1, 0, 0, -1, pen_x + position.x_offset, 0)))
    parts.append(path.getCommands())
    box = BoundsPen(glyphs)
    glyphs[name].draw(box)
    x0, y0, x1, y1 = box.bounds
    ink = [min(ink[0], pen_x + x0), min(ink[1], -y1), max(ink[2], pen_x + x1), max(ink[3], -y0)]
    pen_x += position.x_advance + TRACKING
word_path = "".join(parts)
d_box = BoundsPen(glyphs)
glyphs["d"].draw(d_box)
d_top = d_box.bounds[3]  # top of the d, the tallest letter

def fmt(value: float) -> str:
    return f"{value:.1f}".rstrip("0").rstrip(".")

def wordmark_svg(fill: str) -> str:
    x0, y0, x1, y1 = ink
    return (
        f'<svg xmlns="http://www.w3.org/2000/svg" width="{WORDMARK_WIDTH}" height="{WORDMARK_WIDTH * (y1 - y0) / (x1 - x0):.2f}" viewBox="{fmt(x0)} {fmt(y0)} {fmt(x1 - x0)} {fmt(y1 - y0)}">'
        f'<path fill="{fill}" d="{word_path}"/></svg>\n'
    )

def mark_inner(source: Path) -> str:
    svg = source.read_text()
    defs = re.search(r"<defs>.*?</defs>", svg, re.S).group(0)
    group = re.search(r'<g transform="translate\(6\.8 0\) skewX\(-12\)">.*?</g>', svg, re.S).group(0)
    return defs, group

def lockup_svg(mark_source: Path, fill: str) -> str:
    defs, group = mark_inner(mark_source)
    scale = MARK_HEIGHT / MARK_H
    mark_width = MARK_W * scale
    # The mark's vertical centre sits halfway between the baseline and the top of the d.
    centre = -d_top / 2
    top = centre - MARK_HEIGHT / 2
    word_x = mark_width + GAP - ink[0]
    left, right = 0.0, mark_width + GAP + (ink[2] - ink[0])
    bottom = max(centre + MARK_HEIGHT / 2, 0)
    top = min(top, ink[1])
    view_width, view_height = right - left, bottom - top
    return (
        f'<svg xmlns="http://www.w3.org/2000/svg" width="{LOCKUP_WIDTH}" height="{LOCKUP_WIDTH * view_height / view_width:.2f}" viewBox="{fmt(left)} {fmt(top)} {fmt(view_width)} {fmt(view_height)}">{defs}'
        f'<g transform="translate({fmt(-MARK_X0 * scale)} {fmt(centre - (MARK_Y0 + MARK_H / 2) * scale)}) scale({fmt(scale)})">{group}</g>'
        f'<path transform="translate({fmt(word_x)} 0)" fill="{fill}" d="{word_path}"/></svg>\n'
    )

brand = ROOT / "brand"
(brand / "cuadrao-wordmark.svg").write_text(wordmark_svg(INK))
(brand / "cuadrao-wordmark-dark.svg").write_text(wordmark_svg(PAPER))
(brand / "cuadrao-lockup-light.svg").write_text(lockup_svg(brand / "cuadrao-mark-light.svg", INK))
(brand / "cuadrao-lockup-dark.svg").write_text(lockup_svg(brand / "cuadrao-mark-dark.svg", PAPER))
print("ink bounds", [round(v, 1) for v in ink], "d top", d_top)
