"""The color of a glyph: how dark it is in text beside the other glyphs.

A designer judges the weight of a glyph in running text, from a distance: a
glyph that is too heavy is a dark spot, and a glyph that is too light is a
hole. This module gives a model the same two tests.

- `color` is a number. The fill of a glyph is its ink divided by the area of
  its ink box. The color is the fill of the glyph divided by the fill of a
  control letter of its script (H, he or alef). The same ratio in each font of
  `reference-fonts/` gives the range that readers know. A glyph of many
  crossing strokes, for example the number sign, has thinner strokes than H in
  every font, and the ratio shows it.
- `strip` is a picture: the glyph between control letters and in words, sharp
  and blurred. `fgtools render` draws it under the glyph.

The number is a filter, as every check: the picture and the designer decide.
"""
from __future__ import annotations

import sys

from fgtools import accent_proofs

# The control letter of each script, and the letters around the glyph in the
# strip. The Arabic letters do not join the next letter, so their isolated
# forms are correct without shaping.
CONTROL = {'Latin': 'H', 'Hebrew': 'ה', 'Arabic': 'ا'}
NEIGHBORS = {'Latin': 'noHO', 'Hebrew': 'הסםר', 'Arabic': 'ادرو'}
WORDS = {'Latin': ('Hamburgefonstiv', 'minimum', '204'),
         'Hebrew': ('שלום', 'עולם', 'אבג'),
         'Arabic': ('دار', 'ورد', 'زار')}
MEASURE_SCALE = 0.25    # pixels for one unit of a 1024-unit em
STRIP_SCALE = 0.085
BLUR = 60               # the radius of the blur of the strip, in units
TOLERANCE = 0.03        # a color this far outside the reference range is a finding


def script_of(name, code=None):
    if '-ar' in name or (code and 0x600 <= code <= 0x6FF):
        return 'Arabic'
    if '-hb' in name or (code and 0x590 <= code <= 0x5FF):
        return 'Hebrew'
    return 'Latin'


def fill(font, name):
    """Ink divided by the area of the ink box, or None for a glyph without ink."""
    shape = font.shape(name)
    points = [point for contour in shape.contours for point in contour]
    if not points:
        return None
    unit = 1024 / font.units_per_em * MEASURE_SCALE
    left, right = min(x for x, _ in points), max(x for x, _ in points)
    bottom, top = min(y for _, y in points), max(y for _, y in points)
    width, height = (right - left) * unit, (top - bottom) * unit
    if width < 2 or height < 2:
        return None
    coverage = accent_proofs.rasterize(shape, unit, 2 - left * unit, width=int(width) + 4,
                                       rows=int(height) + 4, baseline=int(top * unit) + 2, oversample=2)
    return float(coverage.sum()) / (width * height)


def color(font, name, script=None):
    """The fill of the glyph divided by the fill of the control letter, or None."""
    control = font.names.get(ord(CONTROL[script or script_of(name, font.code_points.get(name))]))
    if not control or name not in font.glyph_set:
        return None
    own, other = fill(font, name), fill(font, control)
    return own / other if own and other else None


def reference_fonts(layout, weight):
    """[(family, font)] of reference-fonts/, at the weight of a master."""
    from fgtools.accent_placement import Font
    folder, fonts = layout.root / 'reference-fonts', []
    if folder.is_dir():
        for path in accent_proofs.reference_paths(folder, weight):
            try:
                fonts.append((path.parent.name, Font.from_compiled(path, weight)))
            except Exception as error:      # a font that cannot be read is named and left out
                print(f'{path.name}: not read ({error})', file=sys.stderr)
    return fonts


def reference_colors(references, code, script):
    """{family: color} of the character in each reference font that has it."""
    found = {}
    for family, font in references:
        name = font.names.get(code)
        value = color(font, name, script) if name else None
        if value:
            found[family] = value
    return found


def compare(font, name, references):
    """(color, lowest, highest, count) against the reference fonts, or None
    when the glyph has no code point, or fewer than three fonts have it."""
    code = font.code_points.get(name)
    if code is None:
        return None
    script = script_of(name, code)
    own, others = color(font, name, script), reference_colors(references, code, script)
    if own is None or len(others) < 3:
        return None
    return own, min(others.values()), max(others.values()), len(others)


def finding(master, comparison):
    """A line for the design check when the color is outside the references."""
    own, low, high, count = comparison
    if low - TOLERANCE <= own <= high + TOLERANCE:
        return None
    word = 'darker' if own > high else 'lighter'
    return (f'{master}: color {own:.2f} of the control letter is {word} than in all {count} reference '
            f'fonts ({low:.2f} to {high:.2f}). Look at it in text.')


def sequence(font, name):
    """The glyph names of the strip: the glyph between the neighbors, then in words."""
    script = script_of(name, font.code_points.get(name))
    glyph = lambda character: font.names.get(ord(character))
    names = []
    for character in NEIGHBORS[script]:
        if glyph(character):
            names += [glyph(character), name, glyph(character), 'space']
    names += [name] * 3 + ['space']
    first, second, third = WORDS[script]
    for word in (first, None, second, None, third):
        names += [name, 'space'] if word is None else [glyph(c) for c in word if glyph(c)] + ['space']
    return names[::-1] if script != 'Latin' else names


def strip(font, name, top, bottom):
    """Two arrays of coverage, sharp and blurred: the glyph in a line of text."""
    import numpy
    from PIL import Image, ImageFilter
    unit = 1024 / font.units_per_em * STRIP_SCALE
    names = sequence(font, name)
    space = font.advances.get('space', font.units_per_em / 4)
    advance = lambda glyph: space if glyph == 'space' else font.advances.get(glyph, 0)
    margin = 24
    width = int(sum(advance(glyph) for glyph in names) * unit) + margin * 2
    rows = int((top - bottom) * unit) + margin
    baseline = int(top * unit) + margin // 2
    line = numpy.zeros((rows, width), dtype=numpy.float32)
    x = margin
    for glyph in names:
        if glyph != 'space' and glyph in font.glyph_set and not font.shape(glyph).empty:
            cell = int(advance(glyph) * unit) + 40
            ink = accent_proofs.rasterize(font.shape(glyph), unit, 20 + x % 1, width=cell, rows=rows,
                                          baseline=baseline)
            start = int(x) - 20
            lo, hi = max(start, 0), min(start + cell, width)
            line[:, lo:hi] = numpy.maximum(line[:, lo:hi], ink[:, lo - start:hi - start])
        x += advance(glyph) * unit
    blurred = Image.fromarray((line * 255).astype(numpy.uint8)).filter(ImageFilter.GaussianBlur(BLUR * unit))
    return line, numpy.asarray(blurred, dtype=numpy.float32) / 255
