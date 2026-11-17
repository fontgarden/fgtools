"""The layout system of proofs and media: a lattice, a typesetter and a drawing as data.

A layout is not drawn by hand. It is placed on the lattice of the typeface:
the module is the large step of the design grid (64 units in a font with an
em of 1024), every position is a multiple of the unit (8 pixels), and type
sizes double, so that the cap height stands on a module line. The numbers are
in the `[layout]` block of CONTEXT.md of a project, and the defaults are the
same.

The parts:

- `lattice` gives a canvas its live area (a whole number of modules) and its
  text area (the live area less one module on each side, inside the safe area
  of the platform).
- `Type` measures text in the font with HarfBuzz: advance and ink, at any
  weight. It fits a word to a measure and breaks a paragraph into lines. The
  size never changes to make a text fit: the text is chosen to fit.
- `Sheet` is one drawing: pages of text, rules and paths at lattice positions.
  It checks each element when it is placed (size on the scale, position on
  the unit, ink inside the text area, characters in the font) and keeps the
  faults. A sheet with a fault is not published.
- `plot` writes the drawing as a text file, one element for each line, and
  DesignBot draws it with `media_plotter.rs`. The format scripts never touch
  pixels.
"""
from __future__ import annotations

import math
from pathlib import Path

DEFAULT_LAYOUT = {'unit': 8, 'module': 64, 'sizes': [32, 64, 128, 256, 512, 1024], 'label_size': 24}
# Gray levels on the same binary steps as the grid, and one accent of the brand.
PALETTE = {'ground': (32, 32, 32), 'grid': (64, 64, 64), 'secondary': (128, 128, 128), 'ink': (224, 224, 224),
           'accent': (232, 197, 71)}
# Paper: the print page has dark ink on a light ground.
LIGHT = {'ground': (240, 240, 240), 'grid': (192, 192, 192), 'secondary': (128, 128, 128), 'ink': (32, 32, 32),
         'accent': (208, 64, 32)}
RULE = 2            # pixels: the one line weight
LABEL_DROP = 16     # pixels from a module line to the cap top of a label


def lattice(canvas, layout=None):
    """The live area and the text area of a canvas, in modules and pixels."""
    layout = {**DEFAULT_LAYOUT, **(layout or {})}
    module, unit = layout['module'], layout['unit']
    width, height, safe = canvas['width'], canvas['height'], canvas.get('safe', {})

    def live(length):
        count = length // module
        while count > 2 and (count % 2 or length - count * module < 6 * unit):
            count -= 1
        return count, (length - count * module) // 2

    (cols, ox), (rows, oy) = live(width), live(height)

    def inside(count, origin, low, high):
        first = next(k for k in range(1, count) if origin + k * module >= low)
        last = next(k for k in range(count - 1, 0, -1) if origin + k * module <= high)
        return first, last - first

    col0, text_cols = inside(cols, ox, safe.get('left', 0), width - safe.get('right', 0))
    row0, text_rows = inside(rows, oy, safe.get('top', 0), height - safe.get('bottom', 0))
    return {'width': width, 'height': height, 'module': module, 'unit': unit, 'sizes': layout['sizes'],
            'label_size': layout['label_size'], 'origin': (ox, oy), 'live': (cols, rows),
            'text': (col0, row0, text_cols, text_rows), 'scale': canvas.get('scale', 1),
            'light': canvas.get('theme') == 'light'}


class Type:
    """The font of the project, measured with HarfBuzz."""

    def __init__(self, path, family, low, high, upm, cap, x_height, descender):
        import uharfbuzz as hb
        self.hb = hb
        self.path, self.family, self.low, self.high = Path(path), family, low, high
        self.upm, self.cap, self.x_height, self.descender = upm, cap, x_height, descender   # parts of the em
        self.face = hb.Face(hb.Blob.from_file_path(str(path)))
        self.font = hb.Font(self.face)
        self.characters = set(self.face.unicodes)
        self.cache = {}

    def covers(self, text):
        return bool(text) and all(ord(character) in self.characters for character in text)

    def measure(self, text, weight=None, features=()):
        """(advance, ink left, ink right) of a line of text, in parts of the em. The ink values are
        the distances from the origin to the first and the last ink."""
        weight = self.low if weight is None else weight
        key = (text, round(weight, 3), tuple(features))
        if key not in self.cache:
            hb = self.hb
            if self.high > self.low:
                self.font.set_variations({'wght': weight})
            buffer = hb.Buffer()
            buffer.add_str(text)
            buffer.guess_segment_properties()
            hb.shape(self.font, buffer, {tag: True for tag in features})
            x, left, right = 0, math.inf, -math.inf
            for info, position in zip(buffer.glyph_infos, buffer.glyph_positions):
                extents = self.font.get_glyph_extents(info.codepoint)
                if extents and extents.width:
                    start = x + position.x_offset + extents.x_bearing
                    left, right = min(left, start), max(right, start + extents.width)
                x += position.x_advance
            if left > right:
                left = right = 0
            self.cache[key] = (x / self.upm, left / self.upm, right / self.upm)
        return self.cache[key]

    def fit(self, words, measure, size, weight=None, used=(), least=0.9):
        """The text whose ink is nearest to the measure (pixels) without being wider, at this size.
        Words, and pairs of words when no single word is long enough. None when nothing fits."""
        target = measure / size

        def ink(text):
            _, left, right = self.measure(text, weight)
            return right - left

        words = [word for word in words if self.covers(word) and word not in used]
        best = max(((ink(word), word) for word in words if ink(word) <= target), default=(0, None))
        if best[0] < target * 0.97:
            space = self.measure(' ', weight)[0] if self.covers(' ') else 0
            if space:
                short = sorted(words, key=ink)
                for first in short:
                    rest = target - ink(first) - space
                    if rest <= 0:
                        break
                    second = max(((ink(word), word) for word in short if word != first and ink(word) <= rest),
                                 default=None)
                    if second:
                        text = f'{first} {second[1]}'
                        if text not in used and ink(text) <= target:
                            best = max(best, (ink(text), text))
        return best[1] if best[0] >= target * least else None

    def lines(self, text, measure, size, weight=None):
        """The paragraph in lines not wider than the measure (pixels), ragged right, without a last
        line shorter than half the measure where a narrower setting avoids it."""
        def broken(limit):
            found, line = [], ''
            for word in text.split():
                trial = f'{line} {word}'.strip()
                if line and self.measure(trial, weight)[0] * size > limit:
                    found.append(line)
                    line = word
                else:
                    line = trial
            return found + [line]

        result = broken(measure)
        for step in range(1, 13):
            if len(result) < 2 or self.measure(result[-1], weight)[0] * size >= measure / 2:
                break
            trial = broken(measure - 16 * step)
            if len(trial) == len(result):
                result = trial
        return result


class Sheet:
    """One drawing on the lattice of a canvas. Columns and rows count modules from the top left
    corner of the text area."""

    def __init__(self, grid, type_, colors=None, name=''):
        self.grid, self.type, self.name = grid, type_, name
        self.colors = dict(LIGHT) if grid.get('light') else {**PALETTE, **(colors or {})}
        self.cols, self.rows = grid['text'][2], grid['text'][3]
        self.pages, self.faults, self.axis = [], [], False

    # positions
    def x(self, col):
        return self.grid['origin'][0] + (self.grid['text'][0] + col) * self.grid['module']

    def y(self, row):
        return self.grid['origin'][1] + (self.grid['text'][1] + row) * self.grid['module']

    def fault(self, text):
        self.faults.append(f'{self.name} page {len(self.pages)}: {text}')

    def on_unit(self, x, y):
        """True when a point is on the unit grid of the lattice. The lattice starts at the corner of
        the live area, not at the corner of the canvas."""
        unit, (ox, oy) = self.grid['unit'], self.grid['origin']
        return all(abs(value / unit - round(value / unit)) < 1e-6 for value in (x - ox, y - oy))

    # elements
    def page(self, duration=0):
        self.pages.append({'duration': duration, 'items': [], 'sizes': set(), 'weights': set()})
        return self

    def add(self, *item):
        self.pages[-1]['items'].append(item)

    def text(self, text, col, row, size, weight=None, color='ink', optical=False, flush='left', drop=0,
             features=(), free=False):
        """Set a line with its cap top on the row line (plus `drop` pixels) and its start on the
        column line. `optical` puts the ink, not the origin, on the column line. `flush='right'`
        ends the line at the column line. Returns the advance in pixels, or 0 when the font cannot
        set the text."""
        type_ = self.type
        weight = type_.low if weight is None else weight
        if not type_.covers(text):
            return 0
        advance, left, right = (value * size for value in type_.measure(text, weight, features))
        if flush == 'right':
            origin = self.x(col) - (right if optical else advance)
        else:
            origin = self.x(col) - (left if optical else 0)
        top = self.y(row) + drop
        baseline = top + size * type_.cap
        page = self.pages[-1]
        page['sizes'].add(size)
        page['weights'].add(round(weight))
        if size not in self.grid['sizes'] and size != self.grid['label_size']:
            self.fault(f'the size {size:g} of "{text[:20]}" is not on the scale')
        if not free and not self.on_unit(self.x(col), top):
            self.fault(f'"{text[:20]}" is not on the unit of {self.grid["unit"]} pixels')
        if not free and (origin + left < self.x(0) - 1 or origin + right > self.x(self.cols) + 1
                         or top < self.y(0) - 1 or baseline > self.y(self.rows) + 1):
            self.fault(f'"{text[:20]}" at size {size:g} is outside the text area')
        self.add('text', origin, baseline, size, weight, self.colors[color], ','.join(features), text)
        return advance

    def label(self, text, col, row, color='secondary', flush='left', drop=LABEL_DROP, free=False):
        """A label: the one small size, with tabular figures, under the row line."""
        features = ('tnum',) if any(character.isdigit() for character in text) else ()
        return self.text(text, col, row, self.grid['label_size'], self.type.low, color, flush=flush,
                         drop=drop, features=features, free=free)

    def header(self, *fields, row=0):
        """A rule and a row of labels on fixed columns. The last field ends at the right edge."""
        self.rule(row)
        fields = [field for field in fields if field]
        for index, field in enumerate(fields):
            if index == len(fields) - 1 and index > 0:
                self.label(field, self.cols, row, flush='right')
            else:
                self.label(field, index * 4, row)

    def size(self, *values):
        """A size, or a size and its leading, as a label: pixels on a screen canvas, points on the print page."""
        scale = self.grid['scale']
        text = '/'.join(f'{value * scale:g}' for value in values)
        return text if len(values) > 1 else f'{text} {"px" if scale == 1 else "pt"}'

    @property
    def measure(self):
        """The width of the text area in pixels."""
        return self.cols * self.grid['module']

    def rule(self, row, col0=0, col1=None, color='grid', weight=RULE):
        y = self.y(row)
        self.add('line', self.x(col0), y, self.x(self.cols if col1 is None else col1), y, weight, self.colors[color])

    def line(self, x0, y0, x1, y1, color='grid', weight=RULE):
        self.add('line', x0, y0, x1, y1, weight, self.colors[color])

    def rect(self, x, y, width, height, color='ink'):
        self.add('rect', x, y, width, height, self.colors[color])

    def oval(self, x, y, width, height, color='ink'):
        self.add('oval', x, y, width, height, self.colors[color])

    def path(self, commands, color='ink', stroke=0):
        """A path of ('M', x, y), ('L', x, y), ('C', x1, y1, x2, y2, x, y) and ('Z',), in pixels."""
        self.add('path', stroke, self.colors[color], commands)

    def check(self):
        """The faults of the whole sheet: the rules that concern a page, not one element."""
        for index, page in enumerate(self.pages, 1):
            sizes = page['sizes'] - {self.grid['label_size']}
            if len(sizes) > 3:
                self.faults.append(f'{self.name} page {index}: {len(sizes)} type sizes; a picture has at most three')
            if len(page['weights']) > 2 and not self.axis:
                self.faults.append(f'{self.name} page {index}: {len(page["weights"])} weights; a picture has at '
                                   'most two, except when its subject is the weight axis')
        return self.faults


def plot(sheets, output, path):
    """Write the drawings as a plot file for media_plotter.rs. The plotter has its origin at the
    bottom left, so the heights are turned here. A canvas with a scale (the print page) is written
    at that scale."""
    first = sheets[0]
    scale, height = first.grid['scale'], first.grid['height']
    s = lambda value: f'{value * scale:.3f}'.rstrip('0').rstrip('.')
    up = lambda y: s(height - y)
    rgba = lambda color: '\t'.join(str(part) for part in (tuple(color) + (255,))[:4])
    type_ = first.type
    lines = [f'canvas\t{s(first.grid["width"])}\t{s(height)}',
             f'font\t{type_.path.resolve()}\t{type_.family}\t{int(type_.high > type_.low)}',
             f'output\t{Path(output).resolve()}']
    for sheet in sheets:
        ground = '\t'.join(str(part) for part in sheet.colors['ground'][:3])
        for page in sheet.pages:
            lines.append(f'page\t{page["duration"]:.6f}\t{ground}')
            for item in page['items']:
                kind = item[0]
                if kind == 'text':
                    _, x, baseline, size, weight, color, features, text = item
                    lines.append(f'text\t{s(x)}\t{up(baseline)}\t{s(size)}\t{weight:g}\t{rgba(color)}\t{features}\t{text}')
                elif kind == 'line':
                    _, x0, y0, x1, y1, weight, color = item
                    lines.append(f'line\t{s(x0)}\t{up(y0)}\t{s(x1)}\t{up(y1)}\t{s(weight)}\t{rgba(color)}')
                elif kind in ('rect', 'oval'):
                    _, x, y, width, tall, color = item
                    lines.append(f'{kind}\t{s(x)}\t{up(y + tall)}\t{s(width)}\t{s(tall)}\t{rgba(color)}')
                elif kind == 'path':
                    _, stroke, color, commands = item
                    d = ' '.join(c[0] + ' ' + ' '.join(f'{s(c[i])} {up(c[i + 1])}' for i in range(1, len(c), 2))
                                 if len(c) > 1 else c[0] for c in commands)
                    lines.append(f'path\t{s(stroke)}\t{rgba(color)}\t{d}')
    Path(path).write_text('\n'.join(lines) + '\n')
