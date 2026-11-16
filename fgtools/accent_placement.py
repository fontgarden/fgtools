#!/usr/bin/env python3
"""Measure where accent marks sit on their base letters.

    fgtools check-accents [--master NAME] [--tolerance UNITS] [--all]
    fgtools evaluate-accent-placement [FONT.ttf ...] [--letters]

An accented letter is a composite: a base letter and one or more marks, for
example Aacute = A + acute. Unicode gives the parts. The position of a mark
has two parts that this module predicts from the outlines:

    horizontal   the mark is centered on a reference x of the base
    vertical     the mark keeps its drawn height over a reference line of
                 the base: the x-height, the cap height or the ascender

The offset of a mark is then `reference of the base + a constant of the
mark`. The constant is not known in advance. It is the median over the other
letters that use the same mark, so a font is measured against itself.

`evaluate-accent-placement` tests the rules on compiled fonts, where the
designer's positions are known: each letter is predicted from the other
letters, and the error is the distance from the designer's position.

`check-accents` applies the same prediction to the composites of the
project and lists the ones that differ from it. It also lists a composite
whose position differs from the anchors of its parts. It does not change
the sources.
"""
from __future__ import annotations

import argparse
import statistics
import sys
import unicodedata
from collections import defaultdict
from pathlib import Path

from fontTools.pens.basePen import BasePen

from fgtools import project

# Combining mark: (side, code point of the spacing form). Fonts build
# composites from either form.
MARKS = {
    0x0300: ('top', 0x0060), 0x0301: ('top', 0x00B4), 0x0302: ('top', 0x02C6),
    0x0303: ('top', 0x02DC), 0x0304: ('top', 0x00AF), 0x0306: ('top', 0x02D8),
    0x0307: ('top', 0x02D9), 0x0308: ('top', 0x00A8), 0x030A: ('top', 0x02DA),
    0x030B: ('top', 0x02DD), 0x030C: ('top', 0x02C7),
    0x0323: ('bottom', None), 0x0326: ('bottom', None),
    0x0327: ('bottom', 0x00B8), 0x0328: ('bottom', 0x02DB),
}
DOTLESS = {'i': 'ı', 'j': 'ȷ'}
# On these letters the caron is drawn as an apostrophe to the right of the ascender.
CARON_BESIDE = 'dtlL'
# The share of the height of a base that counts as its top or bottom.
BAND = 0.15
# A base within this share of the em of a metric line uses that line.
LINE_TOLERANCE = 0.04


class Flatten(BasePen):
    """Collect the outline of a glyph as line segments."""

    def __init__(self, glyph_set):
        super().__init__(glyph_set)
        self.segments = []
        self.contours = []                    # the points of each contour, for drawing
        self.start = self.point = None

    def _moveTo(self, point):
        self.start = self.point = point
        self.contours.append([point])

    def _lineTo(self, point):
        self.segments.append((self.point, point))
        self.contours[-1].append(point)
        self.point = point

    def _curveToOne(self, one, two, three):
        zero, previous = self.point, self.point
        for step in range(1, 9):
            t = step / 8
            a, b, c, d = (1 - t) ** 3, 3 * t * (1 - t) ** 2, 3 * t * t * (1 - t), t ** 3
            point = (a * zero[0] + b * one[0] + c * two[0] + d * three[0],
                     a * zero[1] + b * one[1] + c * two[1] + d * three[1])
            self.segments.append((previous, point))
            self.contours[-1].append(point)
            previous = point
        self.point = three

    def _closePath(self):
        if self.point != self.start:
            self.segments.append((self.point, self.start))
        self.point = self.start


class Shape:
    """The flattened outline of one glyph."""

    def __init__(self, segments, advance, contours=()):
        self.segments = segments
        self.advance = advance
        self.contours = contours
        points = [point for segment in segments for point in segment]
        self.empty = not points
        if not self.empty:
            self.left = min(x for x, _ in points)
            self.right = max(x for x, _ in points)
            self.bottom = min(y for _, y in points)
            self.top = max(y for _, y in points)

    def span(self, low, high):
        """The horizontal extent of the ink between two heights."""
        found = []
        for (x0, y0), (x1, y1) in self.segments:
            if max(y0, y1) < low or min(y0, y1) > high:
                continue
            for y in (max(low, min(y0, y1)), min(high, max(y0, y1))):
                found.append(x0 if y1 == y0 else x0 + (x1 - x0) * (y - y0) / (y1 - y0))
        return (min(found), max(found)) if found else (self.left, self.right)


class Font:
    """Glyph outlines, code points and composites of a UFO or a compiled font."""

    def __init__(self, glyph_set, code_points, advances, components, units_per_em, anchors=None,
                 mark_colors=None):
        self.glyph_set = glyph_set
        self.code_points = code_points        # glyph name: code point
        self.names = {value: name for name, value in code_points.items()}
        self.advances = advances
        self.components = components          # glyph name: [(base, dx, dy)]
        self.units_per_em = units_per_em
        self.anchors = anchors or {}          # glyph name: {anchor: (x, y)}
        self.mark_colors = mark_colors or {}  # glyph name: the public.markColor value
        self.shapes = {}
        self.lines = [self.shape(name).top for name in map(self.names.get, map(ord, 'xHl'))
                      if name and not self.shape(name).empty]

    @classmethod
    def from_compiled(cls, path, weight=None):
        """A compiled font. With `weight`, a variable font is read at that
        value of its weight axis, limited to the range of the axis."""
        from fontTools.ttLib import TTFont
        font = TTFont(path)
        if 'glyf' not in font:
            raise ValueError(f'{path}: no glyf table')
        if weight is not None and 'fvar' in font:
            from fontTools.varLib.instancer import instantiateVariableFont
            location = {axis.axisTag: axis.defaultValue for axis in font['fvar'].axes}
            for axis in font['fvar'].axes:
                if axis.axisTag == 'wght':
                    location['wght'] = min(max(weight, axis.minValue), axis.maxValue)
            font = instantiateVariableFont(font, location)
        glyf, components = font['glyf'], {}
        for name in font.getGlyphOrder():
            glyph = glyf[name]
            if glyph.isComposite():
                # A scaled or rotated component is not a plain accent.
                if all(not hasattr(part, 'transform') for part in glyph.components):
                    components[name] = [(part.glyphName, part.x, part.y) for part in glyph.components]
        code_points = {name: value for value, name in sorted(font.getBestCmap().items(), reverse=True)}
        advances = {name: metric[0] for name, metric in font['hmtx'].metrics.items()}
        return cls(font.getGlyphSet(), code_points, advances, components, font['head'].unitsPerEm)

    @classmethod
    def from_ufo(cls, path):
        import plistlib
        import xml.etree.ElementTree as ET
        from fontTools.ufoLib.glifLib import GlyphSet
        path = Path(path)
        glyph_set = GlyphSet(str(path / 'glyphs'), validateRead=False)
        code_points, advances, components, anchors, mark_colors = {}, {}, {}, {}, {}
        for name, file_name in glyph_set.contents.items():
            root = ET.parse(path / 'glyphs' / file_name).getroot()
            unicode = root.find('unicode')
            if unicode is not None:
                code_points[name] = int(unicode.get('hex'), 16)
            advance = root.find('advance')
            advances[name] = float(advance.get('width', 0)) if advance is not None else 0
            anchors[name] = {anchor.get('name'): (float(anchor.get('x')), float(anchor.get('y')))
                             for anchor in root.findall('anchor') if anchor.get('name')}
            entries = list(root.find('lib/dict')) if root.find('lib/dict') is not None else []
            for key, value in zip(entries, entries[1:]):
                if key.tag == 'key' and key.text == 'public.markColor':
                    mark_colors[name] = value.text
            parts = root.findall('outline/component')
            # A scaled or rotated component is not a plain accent.
            plain = all(float(part.get(key, default)) == default
                        for part in parts
                        for key, default in (('xScale', 1), ('yScale', 1), ('xyScale', 0), ('yxScale', 0)))
            if parts and plain and root.find('outline/contour') is None:
                components[name] = [(part.get('base'), float(part.get('xOffset', 0)),
                                     float(part.get('yOffset', 0))) for part in parts]
        units_per_em = 1000
        if (path / 'fontinfo.plist').is_file():
            with open(path / 'fontinfo.plist', 'rb') as file:
                units_per_em = plistlib.load(file).get('unitsPerEm', units_per_em)
        return cls(glyph_set, code_points, advances, components, units_per_em, anchors, mark_colors)

    def shape(self, name):
        if name not in self.shapes:
            pen = Flatten(self.glyph_set)
            self.glyph_set[name].draw(pen)
            self.shapes[name] = Shape(pen.segments, self.advances.get(name, 0), pen.contours)
        return self.shapes[name]

    def accents(self):
        """The accented letters: (glyph, base glyph, [(mark glyph, side, dx, dy)])."""
        for name, parts in self.components.items():
            code_point = self.code_points.get(name)
            if code_point is None or len(parts) < 2:
                continue
            base_character, *marks = unicodedata.normalize('NFD', chr(code_point))
            if not unicodedata.name(base_character, '').startswith('LATIN'):
                continue                  # the rules are for Latin; Greek tonos and Cyrillic differ
            if base_character in CARON_BESIDE and marks == ['\u030c']:
                continue                  # this caron is an apostrophe form beside the letter
            if not marks or any(ord(mark) not in MARKS for mark in marks) \
                    or len(marks) != len(parts) - 1:
                continue
            (base, base_x, base_y), *others = parts
            allowed = {ord(base_character), ord(DOTLESS.get(base_character, base_character))}
            if self.code_points.get(base) not in allowed or self.shape(base).empty:
                continue
            # The components can be in any order, so match each mark by its code points.
            found, unused = [], list(others)
            for mark in marks:
                side, spacing = MARKS[ord(mark)]
                match = next((part for part in unused
                              if self.code_points.get(part[0]) in (ord(mark), spacing)), None)
                if match is None and len(unused) == 1:
                    match = unused[0]         # for example acute.case, which has no code point
                if match is None or self.shape(match[0]).empty:
                    break
                unused.remove(match)
                found.append((match[0], side, match[1] - base_x, match[2] - base_y))
            else:
                yield name, base, found

    def reference_x(self, base, side, rule):
        shape = self.shape(base)
        if rule == 'advance':
            return shape.advance / 2
        if rule == 'band':
            height = (shape.top - shape.bottom) * BAND
            low, high = ((shape.top - height, shape.top) if side == 'top'
                         else (shape.bottom, shape.bottom + height))
            left, right = shape.span(low, high)
            return (left + right) / 2
        return (shape.left + shape.right) / 2

    def reference_y(self, base, side, rule):
        shape = self.shape(base)
        if side == 'bottom':
            return 0 if rule == 'line' and abs(shape.bottom) < LINE_TOLERANCE * self.units_per_em \
                else shape.bottom
        if rule == 'line' and self.lines:
            line = min(self.lines, key=lambda value: abs(value - shape.top))
            if abs(line - shape.top) < LINE_TOLERANCE * self.units_per_em:
                return line
        return shape.top


def observations(font):
    """One record for each mark of each accented letter with one mark."""
    for glyph, base, marks in font.accents():
        if len(marks) == 1:               # a second mark sits on the first, not on the base
            mark, side, dx, dy = marks[0]
            yield {'glyph': glyph, 'base': base, 'mark': mark, 'side': side, 'dx': dx, 'dy': dy}


def outline_position(font, row):
    """The offset of a mark from the outlines only."""
    mark, side = font.shape(row['mark']), row['side']
    x = font.reference_x(row['base'], side, 'band') - (mark.left + mark.right) / 2
    line = font.reference_y(row['base'], side, 'line')
    if side == 'bottom':
        return x, line
    # A mark is drawn over the x-height, or over the cap height for a cap form.
    tolerance = LINE_TOLERANCE * font.units_per_em
    drawn = max((value for value in font.lines if value <= mark.bottom + tolerance),
                default=min(font.lines, default=0))
    return x, line - drawn


def calibrated_position(font, row, others):
    """The outline rule, with the constant of the mark from the other letters
    of the same height that use the mark."""
    def constant(member):
        return (member['dx'] - font.reference_x(member['base'], member['side'], 'band'),
                member['dy'] - font.reference_y(member['base'], member['side'], 'line'))

    def height(member):
        return font.reference_y(member['base'], member['side'], 'line')

    same = [constant(member) for member in others
            if (member['mark'], member['side']) == (row['mark'], row['side'])
            and height(member) == height(row)]
    if len(same) < 2:
        return None
    return (font.reference_x(row['base'], row['side'], 'band') + statistics.median(x for x, _ in same),
            height(row) + statistics.median(y for _, y in same))


def anchor_position(font, row, others):
    """The offset from the anchors that the other composites imply.

    The offset of a mark is `anchor of the base - anchor of the mark`. The
    two anchors are fitted to the other composites with medians. The base
    must have another mark, and the mark another base.
    """
    side = row['side']
    members = [member for member in others if member['side'] == side]
    if not any(member['base'] == row['base'] and member is not row for member in members) \
            or not any(member['mark'] == row['mark'] and member is not row for member in members):
        return None
    result = []
    for axis, reference in (('dx', font.reference_x), ('dy', font.reference_y)):
        rule = 'band' if axis == 'dx' else 'line'
        base_anchor = {member['base']: reference(member['base'], side, rule) for member in members}
        mark_anchor = {}
        for _ in range(4):
            for mark in {member['mark'] for member in members}:
                mark_anchor[mark] = statistics.median(
                    base_anchor[member['base']] - member[axis]
                    for member in members if member['mark'] == mark)
            for base in base_anchor:
                base_anchor[base] = statistics.median(
                    member[axis] + mark_anchor[member['mark']]
                    for member in members if member['base'] == base)
        result.append(base_anchor[row['base']] - mark_anchor[row['mark']])
    return tuple(result)


METHODS = {
    'outlines': 'from the outlines only, for a font with no accented letters yet',
    'calibrated': 'outlines, with the constant of each mark from the other letters',
    'anchors': 'from the anchors that the other accented letters imply',
}


def predictions(font, method):
    """[(record, predicted dx, predicted dy)], each letter predicted without itself."""
    rows = list(observations(font))
    found = []
    for index, row in enumerate(rows):
        others = rows[:index] + rows[index + 1:]
        position = (outline_position(font, row) if method == 'outlines'
                    else calibrated_position(font, row, others) if method == 'calibrated'
                    else anchor_position(font, row, others))
        if position is not None:
            found.append((row, *position))
    return found


def share(values, limit):
    return sum(1 for value in values if value <= limit) / len(values) if values else 0.0


def errors(font, method):
    """[(record, error)], the larger of the horizontal and vertical error as a share of the em."""
    return [(row, max(abs(row['dx'] - x), abs(row['dy'] - y)) / font.units_per_em)
            for row, x, y in predictions(font, method)]


def evaluate(paths, letters=False):
    """Print the placement error of each method on compiled fonts."""
    fonts = []
    for path in paths:
        try:
            fonts.append((Path(path).name, Font.from_compiled(path)))
        except Exception as error:   # a font that fontTools cannot read is reported and left out
            print(f'{path}: {error}', file=sys.stderr)
    if not fonts:
        return 1
    print('The designer\'s position of each mark against the predicted position.')
    print('Each letter is predicted without itself. The error is the larger of the')
    print('horizontal and the vertical error.')
    print('exact: within 0.8% of the em (8 units of 1024). close: within 2%.\n')
    results = {method: {name: errors(font, method) for name, font in fonts} for method in METHODS}
    total = sum(len(list(observations(font))) for _, font in fonts)
    print(f'{len(fonts)} fonts, {total} marks\n')
    print('method       predicted   top exact  close   bottom exact  close')
    for method, text in METHODS.items():
        rows = [item for found in results[method].values() for item in found]
        top = [error for row, error in rows if row['side'] == 'top']
        bottom = [error for row, error in rows if row['side'] == 'bottom']
        print(f'{method:<12} {len(rows) / total:>9.1%} {share(top, 0.008):>11.1%} {share(top, 0.02):>6.1%}'
              f' {share(bottom, 0.008):>14.1%} {share(bottom, 0.02):>6.1%}   {text}')
    print('\nfont                          marks   ' + '   '.join(f'{method:>10}' for method in METHODS))
    for name, font in fonts:
        cells = [f'{share([error for _, error in results[method][name]], 0.008):>10.1%}'
                 for method in METHODS]
        print(f'{name[:28]:<28} {len(list(observations(font))):>6}   ' + '   '.join(cells))
    if letters:
        for key, title in (('base', 'base letter'), ('mark', 'mark')):
            print(f'\n{title}, method outlines: marks, exact, close (worst first)')
            groups = defaultdict(list)
            for name, font in fonts:
                for row, error in results['outlines'][name]:
                    label = chr(font.code_points[row['base']]) if key == 'base' else row['mark']
                    groups[label, row['side']].append(error)
            ranked = sorted(groups.items(), key=lambda item: share(item[1], 0.008))
            for (label, side), found in ranked:
                if len(found) >= 8:
                    print(f'  {label:<18} {side:<7} {len(found):>5} {share(found, 0.008):>6.1%}'
                          f' {share(found, 0.02):>6.1%}')
    return 0


def check(root=None, master=None, tolerance=8, show_all=False):
    """List the accented letters of the project whose mark is not where the
    other accented letters predict, or not where the anchors of its parts are."""
    layout = project.load(root)
    status = 0
    for name in [master] if master else layout.masters:
        font = Font.from_ufo(layout.ufo(name))
        rows = list(observations(font))
        findings, unpredicted, missing = [], 0, set()
        for row in rows:
            glyph, base, mark, side = row['glyph'], row['base'], row['mark'], row['side']
            notes, size = [], 0
            # The fit uses all letters. A median is not moved by one displaced mark.
            position = anchor_position(font, row, rows) or calibrated_position(font, row, rows)
            if position is None:
                unpredicted += 1
            else:
                error = (row['dx'] - position[0], row['dy'] - position[1])
                size = max(map(abs, error))
                if size > tolerance:
                    notes.append(f'{error[0]:+.0f}, {error[1]:+.0f} from the position that the '
                                 'other accented letters predict')
            anchor = font.anchors.get(base, {}).get(side)
            attach = font.anchors.get(mark, {}).get('_' + side)
            if anchor and attach:
                difference = (row['dx'] - (anchor[0] - attach[0]), row['dy'] - (anchor[1] - attach[1]))
                if max(map(abs, difference)) > 0:
                    size = max(size, *map(abs, difference))
                    notes.append(f'{difference[0]:+.0f}, {difference[1]:+.0f} from the `{side}` anchors')
            else:
                missing.add(f'{mark} `_{side}`' if anchor else f'{base} `{side}`')
            if notes or show_all:
                findings.append((size, glyph, mark, notes))
        print(f'{name}: {len(rows)} accented letters with one mark, {len(findings)} listed, '
              f'{unpredicted} without a prediction')
        for _, glyph, mark, notes in sorted(findings, key=lambda item: (-item[0], item[1])):
            print(f'  {glyph} ({mark}): ' + ('; '.join(notes) or 'as predicted'))
        if missing:
            print(f'  {len(missing)} anchors are missing: ' + ', '.join(sorted(missing)))
        status = status or (1 if any(notes for *_, notes in findings) else 0)
    return status


def main_check():
    parser = argparse.ArgumentParser(prog='fgtools check-accents', description=check.__doc__)
    parser.add_argument('--master', help='check one master (default: all)')
    parser.add_argument('--tolerance', type=float, default=8, help='font units (default: 8)')
    parser.add_argument('--all', action='store_true', help='also list the marks that are as predicted')
    args = parser.parse_args()
    return check(master=args.master, tolerance=args.tolerance, show_all=args.all)


def main_evaluate():
    parser = argparse.ArgumentParser(prog='fgtools evaluate-accent-placement',
                                     description=evaluate.__doc__)
    parser.add_argument('fonts', nargs='*',
                        help='compiled TTF fonts (default: the shared reference fonts)')
    parser.add_argument('--letters', action='store_true', help='also list the error for each base letter')
    args = parser.parse_args()
    from fgtools import reference_fonts
    return evaluate(args.fonts or reference_fonts.one_for_each_family(), args.letters)
