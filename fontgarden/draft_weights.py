#!/usr/bin/env python3
"""Draft the masters of more weights from two masters of the project.

usage:
  fgtools draft-weights            draft every weight of sources/design.toml
  fgtools draft-weights Thin       draft the named weights
  fgtools draft-weights --build    also compile a variable font of all masters

A weight is a table of sources/design.toml:

  [weights.Thin]
  wght = 100
  between = ["Regular", "Bold"]
  vertical_stem = { Regular = 100, Bold = 192, target = 28 }
  horizontal_stroke = { Regular = 88, Bold = 168, target = 26 }

Each coordinate of the draft is on the line through its values in the two
masters. The position on that line comes from the strokes: `vertical_stem`
sets it for x and `horizontal_stroke` sets it for y, so that a weight can
gain less in its horizontals than in its verticals. A position outside the
two masters is an extrapolation, and it makes every difference between the
two masters larger. A glyph that is not compatible in the two masters is
copied from the nearer master, and the report lists it.

The drafts are written to out/weights/, which Git ignores, with a
designspace that has the masters of the project and the drafts. Every
drafted glyph is purple. Nothing in sources/ is changed.
"""
from __future__ import annotations

import argparse
import os
import plistlib
import re
import shutil
import subprocess
import sys
import xml.etree.ElementTree as ET
from pathlib import Path

from fontgarden import project
from fontgarden.build_source_snapshot import tool_path

OUTPUT = 'out/weights'
PURPLE = '0.54,0.44,0.88,1'
TAG = re.compile(r'<(advance|point|anchor|component)\b([^>]*?)/?>')
ATTRIBUTE = re.compile(r'\b(\w+)="([^"]*)"')
# The attributes that hold a coordinate, and the axis of each.
COORDINATES = {
    'advance': {'width': 'x', 'height': 'y'},
    'point': {'x': 'x', 'y': 'y'},
    'anchor': {'x': 'x', 'y': 'y'},
    'component': {'xOffset': 'x', 'yOffset': 'y'},
}
# The attributes that two masters must have in common for a tag to be compatible.
IDENTITY = {'point': ('type',), 'anchor': ('name',), 'component': ('base',), 'advance': ()}
STYLE_NAMES = {100: 'Thin', 200: 'ExtraLight', 300: 'Light', 400: 'Regular', 500: 'Medium',
               600: 'SemiBold', 700: 'Bold', 800: 'ExtraBold', 900: 'Black'}


def number(value):
    """A coordinate as GLIF text: an integer without a decimal point."""
    return str(int(value)) if float(value) == int(value) else str(value)


def slots(text):
    """The coordinate attributes of a GLIF text, in order, and its structure.

    Returns (slots, structure). A slot is (start, end, axis, value) of one
    attribute value. The structure is equal in two masters that are compatible.
    """
    found, structure = [], []
    for tag in TAG.finditer(text):
        kind, attributes = tag.group(1), {}
        for attribute in ATTRIBUTE.finditer(tag.group(2)):
            attributes[attribute.group(1)] = attribute.group(2)
            axis = COORDINATES[kind].get(attribute.group(1))
            if axis:
                start = tag.start(2) + attribute.start(2)
                found.append((start, start + len(attribute.group(2)), axis, float(attribute.group(2))))
        structure.append((kind, tuple(attributes.get(key) for key in IDENTITY[kind]),
                          tuple(key for key in attributes if key in COORDINATES[kind])))
    return found, structure + [text.count('<contour>')]


def set_purple(text, purple):
    """The GLIF text with a purple mark, and a purple label where the glyph has a label."""
    text = re.sub(r'(<key>public\.markColor</key>\s*<string>)[^<]*', rf'\g<1>{purple}', text)
    text = re.sub(r'(<key>com\.runebender\.markLabel</key>\s*<string>)[^<]*', r'\g<1>purple', text)
    if 'public.markColor' in text:
        return text
    entry = f'\t\t\t<key>public.markColor</key>\n\t\t\t<string>{purple}</string>\n'
    if '<lib>' in text:
        return re.sub(r'(<lib>\s*<dict>\n)', rf'\g<1>{entry}', text, count=1)
    return text.replace('</glyph>', f'\t<lib>\n\t\t<dict>\n{entry}\t\t</dict>\n\t</lib>\n</glyph>')


def draft_glyph(first, second, factors, grid, template):
    """The GLIF text of one glyph at `factors`, or None when the two masters
    are not compatible. `template` is the text that gives everything but the
    coordinates: `first` or `second`."""
    (slots_a, structure_a), (slots_b, structure_b) = slots(first), slots(second)
    if structure_a != structure_b:
        return None
    parts, position = [], 0
    for (start, end, axis, _), (_, _, _, a), (_, _, _, b) in zip(
            slots(template)[0], slots_a, slots_b):
        value = a + (b - a) * factors[axis]
        parts += [template[position:start], number(round(value / grid) * grid)]
        position = end
    return ''.join(parts) + template[position:]


def signed_areas(text):
    """The signed area of the point polygon of each contour of a GLIF text."""
    areas = []
    for contour in re.findall(r'<contour>(.*?)</contour>', text, re.S):
        points = [(float(x), float(y)) for x, y in
                  re.findall(r'<point\b[^>]*?\bx="([^"]*)"[^>]*?\by="([^"]*)"', contour)]
        areas.append(sum(x0 * y1 - x1 * y0 for (x0, y0), (x1, y1)
                         in zip(points, points[1:] + points[:1])) / 2)
    return areas


def collapsed(source, draft):
    """True when a contour of the draft has turned inside out or has no area."""
    return any(before * after <= 0 for before, after
               in zip(signed_areas(source), signed_areas(draft)) if before)


def factor(setting, between, name):
    first, second = (setting[master] for master in between)
    if first == second:
        raise project.ProjectError(f'[weights.{name}]: the two masters have the same stroke')
    return (setting['target'] - first) / (second - first)


def draft_master(source, name, weight, output):
    """Write the UFO of one weight. Returns (path, counts, lists of glyph names)."""
    between = weight['between']
    factors = {'x': factor(weight['vertical_stem'], between, name),
               'y': factor(weight['horizontal_stroke'], between, name)}
    design = source.design()
    grid = design.get('grid', {}).get('source', 1)
    rgba = design.get('colors', {}).get('purple', {}).get('rgba')
    purple = ','.join(number(value) for value in rgba[-1]) if rgba else PURPLE
    first, second = (source.ufo(master) for master in between)
    # The nearer master gives the glyph set, the features and the font info.
    template = first if (factors['x'] + factors['y']) / 2 < 0.5 else second
    target = output / template.name.replace(template.stem.rsplit('-', 1)[-1], name)
    if target.exists():
        shutil.rmtree(target)
    shutil.copytree(template, target)
    report = {'drafted': [], 'copied': [], 'collapsed': []}
    for path in sorted((target / 'glyphs').glob('*.glif')):
        texts = [(ufo / 'glyphs' / path.name) for ufo in (first, second)]
        glyph = re.search(r'<glyph name="([^"]*)"', path.read_text()).group(1)
        if not all(text.is_file() for text in texts):
            report['copied'].append(glyph)
            continue
        a, b = (text.read_text() for text in texts)
        draft = draft_glyph(a, b, factors, grid, a if template == first else b)
        if draft is None:
            report['copied'].append(glyph)
            continue
        if collapsed(a, draft):
            report['collapsed'].append(glyph)
        path.write_text(set_purple(draft, purple))
        report['drafted'].append(glyph)
    kernings = [plistlib.loads((ufo / 'kerning.plist').read_bytes())
                if (ufo / 'kerning.plist').is_file() else {} for ufo in (first, second)]
    if any(kernings):
        kerning = {}
        for left in sorted(set(kernings[0]) | set(kernings[1])):
            for right in sorted(set(kernings[0].get(left, {})) | set(kernings[1].get(left, {}))):
                a, b = (table.get(left, {}).get(right, 0) for table in kernings)
                value = round((a + (b - a) * factors['x']) / grid) * grid
                if value:
                    kerning.setdefault(left, {})[right] = value
        (target / 'kerning.plist').write_bytes(plistlib.dumps(kerning))
    info_path = target / 'fontinfo.plist'
    if info_path.is_file():
        info = plistlib.loads(info_path.read_bytes())
        before = info.get('styleName', '')
        info['styleName'] = name
        info['openTypeOS2WeightClass'] = weight['wght']
        for key in ('postscriptFontName', 'postscriptFullName'):
            if before and before in info.get(key, ''):
                info[key] = info[key].replace(before, name)
        info_path.write_bytes(plistlib.dumps(info))
    return target, factors, report


def write_designspace(source, drafted, output):
    """A designspace in `output` with the masters of the project and the drafts."""
    tree = ET.parse(source.designspace)
    root = tree.getroot()
    axis = root.find('axes/axis[@tag="wght"]')
    old = float(axis.get('minimum')), float(axis.get('maximum'))
    weights = [weight for _, weight, _ in drafted]
    new = min(old[0], *weights), max(old[1], *weights)
    axis.set('minimum', number(new[0]))
    axis.set('maximum', number(new[1]))
    sources = root.find('sources')
    model = sources.find('source')
    for element in sources.findall('source'):
        ufo = (source.designspace.parent / element.get('filename')).resolve()
        element.set('filename', Path(os.path.relpath(ufo, output)).as_posix())
    family = model.get('familyname') or source.config.get('familyName', '')
    for name, weight, ufo in drafted:
        element = ET.SubElement(sources, 'source', {
            'familyname': family, 'stylename': name, 'name': f'{family} {name}'.strip(),
            'filename': ufo.name})
        location = ET.SubElement(element, 'location')
        ET.SubElement(location, 'dimension', {'name': axis.get('name'), 'xvalue': number(weight)})
    # A rule that reached the old end of the axis reaches the new end.
    for condition in root.findall('rules/rule/conditionset/condition'):
        if condition.get('name') == axis.get('name'):
            if condition.get('minimum') and float(condition.get('minimum')) == old[0]:
                condition.set('minimum', number(new[0]))
            if condition.get('maximum') and float(condition.get('maximum')) == old[1]:
                condition.set('maximum', number(new[1]))
    instances = root.find('instances')
    if instances is not None:
        root.remove(instances)
    instances = ET.Element('instances')
    root.insert(list(root).index(sources) + 1, instances)
    for value, style in STYLE_NAMES.items():
        if new[0] <= value <= new[1]:
            element = ET.SubElement(instances, 'instance', {
                'familyname': family, 'stylename': style, 'name': f'{family} {style}'.strip()})
            location = ET.SubElement(element, 'location')
            ET.SubElement(location, 'dimension', {'name': axis.get('name'), 'xvalue': str(value)})
    ET.indent(tree, space='  ')
    path = output / source.designspace.name
    tree.write(path, encoding='UTF-8', xml_declaration=True)
    return path


def build(designspace):
    """Compile the variable font of a designspace with fontc. Returns its path."""
    fontc = shutil.which('fontc', path=tool_path())
    if fontc is None:
        sys.exit('fontc is not installed. Run `fgtools install-tools`.')
    font = designspace.with_name(designspace.stem + '[wght].ttf')
    result = subprocess.run([fontc, str(designspace), '--output-file', str(font),
                             '--build-dir', str(designspace.parent / 'build')],
                            capture_output=True, text=True)
    if result.returncode:
        print(result.stdout + result.stderr, file=sys.stderr)
        sys.exit('fontc failed on the designspace of the drafts.')
    return font


def main():
    parser = argparse.ArgumentParser(prog='fgtools draft-weights', description=__doc__,
                                     formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument('weights', nargs='*', help='the weights to draft (default: all)')
    parser.add_argument('--build', action='store_true',
                        help='compile a variable font of the masters and the drafts')
    parser.add_argument('--output', default=OUTPUT, help=f'output directory (default: {OUTPUT})')
    args = parser.parse_args()
    source = project.load()
    if source.designspace is None:
        raise project.ProjectError('draft-weights needs a designspace with two masters')
    tables = source.design().get('weights', {})
    if not tables:
        raise project.ProjectError(f'{source.design_config} has no [weights.<name>] table')
    names = args.weights or list(tables)
    for name in names:
        if name not in tables:
            raise project.ProjectError(f'{source.design_config} has no [weights.{name}] table')
        for master in tables[name]['between']:
            if master not in source.ufos:
                raise project.ProjectError(f'[weights.{name}]: no master named {master}')
    output = (source.root / args.output).resolve()
    output.mkdir(parents=True, exist_ok=True)
    drafted = []
    for name in names:
        ufo, factors, report = draft_master(source, name, tables[name], output)
        drafted.append((name, tables[name]['wght'], ufo))
        print(f'{name} (wght {tables[name]["wght"]}): position x {factors["x"]:+.2f}, '
              f'y {factors["y"]:+.2f} between {" and ".join(tables[name]["between"])}')
        print(f'  drafted {len(report["drafted"])} glyphs, '
              f'copied {len(report["copied"])} that are not compatible, '
              f'{len(report["collapsed"])} with a contour that turned inside out')
        for key, label in (('copied', 'not compatible'), ('collapsed', 'inside out')):
            if report[key]:
                print(f'  {label}: {" ".join(report[key])}')
        print(f'  {ufo.relative_to(source.root)}')
    designspace = write_designspace(source, drafted, output)
    print(designspace.relative_to(source.root))
    if args.build:
        print(build(designspace).relative_to(source.root))
    return 0


if __name__ == '__main__':
    sys.exit(main())
