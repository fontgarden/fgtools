"""Measure the glyphs in a picture of text, for example a screenshot of another font.

A picture of a font that the designer gives as an example holds numbers: how
large a glyph is beside the letters, how thick its strokes are, where it
stands. An agent that only looks at the picture misses differences of a few
percent. This command reads them.

The picture is one line of text, dark on light or light on dark. The command
divides it into glyphs at the empty columns, so the glyphs must not touch.
With --text it names each glyph. When the text has an H, sizes are in cap
heights (the height of H, with the baseline at 0) and strokes are in H stems.
Without an H they are in pixels.

    fgtools measure-picture picture.png --text 'H$Sn$o$O'

For each glyph it prints the width, the top and the bottom, and the strokes
that two vertical and two horizontal cuts cross. Compare a glyph with the
related letter of the same picture (a dollar sign with S), and draw to the
ratios, not to the pixels.
"""
from __future__ import annotations

import argparse
import sys

CUTS = (0.3, 0.7)       # the cuts, as a part of the width or the height of the glyph


def ink(path):
    """A boolean array: True where the picture has ink."""
    import numpy
    from PIL import Image
    gray = numpy.asarray(Image.open(path).convert('L'), dtype=numpy.float32)
    background = float(numpy.median(gray))
    return numpy.abs(gray - background) > 96


def runs(line):
    """[(start, end)] of the runs of True values in a row or a column."""
    found, start = [], None
    for index, value in enumerate(line):
        if value and start is None:
            start = index
        elif not value and start is not None:
            found.append((start, index))
            start = None
    if start is not None:
        found.append((start, len(line)))
    return found


def glyphs(picture):
    """One dict for each glyph of the picture, from left to right, in pixels."""
    found = []
    for left, right in runs(picture.any(axis=0)):
        part = picture[:, left:right]
        rows = runs(part.any(axis=1))
        top, bottom = rows[0][0], rows[-1][1]
        width, height = right - left, bottom - top
        down = [[end - start for start, end in runs(part[:, int(width * cut)])] for cut in CUTS]
        across = [[end - start for start, end in runs(part[top + int(height * cut)])] for cut in CUTS]
        found.append(dict(left=left, right=right, top=top, bottom=bottom, down=down, across=across))
    return found


def report(found, text=None):
    """The lines of the report. `text` names the glyphs when it has one character for each."""
    names = list(text) if text and len(text) == len(found) else [str(index + 1) for index in range(len(found))]
    lines = []
    if text and len(text) != len(found):
        lines.append(f'The picture has {len(found)} glyphs and the text has {len(text)} characters: '
                     'the glyphs have numbers. Glyphs that touch count as one.')
    control = next((glyph for name, glyph in zip(names, found) if name == 'H'), None)
    if control:
        cap, baseline = control['bottom'] - control['top'], control['bottom']
        stem = control['across'][0][0]
        size, stroke = (lambda value: f'{value / cap:.2f}'), (lambda value: f'{value / stem:.2f}')
        lines.append(f'Sizes in cap heights ({cap} pixels), strokes in H stems ({stem} pixels). The baseline is 0.')
    else:
        baseline = max(glyph['bottom'] for glyph in found)
        size = stroke = lambda value: f'{value:g}'
        lines.append('No H in the text: sizes and strokes in pixels. The lowest glyph is at 0.')
    for name, glyph in zip(names, found):
        cuts = lambda groups: ' | '.join(' '.join(stroke(value) for value in group) or '-' for group in groups)
        lines.append(f'{name}  width {size(glyph["right"] - glyph["left"])}  '
                     f'top {size(baseline - glyph["top"])}  bottom {size(baseline - glyph["bottom"])}  '
                     f'strokes down {cuts(glyph["down"])}  across {cuts(glyph["across"])}')
    return lines


def main(argv=None):
    parser = argparse.ArgumentParser(prog='fgtools measure-picture', description=__doc__.split('\n')[0])
    parser.add_argument('picture', help='a PNG or JPEG of one line of text')
    parser.add_argument('--text', help='the characters of the picture, without spaces')
    args = parser.parse_args(argv)
    found = glyphs(ink(args.picture))
    if not found:
        sys.exit('The picture has no ink.')
    print('\n'.join(report(found, args.text.replace(' ', '') if args.text else None)))


if __name__ == '__main__':
    main()
