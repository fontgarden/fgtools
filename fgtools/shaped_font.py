"""Read a compiled font as HarfBuzz shapes it: glyph names, ink boxes and
positions of shaped text. The Fontspector checks of the profile use it."""
from __future__ import annotations

import io
import unicodedata

from fontTools import subset
from fontTools.pens.boundsPen import BoundsPen
from fontTools.pens.transformPen import TransformPen
from fontTools.ttLib import TTFont
import uharfbuzz as hb


class Instance:
    """One font at one weight: its tables, outlines and a HarfBuzz font."""

    def __init__(self, name, font, data, weight=None):
        self.font, self.weight = font, weight
        self.name = f'{name} at {weight:g}' if weight is not None else name
        self.cmap = font.getBestCmap()
        self.glyphs = font.getGlyphSet(location={'wght': weight} if weight is not None else None)
        self.shaper = hb.Font(hb.Face(data))
        if weight is not None:
            self.shaper.set_variations({'wght': weight})

    def bounds(self, name):
        pen = BoundsPen(self.glyphs)
        self.glyphs[name].draw(pen)
        return pen.bounds

    def shape(self, text, features=None):
        """Shape text; return (glyph name, ink box in text coordinates, position)."""
        buffer = hb.Buffer()
        buffer.add_str(text)
        buffer.guess_segment_properties()
        hb.shape(self.shaper, buffer, features or {})
        rows, x = [], 0
        for info, position in zip(buffer.glyph_infos, buffer.glyph_positions):
            name = self.font.getGlyphName(info.codepoint)
            pen = BoundsPen(self.glyphs)
            self.glyphs[name].draw(TransformPen(pen, (1, 0, 0, 1, x + position.x_offset, position.y_offset)))
            rows.append((name, pen.bounds, position))
            x += position.x_advance
        return rows


def weights(font):
    """The lowest, the middle and the highest weight of a variable font, or
    None for a font without a weight axis."""
    for axis in font['fvar'].axes if 'fvar' in font else ():
        if axis.axisTag == 'wght':
            return [axis.minValue, (axis.minValue + axis.maxValue) / 2, axis.maxValue]
    return [None]


def instances(path, data=None):
    """The font at each weight of `weights`."""
    data = data if data is not None else path.read_bytes()
    font = TTFont(io.BytesIO(data))
    return [Instance(path.name, font, data, weight) for weight in weights(font)]


def precomposed(cmap):
    """Encoded characters whose canonical decomposition is also encoded."""
    found = []
    for code in cmap:
        decomposed = unicodedata.normalize('NFD', chr(code))
        if decomposed != chr(code) and all(ord(c) in cmap for c in decomposed):
            found.append(code)
    return found


def without_precomposed(path):
    """The data of a subset of the font without its precomposed letters, as a
    web font subset can be. HarfBuzz then shapes their decomposed sequences."""
    font = TTFont(path)
    cmap = font.getBestCmap()
    options = subset.Options()
    options.layout_features = ['*']
    options.name_IDs = ['*']
    options.glyph_names = True
    options.notdef_outline = True
    options.drop_tables += ['meta']
    subsetter = subset.Subsetter(options=options)
    subsetter.populate(unicodes=set(cmap) - set(precomposed(cmap)))
    subsetter.subset(font)
    stream = io.BytesIO()
    font.save(stream)
    return stream.getvalue()


def union(boxes):
    boxes = [box for box in boxes if box]
    return (min(b[0] for b in boxes), min(b[1] for b in boxes),
            max(b[2] for b in boxes), max(b[3] for b in boxes))
