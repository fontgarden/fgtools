#!/usr/bin/env python3
"""Change a glyph of the sources with a calculated operation.

    fgtools edit GLYPH set-coordinate --axis y --from 536 --to 520
    fgtools edit GLYPH set-sidebearings --left 64 --right 40
    fgtools edit GLYPH copy DONOR [--mirror horizontal|vertical|both]

An agent chooses the operation and its values; this command calculates the
points and writes them. Each operation states the result, not a movement, so
a second run changes nothing.

    set-coordinate    Every point with the coordinate --from on the axis gets
                      the coordinate --to: an edge of a stroke moves, with its
                      handles on the same line. --within LOW HIGH limits the
                      points to a range on the other axis.
    set-sidebearings  The outline, the components and the anchors move so
                      that the left sidebearing is --left, and the advance is
                      set so that the right sidebearing is --right.
    copy              The contours and the advance of DONOR replace those of
                      the glyph. --mirror horizontal mirrors in the advance
                      width (b from d). --mirror vertical mirrors between the
                      baseline and the x-height (q from d). --mirror both is
                      a rotation by 180 degrees (p from d). A mirror reverses
                      the contours, so the command reverses them again.

--master names a master; the default is every master. The command changes
the GLIF text in place and keeps its style. It gives a changed glyph the
purple mark, and it refuses a green glyph: green contour glyphs are frozen.
Look at the result with `fgtools render GLYPH`.
"""
from __future__ import annotations

import argparse
import plistlib
import re
import sys

from fontTools.pens.pointPen import ReverseContourPointPen
from fontTools.ufoLib.glifLib import GlyphSet

from fgtools import project
from fgtools.accent_placement import Font
from fgtools.draft_weights import ATTRIBUTE, PURPLE, number, set_purple

POINT = re.compile(r'<point\b([^>]*?)/?>')
MOVED = re.compile(r'<(point|anchor|component)\b([^>]*?)/?>')
OUTLINE = re.compile(r'(\t*)<outline>.*?</outline>|(\t*)<outline/>', re.S)


def replace_attributes(text, pattern, change):
    """`text` with the attributes of each tag of `pattern` changed.
    `change(kind, attributes)` returns {attribute: new value}."""
    parts, position = [], 0
    for tag in pattern.finditer(text):
        body = tag.group(tag.lastindex)
        offset = tag.start(tag.lastindex)
        attributes = {m.group(1): m.group(2) for m in ATTRIBUTE.finditer(body)}
        new = change(tag.group(1) if tag.lastindex > 1 else 'point', attributes)
        for match in ATTRIBUTE.finditer(body):
            if match.group(1) in new:
                parts += [text[position:offset + match.start(2)], number(new[match.group(1)])]
                position = offset + match.end(2)
    return ''.join(parts) + text[position:]


def set_coordinate(text, axis, old, new, within=None):
    other = 'y' if axis == 'x' else 'x'

    def change(_, attributes):
        if float(attributes.get(axis, 'nan')) != old:
            return {}
        if within and not within[0] <= float(attributes.get(other, 'nan')) <= within[1]:
            return {}
        return {axis: new}
    return replace_attributes(text, POINT, change)


def set_sidebearings(text, shape, left, right):
    """`shape` is the flattened outline of the glyph, with its components."""
    shift = left - shape.left
    names = {'point': 'x', 'anchor': 'x', 'component': 'xOffset'}

    def change(kind, attributes):
        name = names[kind]
        # A component without an offset has the offset 0, which is not written.
        return {name: float(attributes[name]) + shift} if name in attributes else {}
    if shift:
        text = replace_attributes(text, MOVED, change)
        if 'xOffset' not in text and '<component' in text:
            text = re.sub(r'<component\b(?![^>]*xOffset)([^>]*?)(/?>)',
                          rf'<component\1 xOffset="{number(shift)}"\2', text)
    advance = number(shape.right + shift + right)
    return re.sub(r'(<advance\b[^>]*?\bwidth=")[^"]*', rf'\g<1>{advance}', text, count=1)


class Record:
    def __init__(self):
        self.contours = []

    def beginPath(self, **_):
        self.contours.append([])

    def addPoint(self, point, segmentType=None, smooth=False, **_):
        self.contours[-1].append((point, segmentType, smooth))

    def endPath(self):
        pass

    def addComponent(self, *_, **__):
        pass


def copied_outline(ufo, donor, mirror, advance, height):
    """The contour lines of the donor, mirrored, in the GLIF style of the sources."""
    record = Record()
    pen = ReverseContourPointPen(record) if mirror in ('horizontal', 'vertical') else record
    glyph_set = GlyphSet(str(ufo / 'glyphs'), validateRead=False)
    glyph_set[donor].drawPoints(pen)
    lines = []
    for contour in record.contours:
        lines.append('\t\t<contour>')
        for (x, y), kind, smooth in contour:
            if mirror in ('horizontal', 'both'):
                x = advance - x
            if mirror in ('vertical', 'both'):
                y = height - y
            line = f'\t\t\t<point x="{number(x)}" y="{number(y)}"'
            line += f' type="{kind}"' if kind else ''
            lines.append(line + (' smooth="yes"/>' if smooth else '/>'))
        lines.append('\t\t</contour>')
    return '\n'.join(lines)


def copy(text, ufo, donor, donor_text, mirror):
    height = 0
    if (ufo / 'fontinfo.plist').is_file():
        with open(ufo / 'fontinfo.plist', 'rb') as file:
            height = plistlib.load(file).get('xHeight', 0)
    width = re.search(r'<advance\b[^>]*?\bwidth="([^"]*)"', donor_text)
    advance = float(width.group(1)) if width else 0
    contours = copied_outline(ufo, donor, mirror, advance, height)
    components = '\n'.join(re.findall(r'^\t\t<component\b.*$', text, re.M))
    body = '\n'.join(part for part in (contours, components) if part)
    text = OUTLINE.sub(lambda m: f'\t<outline>\n{body}\n\t</outline>', text, count=1)
    return re.sub(r'(<advance\b[^>]*?\bwidth=")[^"]*', rf'\g<1>{number(advance)}', text, count=1)


def main():
    parser = argparse.ArgumentParser(description=__doc__.split('\n')[0])
    parser.add_argument('glyph')
    parser.add_argument('--master', action='append', help='a master; the default is every master')
    operations = parser.add_subparsers(dest='operation', required=True)
    edge = operations.add_parser('set-coordinate')
    edge.add_argument('--axis', choices=('x', 'y'), required=True)
    edge.add_argument('--from', dest='old', type=float, required=True)
    edge.add_argument('--to', dest='new', type=float, required=True)
    edge.add_argument('--within', type=float, nargs=2, metavar=('LOW', 'HIGH'))
    bearings = operations.add_parser('set-sidebearings')
    bearings.add_argument('--left', type=float, required=True)
    bearings.add_argument('--right', type=float, required=True)
    donor = operations.add_parser('copy')
    donor.add_argument('donor')
    donor.add_argument('--mirror', choices=('horizontal', 'vertical', 'both'))
    args = parser.parse_args()

    source = project.load()
    design = source.design() if source.design_config.exists() else {}
    colors = design.get('colors', {})
    green = [','.join(number(value) for value in rgba) for rgba in colors.get('green', {}).get('rgba', [])]
    rgba = colors.get('purple', {}).get('rgba')
    purple = ','.join(number(value) for value in rgba[-1]) if rgba else PURPLE
    status = 0
    for master in args.master or source.masters:
        ufo = source.ufo(master)
        with open(ufo / 'glyphs/contents.plist', 'rb') as file:
            contents = plistlib.load(file)
        if args.glyph not in contents:
            print(f'{master}: no glyph {args.glyph}')
            status = 1
            continue
        path = ufo / 'glyphs' / contents[args.glyph]
        text = path.read_text()
        mark = re.search(r'<key>public\.markColor</key>\s*<string>([^<]*)', text)
        if mark and mark.group(1) in green:
            print(f'{master}: {args.glyph} is green and is not changed.')
            status = 1
            continue
        if args.operation == 'set-coordinate':
            new = set_coordinate(text, args.axis, args.old, args.new, args.within)
        elif args.operation == 'set-sidebearings':
            shape = Font.from_ufo(ufo).shape(args.glyph)
            if shape.empty:
                print(f'{master}: {args.glyph} has no outline.')
                status = 1
                continue
            new = set_sidebearings(text, shape, args.left, args.right)
        else:
            if args.donor not in contents:
                print(f'{master}: no glyph {args.donor}')
                status = 1
                continue
            new = copy(text, ufo, args.donor, (ufo / 'glyphs' / contents[args.donor]).read_text(), args.mirror)
        if new == text:
            print(f'{master}: {args.glyph} is unchanged.')
            continue
        path.write_text(set_purple(new, purple))
        changed = sum(a != b for a, b in zip(text.splitlines(), new.splitlines()))
        changed += abs(len(text.splitlines()) - len(new.splitlines()))
        print(f'{master}: {args.glyph} changed ({changed} lines), marked purple.')
    return status


if __name__ == '__main__':
    sys.exit(main())
