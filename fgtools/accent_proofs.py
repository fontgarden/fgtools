#!/usr/bin/env python3
"""Draw each accented letter beside the reference fonts, and measure it against them.

    fgtools render-accent-proofs [--master NAME] [--glyphs "NAMES"]
                                 [--references DIRECTORY] [--out DIRECTORY]

The command reads the masters of the project and one font of each family of
the shared reference fonts, at the weight of the master. It does not change
the sources. It writes, to output/accent-proofs/:

    <Master>-01.png ...   proof sheets, the letters with findings first
    review.json           the measurements and the findings of each letter

A row of a sheet is one accented letter: the project in the first column,
then the same character in each reference font. A lowercase letter is drawn
at one x-height in every font, and a capital letter at one cap height, so
that the distance of the mark from the letter can be compared.

Two numbers describe where a mark sits:

    position   the center of the mark, as a share of the width of the base
               letter: 0 is the left edge, 0.5 the center, 1 the right edge
    gap        the distance between the base letter and the mark, as a share
               of the x-height. A negative gap is an overlap.

A letter gets a finding when:

- its position or its gap is outside the range of the reference fonts by
  more than 0.04 (`position`, `gap`);
- its mark is not where the other accented letters of the project predict
  (`project`), the test of `fgtools check-accents`;
- its mark is not where the anchors of its parts are (`anchors`).

A finding is a reason to look at the letter. It is not a fault: the
reference fonts do not dictate the design. A letter without a finding can be
wrong in a way that the numbers do not show, so the sheets show all letters.
"""
from __future__ import annotations

import argparse
import json
import sys
import unicodedata
from pathlib import Path

from fgtools import project, reference_fonts
from fgtools.accent_placement import (Font, anchor_position, calibrated_position, observations)

MARGIN = 0.04          # how far outside the reference range a value can be
MINIMUM_FONTS = 3      # a range needs this number of reference fonts
TOLERANCE = 8          # font units, for the `project` and `anchors` findings
BACKGROUND, GUIDE = (38, 38, 40), (74, 74, 78)
INK, REFERENCE_INK = (226, 226, 220), (150, 150, 152)
TEXT, FINDING = (170, 170, 172), (232, 160, 84)
CELL, ROW, CAPTION, HEADER = 150, 196, 250, 30
BASELINE = 150         # pixels from the top of a row
X_HEIGHT, CAP_HEIGHT = 62, 84


def height(font, character):
    name = font.names.get(ord(character))
    return font.shape(name).top if name and not font.shape(name).empty else None


def measure(font):
    """{character: record} for the accented letters with one mark."""
    x_height = height(font, 'x')
    found = {}
    if not x_height:
        return found
    for row in observations(font):
        base, mark = font.shape(row['base']), font.shape(row['mark'])
        center = (mark.left + mark.right) / 2 + row['dx']
        gap = (mark.bottom + row['dy'] - base.top if row['side'] == 'top'
               else base.bottom - (mark.top + row['dy']))
        found[chr(font.code_points[row['glyph']])] = dict(
            row, position=(center - base.left) / max(base.right - base.left, 1),
            gap=gap / x_height)
    return found


def reference_findings(record, others):
    """The reference range of the position and the gap, and the findings."""
    result, findings = {'fonts': len(others)}, []
    for key in ('position', 'gap'):
        values = [other[key] for other in others]
        if len(values) < MINIMUM_FONTS:
            continue
        low, high = min(values), max(values)
        result[key] = [round(low, 3), round(high, 3)]
        excess = max(low - record[key], record[key] - high)
        if excess > MARGIN:
            findings.append((key, excess, f'{key} {record[key]:.2f}, reference fonts '
                                          f'{low:.2f} to {high:.2f}'))
    return result, findings


def project_findings(font, row, rows, tolerance=TOLERANCE):
    """Findings from the other accented letters and the anchors of the project."""
    findings = []
    position = anchor_position(font, row, rows) or calibrated_position(font, row, rows)
    if position is not None:
        error = (row['dx'] - position[0], row['dy'] - position[1])
        if max(map(abs, error)) > tolerance:
            findings.append(('project', max(map(abs, error)) / font.units_per_em,
                             f'{error[0]:+.0f}, {error[1]:+.0f} units from the position that the '
                             'other accented letters predict'))
    side = row['side']
    anchor = font.anchors.get(row['base'], {}).get(side)
    attach = font.anchors.get(row['mark'], {}).get('_' + side)
    if anchor and attach:
        error = (row['dx'] - (anchor[0] - attach[0]), row['dy'] - (anchor[1] - attach[1]))
        if max(map(abs, error)) > 0:
            findings.append(('anchors', max(map(abs, error)) / font.units_per_em,
                             f'{error[0]:+.0f}, {error[1]:+.0f} units from the `{side}` anchors'))
    return findings


def accented(font):
    """(character, glyph) for each accented Latin letter of a font."""
    for name, code_point in sorted(font.code_points.items(), key=lambda item: item[1]):
        base, *marks = unicodedata.normalize('NFD', chr(code_point))
        if marks and unicodedata.name(base, '').startswith('LATIN') \
                and all(unicodedata.combining(mark) for mark in marks) \
                and not font.shape(name).empty:
            yield chr(code_point), name


def review(font, references, glyphs=None):
    """One record for each accented letter, the largest finding first."""
    rows = list(observations(font))
    by_glyph = {row['glyph']: row for row in rows}
    measured = measure(font)
    reference_measures = [(label, measure(reference)) for label, reference in references]
    records = []
    for character, glyph in accented(font):
        if glyphs and glyph not in glyphs:
            continue
        record = {'glyph': glyph, 'character': character, 'code_point': f'U+{ord(character):04X}',
                  'findings': [], 'size': 0.0}
        if character in measured:
            own = measured[character]
            others = [found[character] for _, found in reference_measures if character in found]
            reference, findings = reference_findings(own, others)
            findings += project_findings(font, by_glyph[glyph], rows)
            record.update(base=own['base'], mark=own['mark'], side=own['side'],
                          position=round(own['position'], 3), gap=round(own['gap'], 3),
                          reference=reference, findings=[text for _, _, text in findings],
                          kinds=[kind for kind, _, _ in findings],
                          size=round(max((size for _, size, _ in findings), default=0.0), 4))
        else:
            record['note'] = 'not measured: not one base and one mark as components'
        records.append(record)
    records.sort(key=lambda record: (-record['size'], 'note' not in record, record['code_point']))
    return records


def rasterize(shape, scale, origin_x, width=CELL, rows=ROW, baseline=BASELINE, oversample=3):
    """The coverage of a glyph in a cell, as an array of 0 to 255. Nonzero winding fill."""
    import numpy
    from PIL import Image, ImageDraw
    size = (width * oversample, rows * oversample)
    winding = numpy.zeros((size[1], size[0]), dtype=numpy.int16)
    for contour in shape.contours:
        if len(contour) < 3:
            continue
        points = [((origin_x + x * scale) * oversample, (baseline - y * scale) * oversample)
                  for x, y in contour]
        area = sum(x0 * y1 - x1 * y0 for (x0, y0), (x1, y1) in zip(points, points[1:] + points[:1]))
        mask = Image.new('L', size, 0)
        ImageDraw.Draw(mask).polygon(points, fill=1)
        winding += numpy.asarray(mask, dtype=numpy.int16) * (1 if area > 0 else -1)
    filled = Image.fromarray(((winding != 0) * 255).astype(numpy.uint8))
    return numpy.asarray(filled.resize((width, rows), Image.BOX), dtype=numpy.float32) / 255


def draw_sheet(path, title, records, first_index, columns):
    """One proof sheet. `columns` is [(label, font)], the project first."""
    import numpy
    from PIL import Image, ImageDraw, ImageFont
    small, large = ImageFont.load_default(13), ImageFont.load_default(17)
    width = CAPTION + CELL * len(columns)
    image = Image.new('RGB', (width, HEADER * 2 + ROW * len(records)), BACKGROUND)
    draw = ImageDraw.Draw(image)
    draw.text((10, 6), title, fill=TEXT, font=large)
    for index, (label, _) in enumerate(columns):
        draw.text((CAPTION + CELL * index + 6, HEADER + 8), label[:20],
                  fill=INK if index == 0 else TEXT, font=small)
    for line, record in enumerate(records):
        top = HEADER * 2 + ROW * line
        draw.line([(0, top), (width, top)], fill=GUIDE)
        upper = unicodedata.normalize('NFD', record['character'])[0].isupper()
        color = FINDING if record['findings'] else TEXT
        draw.text((10, top + 8), f'{first_index + line}  {record["glyph"]}', fill=color, font=large)
        draw.text((10, top + 30), record['code_point'], fill=TEXT, font=small)
        notes = list(record['findings']) or [record.get('note', 'no finding')]
        if 'position' in record:
            notes.append(f'position {record["position"]:.2f}, gap {record["gap"]:.2f}')
        y = top + 50
        for note in notes:
            words, text = note.split(), ''
            for word in words + ['']:
                if not word or len(text) + len(word) > 33:
                    draw.text((10, y), text, fill=color if note in record['findings'] else TEXT,
                              font=small)
                    y, text = y + 15, word
                else:
                    text = f'{text} {word}'.strip()
        for index, (_, font) in enumerate(columns):
            left = CAPTION + CELL * index
            name = font.names.get(ord(record['character']))
            reference_height = height(font, 'H' if upper else 'x')
            target = CAP_HEIGHT if upper else X_HEIGHT
            draw.line([(left + 8, top + BASELINE), (left + CELL - 8, top + BASELINE)], fill=GUIDE)
            draw.line([(left + 8, top + BASELINE - target), (left + CELL - 8, top + BASELINE - target)],
                      fill=GUIDE)
            if not name or not reference_height or font.shape(name).empty:
                draw.text((left + 60, top + 90), 'none', fill=GUIDE, font=small)
                continue
            shape = font.shape(name)
            scale = target / reference_height
            origin = (CELL - (shape.left + shape.right) * scale) / 2
            coverage = rasterize(shape, scale, origin)[..., None]
            box = (left, top, left + CELL, top + ROW)
            under = numpy.asarray(image.crop(box), dtype=numpy.float32)
            ink = numpy.array(INK if index == 0 else REFERENCE_INK, dtype=numpy.float32)
            image.paste(Image.fromarray((under * (1 - coverage) + ink * coverage).astype(numpy.uint8)),
                        box)
    image.save(path)


def master_weights(layout):
    """{master name: value of the weight axis}, 400 for a project without that axis."""
    weights = {name: 400 for name in layout.masters}
    if layout.designspace:
        from fontTools.designspaceLib import DesignSpaceDocument
        document = DesignSpaceDocument.fromfile(layout.designspace)
        axis = next((axis for axis in document.axes if axis.tag == 'wght'), None)
        for name, source in zip(layout.masters, document.sources):
            if axis and axis.name in source.location:
                weights[name] = axis.map_backward(source.location[axis.name])
    return weights


def reference_paths(directory, weight):
    """One upright font for each family: the variable font, or the static
    font nearest to the weight."""
    families = {}
    for path in reference_fonts.fonts(directory):
        bold = 'Bold' in path.name
        rank = 0 if '[' in path.name else 1 if bold == (weight >= 550) else 2
        families[path.parent] = min(families.get(path.parent, (9, path)), (rank, path))
    return [path for _, path in sorted(families.values(), key=lambda item: item[1])]


def render(root=None, master=None, glyphs=None, references=None, out=None, rows=6):
    layout = project.load(root)
    out = Path(out) if out else layout.root / 'output/accent-proofs'
    out.mkdir(parents=True, exist_ok=True)
    for old in out.glob('*-[0-9][0-9].png'):
        old.unlink()
    weights, data, cache = master_weights(layout), {}, {}
    import os
    available = references or os.environ.get(reference_fonts.VARIABLE)
    if not available:
        print(f'No reference fonts: set {reference_fonts.VARIABLE} or give --references. '
              'The sheets show the project only.', file=sys.stderr)
    for name in [master] if master else layout.masters:
        weight = weights[name]
        loaded = []
        for path in reference_paths(available, weight) if available else []:
            if (path, weight) not in cache:
                try:
                    cache[path, weight] = Font.from_compiled(path, weight)
                except Exception as error:   # a font that cannot be read is reported and left out
                    print(f'{path}: {error}', file=sys.stderr)
                    continue
            loaded.append((path.parent.name, cache[path, weight]))
        font = Font.from_ufo(layout.ufo(name))
        records = review(font, loaded, glyphs)
        columns = [(layout.root.name, font), *loaded]
        for start in range(0, len(records), rows):
            sheet = f'{name}-{start // rows + 1:02d}.png'
            for record in records[start:start + rows]:
                record['sheet'] = sheet
            draw_sheet(out / sheet, f'{name}, weight {weight:g}: accented letters '
                       f'{start + 1} to {min(start + rows, len(records))} of {len(records)}',
                       records[start:start + rows], start + 1, columns)
        data[name] = {'weight': weight, 'reference_fonts': [label for label, _ in loaded],
                      'letters': records}
        listed = [record for record in records if record['findings']]
        print(f'{name}: {len(records)} accented letters, {len(listed)} with findings, '
              f'{len(loaded)} reference fonts, {-(-len(records) // rows)} sheets')
        for record in listed:
            print(f'  {record["glyph"]} ({record["sheet"]}): ' + '; '.join(record['findings']))
    (out / 'review.json').write_text(json.dumps(data, indent=1, ensure_ascii=False) + '\n')
    print(f'Sheets and review.json are in {out}')
    return 0


def main():
    parser = argparse.ArgumentParser(prog='fgtools render-accent-proofs',
                                     description=__doc__.split('\n')[0])
    parser.add_argument('--master', help='one master (default: all)')
    parser.add_argument('--glyphs', default='', help='only these glyph names, space-separated')
    parser.add_argument('--references',
                        help=f'the reference font collection (default: ${reference_fonts.VARIABLE})')
    parser.add_argument('--out', help='output directory (default: output/accent-proofs)')
    parser.add_argument('--rows', type=int, default=6, help='letters on one sheet (default: 6)')
    args = parser.parse_args()
    return render(master=args.master, glyphs=set(args.glyphs.split()), references=args.references,
                  out=args.out, rows=args.rows)


if __name__ == '__main__':
    sys.exit(main())
