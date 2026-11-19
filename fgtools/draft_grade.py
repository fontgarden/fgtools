#!/usr/bin/env python3
"""Draft the masters of the grade axis from the weight masters.

usage:
  fgtools draft-grade            draft the grade masters of every weight master
  fgtools draft-grade Regular    draft the grade masters of the named masters

The rule is a table of CONTEXT.md:

  [grade]
  minimum = -200
  maximum = 200

A grade master has the outlines of the weight `wght + grade` on the advances
of `wght`. The outlines come from the weight masters, by interpolation where
the weight is between two of them. A weight below the lightest master or
above the heaviest one is that master, so the grade has no effect past it.
The outline moves by half of the difference of the two advances, so that it
stays in the middle of its advance. On a joining side of an Arabic letter the
points on the edge of the advance stay on that edge. The kerning, the
features and the font info are those of the weight master.

The grade masters are written to sources/, beside the weight masters, and
the designspace gets the grade axis and the masters. A glyph of a grade
master that is calculated is replaced, and one that has a correction of its
own stays: each written glyph has the digest of its outline in its lib. Every drafted glyph is purple.
Use Git to undo a run. Then run `fgtools draft-optical-size --write` for the
grade masters of the large optical size.
"""
from __future__ import annotations

import argparse
import re
import shutil
import sys
import xml.etree.ElementTree as ET

from fgtools import project
from fgtools.draft_optical_size import (ADVANCE, ANCHOR, COMPONENT, POINT, advance_of, body, calculated,
                                        joining_sides, stamp)
from fgtools.draft_weights import PURPLE, draft_glyph, number, set_purple

AXIS = 'Grade'


def weight_masters(source):
    """{master name: weight} of the masters at the default of every other axis."""
    root = ET.parse(source.designspace).getroot()
    defaults = {axis.get('name'): float(axis.get('default')) for axis in root.findall('axes/axis')}
    found = {}
    for element in root.findall('sources/source'):
        location = {d.get('name'): float(d.get('xvalue')) for d in element.findall('location/dimension')}
        if all(location.get(name, value) == value for name, value in defaults.items() if name != 'Weight'):
            found[element.get('stylename')] = location.get('Weight', defaults.get('Weight'))
    return found


def outline_at(texts, weights, weight, file, grid):
    """The GLIF text of a glyph at a weight, or None when the masters are not compatible."""
    names = sorted(weights, key=weights.get)
    weight = min(max(weight, weights[names[0]]), weights[names[-1]])
    for name in names:
        if weights[name] == weight:
            return texts[name].get(file)
    lower = max((n for n in names if weights[n] < weight), key=weights.get)
    upper = min((n for n in names if weights[n] > weight), key=weights.get)
    a, b = texts[lower].get(file), texts[upper].get(file)
    if a is None or b is None:
        return None
    position = (weight - weights[lower]) / (weights[upper] - weights[lower])
    return draft_glyph(a, b, {'x': position, 'y': position}, grid, a if position < 0.5 else b)


def shift_of(own, other, grid):
    """The distance that an outline moves so that it stays in the middle of its advance."""
    return round((own - other) / 2 / grid) * grid


def set_on_advance(name, text, width, advances, grid):
    """The GLIF text of an outline of another weight on the advance `width`.

    `advances` is {glyph name: (advance of the weight master, advance at the other weight)}.
    """
    other = advance_of(text)
    if width == other:
        return text
    shift = shift_of(width, other, grid)
    xs = [float(x) for x in re.findall(r'<point x="(-?[\d.]+)"', text)]
    joins = joining_sides(name)
    left = 'left' in joins and bool(xs) and min(xs) <= 0
    right = 'right' in joins and bool(xs) and max(xs) >= other

    def moved(x):
        if left and x <= 0:
            return x
        if right and x >= other:
            return x + width - other
        return x + shift

    def component(match):
        tag = match.group(0)
        base = re.search(r'\bbase="([^"]*)"', tag).group(1)
        # A part moves with its own draft. The rest of the distance is in the offset.
        rest = shift - shift_of(*advances.get(base, (0, 0)), grid)
        if not rest:
            return tag
        offset = re.search(r'\bxOffset="(-?[\d.]+)"', tag)
        if offset:
            return tag.replace(offset.group(0), f'xOffset="{number(float(offset.group(1)) + rest)}"')
        return tag.replace('/>', f' xOffset="{number(rest)}"/>')

    text = POINT.sub(lambda p: f'{p.group(1)}{number(moved(float(p.group(2))))}{p.group(3)}'
                               f'{p.group(4)}{p.group(5)}', text)
    text = COMPONENT.sub(component, text)
    text = ANCHOR.sub(lambda a: f'{a.group(1)}{number(moved(float(a.group(2))))}{a.group(3)}', text)
    return ADVANCE.sub(lambda a: f'{a.group(1)}{number(width)}{a.group(3)}', text, count=1)


def master_name(name, grade):
    return f'{name} GRAD{number(grade)}'


def drafts_of(name, grade, texts, weights, grid):
    """{file: GLIF text} of a grade master, calculated from the texts of the weight masters."""
    weight = weights[name] + grade
    outlines = {file: outline_at(texts, weights, weight, file, grid) or text
                for file, text in texts[name].items()}
    glyph = lambda value: re.search(r'<glyph name="([^"]*)"', value).group(1)
    advances = {glyph(text): (advance_of(text), advance_of(outlines[file]))
                for file, text in texts[name].items()}
    return {file: set_on_advance(glyph(text), outlines[file], advance_of(text), advances, grid)
            for file, text in texts[name].items()}


def draft_master(source, name, grade, texts, weights, grid, purple, replace_all=False):
    """Write one grade master into sources/. Returns (path, counts).

    Each written glyph gets the digest of its outline. A glyph is replaced
    when its outline still has that digest. Any other glyph of a grade master
    that exists has a correction of its own, and it stays.
    """
    own = source.ufo(name)
    target = own.with_name(f'{own.stem}_GRAD{number(grade)}.ufo')
    new = not target.exists()
    if new:
        shutil.copytree(own, target)
    counts = {'drafted': 0, 'kept': 0}
    for file, draft in drafts_of(name, grade, texts, weights, grid).items():
        path = target / 'glyphs' / file
        present = path.read_text() if path.is_file() else ''
        if not (new or replace_all or calculated(present)):
            counts['kept'] += 1
            continue
        if body(present) != body(draft) or not calculated(present):
            path.write_text(stamp(set_purple(draft, purple)))
            counts['drafted'] += 1
    return target, counts


def write_designspace(source, weights, grades, sizes):
    """Give the designspace the grade axis and the grade masters."""
    tree = ET.parse(source.designspace)
    root = tree.getroot()
    axes = root.find('axes')
    if axes.find(f'axis[@name="{AXIS}"]') is None:
        ET.SubElement(axes, 'axis', {'name': AXIS, 'tag': 'GRAD', 'default': '0',
                                     'minimum': number(min(grades)), 'maximum': number(max(grades))})
    sources = root.find('sources')
    for element in list(sources.findall('source')) + root.findall('instances/instance'):
        location = element.find('location')
        if location.find(f'dimension[@name="{AXIS}"]') is None:
            ET.SubElement(location, 'dimension', {'name': AXIS, 'xvalue': '0'})
    by_name = {element.get('stylename'): element for element in sources.findall('source')}
    for name in weights:
        for suffix in [''] + sizes:
            model = by_name.get(name + suffix)
            if model is None:
                continue
            for grade in grades:
                style = master_name(name, grade) + suffix
                if style in by_name:
                    continue
                stem = model.get('filename')[:-len('.ufo')]
                element = ET.SubElement(sources, 'source', {
                    'familyname': model.get('familyname'), 'stylename': style,
                    'name': f'{model.get("familyname")} {style}',
                    'filename': f'{stem}_GRAD{number(grade)}.ufo'})
                location = ET.SubElement(element, 'location')
                for dimension in model.findall('location/dimension'):
                    value = number(grade) if dimension.get('name') == AXIS else dimension.get('xvalue')
                    ET.SubElement(location, 'dimension', {'name': dimension.get('name'), 'xvalue': value})
    ET.indent(tree, space='  ')
    tree.write(source.designspace, encoding='UTF-8', xml_declaration=True)


def main():
    parser = argparse.ArgumentParser(prog='fgtools draft-grade', description=__doc__,
                                     formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument('masters', nargs='*', help='the weight masters to draft from (default: all)')
    parser.add_argument('--all', action='store_true', help='also replace the glyphs that were corrected by hand')
    args = parser.parse_args()
    source = project.load()
    design = source.design()
    table = design.get('grade')
    if not table:
        raise project.ProjectError(f'{source.design_config} has no [grade] table')
    grades = [table['minimum'], table['maximum']]
    grid = design.get('grid', {}).get('source', 1)
    rgba = design.get('colors', {}).get('purple', {}).get('rgba')
    purple = ','.join(number(value) for value in rgba[-1]) if rgba else PURPLE
    weights = {name: weight for name, weight in weight_masters(source).items() if 'GRAD' not in name}
    for name in args.masters:
        if name not in weights:
            raise project.ProjectError(f'no weight master named {name}')
    texts = {name: {path.name: path.read_text() for path in sorted((source.ufo(name) / 'glyphs').glob('*.glif'))}
             for name in weights}
    optical = design.get('optical_size')
    sizes = [f' {optical["to"]}pt'] if optical else []
    low, high = min(weights.values()), max(weights.values())
    for name in args.masters or weights:
        for grade in grades:
            ufo, counts = draft_master(source, name, grade, texts, weights, grid, purple, args.all)
            print(f'{master_name(name, grade)}: outlines of weight '
                  f'{number(min(max(weights[name] + grade, low), high))}, '
                  f'{counts["drafted"]} glyphs drafted, {counts["kept"]} kept')
            for suffix in sizes:
                large = source.ufos.get(name + suffix)
                if large is not None:
                    copy = large.with_name(f'{large.stem}_GRAD{number(grade)}.ufo')
                    if not copy.exists():
                        # The font info is that of the large master. The glyphs are those
                        # of the grade master, until the optical size draft.
                        shutil.copytree(large, copy)
                        shutil.rmtree(copy / 'glyphs')
                        shutil.copytree(ufo / 'glyphs', copy / 'glyphs')
    write_designspace(source, weights, grades, sizes)
    print(source.designspace.relative_to(source.root))
    return 0


if __name__ == '__main__':
    sys.exit(main())
