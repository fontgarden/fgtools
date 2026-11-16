#!/usr/bin/env python3
"""Draw glyphs of the sources large, so that a person or a model can judge them.

    fgtools render "n alef-hb"                  both masters, to output/render/
    fgtools render "n" --master Bold
    fgtools render "b" --beside "o d"           with other glyphs of the project
    fgtools render "n" --base HEAD~3            compare with another revision
    fgtools render "n" --out FILE.png

One row is one glyph in one master. The columns are:

    change      the glyph at the base revision (default main) and now, in one
                picture: removed ink is red, added ink is green. The column
                is left out when the glyph did not change.
    now         the filled glyph
    points      the outline with its on-curve points (squares), its handles
                (dots) and the start point of each contour (circle)
    beside      each glyph of --beside, in the same master
    references  the same character in each family of reference-fonts/, at
                the weight of the master

Every cell has the same scale and the same baseline, and a reference font is
drawn at the same em size. The lines are the descender, the baseline, the
x-height, the cap height and the ascender of the master. The command does
not change the sources. Look at the picture before and after every edit.
"""
from __future__ import annotations

import argparse
import io
import plistlib
import subprocess
import sys
import tarfile
import tempfile
from pathlib import Path

from fgtools import accent_proofs, project
from fgtools.accent_placement import Font

BACKGROUND, CELL_FILL = (38, 38, 40), (46, 46, 49)
INK, REFERENCE_INK, GUIDE, TEXT = (226, 226, 220), (150, 150, 152), (74, 74, 78), (170, 170, 172)
REMOVED, ADDED, KEPT = (214, 88, 78), (96, 190, 120), (120, 120, 122)
ON_CURVE, OFF_CURVE, OUTLINE = (240, 200, 90), (120, 170, 230), (150, 150, 152)
SCALE = 0.42          # pixels for one unit of a 1024-unit em
MARGIN, CAPTION = 28, 40


class Points:
    """Record the points of the contours of a glyph, without its components."""

    def __init__(self):
        self.contours = []

    def beginPath(self, **_):
        self.contours.append([])

    def addPoint(self, point, segmentType=None, **_):
        self.contours[-1].append((point, segmentType))

    def endPath(self):
        pass

    def addComponent(self, *_, **__):
        pass


def base_ufo(root, ufo, revision, directory):
    """The glyphs of a UFO at a revision, written to `directory`, or None."""
    relative = ufo.relative_to(root).as_posix()
    archive = subprocess.run(['git', 'archive', revision, f'{relative}/glyphs', f'{relative}/fontinfo.plist'],
                             cwd=root, capture_output=True)
    if archive.returncode:
        return None
    tarfile.open(fileobj=io.BytesIO(archive.stdout)).extractall(directory, filter='data')
    return Path(directory) / relative


def metrics(ufo):
    with open(ufo / 'fontinfo.plist', 'rb') as file:
        info = plistlib.load(file)
    return [info.get(key, 0) for key in ('descender', 'xHeight', 'capHeight', 'ascender')] + [0]


def coverage(font, name, scale, width, height, baseline):
    shape = font.shape(name)
    origin = (width - shape.advance * scale) / 2
    return accent_proofs.rasterize(shape, scale, origin, width=width, rows=height, baseline=baseline), origin


def render(names, masters=None, beside=(), base='main', out=None, root=None):
    import numpy
    from PIL import Image, ImageDraw, ImageFont
    layout = project.load(root)
    weights = accent_proofs.master_weights(layout)
    small = ImageFont.load_default(13)
    colors = layout.design().get('colors', {}) if layout.design_config.exists() else {}

    def color_name(value):
        if not value:
            return 'no mark'
        numbers = [float(part) for part in value.split(',')]
        return next((name for name, entry in colors.items() if numbers in entry.get('rgba', [])), value)
    rows = []
    with tempfile.TemporaryDirectory(prefix='fgtools-render-') as temporary:
        for master in masters or layout.masters:
            ufo = layout.ufo(master)
            now = Font.from_ufo(ufo)
            old_path = base_ufo(layout.root, ufo, base, Path(temporary) / master)
            old = Font.from_ufo(old_path) if old_path else None
            references = []
            folder = layout.root / 'reference-fonts'
            if folder.is_dir():
                for path in accent_proofs.reference_paths(folder, weights[master]):
                    try:
                        references.append((path.parent.name, Font.from_compiled(path, weights[master])))
                    except Exception as error:      # a font that cannot be read is named and left out
                        print(f'{path.name}: not read ({error})', file=sys.stderr)
            lines = metrics(ufo)
            for name in names:
                if name not in now.glyph_set:
                    print(f'{master}: no glyph {name}', file=sys.stderr)
                    continue
                cells = []
                changed = (old is not None and name in old.glyph_set
                           and (old.shape(name).contours != now.shape(name).contours
                                or old.advances.get(name) != now.advances.get(name)))
                if changed:
                    cells.append(('change', f'{base} to now', (old, now), name, 1))
                cells.append(('fill', f'{name}  {master}', now, name, 1))
                cells.append(('points', f'advance {now.advances.get(name, 0):g}  '
                                        f'{color_name(now.mark_colors.get(name))}', now, name, 1))
                for other in beside:
                    if other in now.glyph_set:
                        cells.append(('fill', other, now, other, 1))
                code = now.code_points.get(name)
                for label, reference in references:
                    other = reference.names.get(code) if code is not None else None
                    if other and not reference.shape(other).empty:
                        cells.append(('reference', label, reference, other,
                                      now.units_per_em / reference.units_per_em))
                rows.append((lines, cells, ufo))
        if not rows:
            sys.exit('No glyph to draw.')
        top = max(max(lines) for lines, _, _ in rows)
        bottom = min(min(lines) for lines, _, _ in rows)
        height = round((top - bottom) * SCALE) + MARGIN * 2 + CAPTION
        baseline = CAPTION + MARGIN + round(top * SCALE)

        def cell_width(cell):
            font = cell[2][1] if cell[0] == 'change' else cell[2]
            return max(220, round(font.advances.get(cell[3], 0) * cell[4] * SCALE) + MARGIN * 2)

        width = max(sum(cell_width(cell) + 4 for cell in cells) for _, cells, _ in rows) + 4
        image = Image.new('RGB', (width, (height + 4) * len(rows) + 4), BACKGROUND)
        draw = ImageDraw.Draw(image)
        for line, (lines, cells, ufo) in enumerate(rows):
            y0, x0 = 4 + line * (height + 4), 4
            for kind, label, font, name, factor in cells:
                cell = cell_width((kind, label, font, name, factor))
                box = (x0, y0, x0 + cell, y0 + height)
                draw.rectangle(box, fill=CELL_FILL)
                for value in lines:
                    y = y0 + baseline - round(value * SCALE)
                    draw.line([(x0, y), (x0 + cell, y)], fill=GUIDE)
                draw.text((x0 + 8, y0 + 8), label[:38], fill=TEXT, font=small)
                scale = SCALE * factor
                under = numpy.asarray(image.crop(box), dtype=numpy.float32)
                if kind == 'change':
                    before, _ = coverage(font[0], name, scale, cell, height, baseline)
                    after, origin = coverage(font[1], name, scale, cell, height, baseline)
                    both = numpy.minimum(before, after)[..., None]
                    gone = numpy.clip(before - after, 0, 1)[..., None]
                    new = numpy.clip(after - before, 0, 1)[..., None]
                    pixels = (under * (1 - both - gone - new) + numpy.array(KEPT) * both
                              + numpy.array(REMOVED) * gone + numpy.array(ADDED) * new)
                    image.paste(Image.fromarray(numpy.clip(pixels, 0, 255).astype(numpy.uint8)), box)
                else:
                    ink, origin = coverage(font, name, scale, cell, height, baseline)
                    ink = ink[..., None] * (0.22 if kind == 'points' else 1)
                    color = numpy.array(REFERENCE_INK if kind == 'reference' else INK, dtype=numpy.float32)
                    image.paste(Image.fromarray((under * (1 - ink) + color * ink).astype(numpy.uint8)), box)
                draw = ImageDraw.Draw(image)
                edge = x0 + origin
                advance = (font[1] if kind == 'change' else font).advances.get(name, 0) * scale
                for x in (edge, edge + advance):
                    draw.line([(x, y0 + CAPTION), (x, y0 + height)], fill=GUIDE)
                if kind == 'points':
                    pen = Points()
                    font.glyph_set[name].drawPoints(pen)

                    def place(point):
                        return edge + point[0] * scale, y0 + baseline - point[1] * scale
                    for contour in font.shape(name).contours:
                        draw.line([place(p) for p in contour] + [place(contour[0])], fill=OUTLINE)
                    for contour in pen.contours:
                        for index, (point, kind_of_point) in enumerate(contour):
                            x, y = place(point)
                            if kind_of_point is None:
                                # A handle belongs to the on-curve point beside it.
                                for step in (-1, 1):
                                    other, other_kind = contour[(index + step) % len(contour)]
                                    if other_kind is not None:
                                        draw.line([(x, y), place(other)], fill=OFF_CURVE)
                                draw.ellipse((x - 2, y - 2, x + 2, y + 2), fill=OFF_CURVE)
                            else:
                                draw.rectangle((x - 3, y - 3, x + 3, y + 3), fill=ON_CURVE)
                        if contour:
                            x, y = place(contour[0][0])
                            draw.ellipse((x - 7, y - 7, x + 7, y + 7), outline=ON_CURVE)
                x0 += cell + 4
        out = Path(out) if out else layout.root / 'output/render' / ('-'.join(names)[:60] + '.png')
        out.parent.mkdir(parents=True, exist_ok=True)
        image.save(out)
    print(out)
    return out


def main():
    parser = argparse.ArgumentParser(description=__doc__.split('\n')[0])
    parser.add_argument('glyphs', nargs='+', help='glyph names, also as one quoted list')
    parser.add_argument('--master', action='append', help='a master; the default is every master')
    parser.add_argument('--beside', default='', help='other glyphs of the project to draw in each row')
    parser.add_argument('--base', default='main', help='the revision to compare with (default main)')
    parser.add_argument('--out', type=Path, help='the PNG file (default output/render/<glyphs>.png)')
    args = parser.parse_args()
    names = [name for group in args.glyphs for name in group.split()]
    render(names, args.master, args.beside.split(), args.base, args.out)


if __name__ == '__main__':
    sys.exit(main())
