#!/usr/bin/env python3
"""Draft the masters of the large optical size from the masters of the small one.

usage:
  fgtools draft-optical-size            draft every master into output/
  fgtools draft-optical-size Regular    draft the named masters
  fgtools draft-optical-size --write    also put the drafts into sources/

The rule is a table of CONTEXT.md:

  [optical_size]
  from = 14       # pt: the masters that are drawn
  to = 144        # pt: the masters that are calculated
  side = 24       # units that each side of a glyph loses
  complete = 72   # pt: the size at which the change is complete

Each side of a glyph loses `side` units. The outline, the anchors and the
marks move left by `side`, and the advance gets smaller by two times `side`.
On a joining side of an Arabic letter the points on the edge of the advance
stay on that edge, so the join gets shorter. Where a join or a sidebearing is
too short to lose `side`, that side loses less. A glyph without an advance does not change. The kerning does not change.

The drafts are written to output/optical-size/, which Git ignores. With
--write, each glyph of a large master that is calculated, and not corrected
by hand, is replaced and gets the purple mark and the digest of its outline, and the designspace of the
project gets the map of the axis. Use Git to undo it. The report lists the
glyphs that the rule does not fit.
"""
from __future__ import annotations

import argparse
import hashlib
import re
import shutil
import sys
import xml.etree.ElementTree as ET
from pathlib import Path

from fgtools import project
from fgtools.draft_weights import PURPLE, number, set_purple

OUTPUT = 'output/optical-size'
ADVANCE = re.compile(r'(<advance\b[^>]*?\bwidth=")([^"]*)(")')
POINT = re.compile(r'(<point x=")(-?[\d.]+)(" y=")(-?[\d.]+)("[^>]*/>)')
ANCHOR = re.compile(r'(<anchor\b[^>]*?\bx=")(-?[\d.]+)(")')
COMPONENT = re.compile(r'<component\b[^>]*/>')
JOINS = {'init': ('left',), 'medi': ('left', 'right'), 'fina': ('right',)}


def advance_of(text):
    found = ADVANCE.search(text)
    return float(found.group(2)) if found else 0.0


def body(text):
    """A GLIF text without its lib, which holds the mark color."""
    return re.sub(r'<lib>.*?</lib>', '', text, flags=re.S)


CALCULATED = 'garden.font.calculated'


def digest(text):
    return hashlib.sha1(body(text).encode()).hexdigest()


def stamp(text):
    """A GLIF text with the digest of its outline in its lib. A glyph whose
    outline still has that digest is calculated: nobody changed it by hand."""
    text = re.sub(rf'\s*<key>{re.escape(CALCULATED)}</key>\s*<string>[^<]*</string>', '', text)
    entry = f'\t\t\t<key>{CALCULATED}</key>\n\t\t\t<string>{digest(text)}</string>\n'
    return re.sub(r'(<lib>\s*<dict>\n)', rf'\g<1>{entry}', text, count=1)


def calculated(text):
    """True when a glyph has the digest of a draft and its outline did not change since."""
    found = re.search(rf'<key>{re.escape(CALCULATED)}</key>\s*<string>([^<]*)</string>', text)
    return bool(found) and found.group(1) == digest(text)


def joining_sides(name):
    """The sides on which an Arabic form joins the next letter, from its name."""
    if '-ar' not in name:
        return ()
    for part in name.split('.')[1:]:
        if part in JOINS:
            return JOINS[part]
    return ()


def points_of(text):
    """The contours of a GLIF text: lists of (x, y, on curve)."""
    return [[(float(x), float(y), 'type="' in rest) for _, x, _, y, rest in POINT.findall(contour)]
            for contour in re.findall(r'<contour>.*?</contour>', text, re.S)]


def losses(name, glyphs, side, grid=8, seen=()):
    """(left, right, note): the units that each side of a glyph loses.

    A free side loses `side`, or less where the sidebearing is smaller than
    `side` and one grid step. A joining side loses `side` where each line or
    handle that goes from the edge of the advance into the letter stays at
    least `grid` long, and less where one of them is shorter. A composite
    loses what its first part with an advance loses.
    """
    text = glyphs[name]
    contours = points_of(text)
    width = advance_of(text)
    joins = joining_sides(name)
    # A glyph whose own points do not reach the edge has its join in a part.
    own = any(x <= 0 or x >= width for contour in contours for x, _, _ in contour)
    if not contours or (joins and not own and '<component' in text):
        for base in re.findall(r'<component\b[^>]*?\bbase="([^"]*)"', text):
            if base in glyphs and base not in seen and advance_of(glyphs[base]):
                return losses(base, glyphs, side, grid, seen + (name,))
        return side, side, None
    found, note = {'left': side, 'right': side}, None
    xs = [x for contour in contours for x, _, _ in contour]
    bearings = {'left': min(xs), 'right': width - max(xs)}
    for which, on_edge in (('left', lambda x: x <= 0), ('right', lambda x: x >= width)):
        if which not in joins:
            # A free side keeps a sidebearing of one grid step, so that the ink stays in its advance.
            found[which] = max(0, min(side, (bearings[which] - grid) // grid * grid))
            continue
        if not any(on_edge(x) for contour in contours for x, _, _ in contour):
            note = 'the name is a joining form, but no point is on the edge of the advance'
            continue
        for contour in contours:
            for (x0, y0, _), (x1, y1, _) in zip(contour, contour[1:] + contour[:1]):
                if on_edge(x0) != on_edge(x1):
                    # A calculated master can have a join that is a few units off level.
                    if abs(y0 - y1) > grid:
                        note = 'a join does not leave the edge of the advance in a horizontal line'
                        found[which] = 0
                    else:
                        room = (abs(x1 - x0) - grid) // grid * grid
                        found[which] = max(0, min(found[which], room))
    return found['left'], found['right'], note


def draft_glyph(name, glyphs, side, shared=None):
    """The GLIF text of one glyph at the large size, and a note or None.
    `glyphs` is {glyph name: GLIF text} of the small master. `shared` is
    {glyph name: (left, right)}: the losses that the masters of one weight have
    in common, so that a grade keeps every advance at the large size too."""
    text = glyphs[name]
    width = advance_of(text)
    if width == 0:
        return text, None
    if width <= 2 * side:
        return text, f'advance {number(width)} is too small'
    left, right, note = losses(name, glyphs, side)
    if shared and name in shared:
        left, right = shared[name]
    joins = joining_sides(name) if points_of(text) else ()
    if (left, right) != (side, side) and not note and joining_sides(name):
        note = f'a join or a sidebearing is short: the sides lose {number(left)} and {number(right)}'

    def moved(x):
        if 'left' in joins and x <= 0:
            return x
        if 'right' in joins and x >= width:
            return x - left - right
        return x - left

    def component(match):
        tag = match.group(0)
        base = re.search(r'\bbase="([^"]*)"', tag).group(1)
        # A part with an advance moves with its own draft. A part without one does not move.
        own = shared[base][0] if shared and base in shared else losses(base, glyphs, side)[0]
        rest = left - (own if base in glyphs and advance_of(glyphs[base]) else 0)
        if not rest:
            return tag
        offset = re.search(r'\bxOffset="(-?[\d.]+)"', tag)
        if offset:
            return tag.replace(offset.group(0), f'xOffset="{number(float(offset.group(1)) - rest)}"')
        return tag.replace('/>', f' xOffset="{number(-rest)}"/>')

    text = POINT.sub(lambda p: f'{p.group(1)}{number(moved(float(p.group(2))))}{p.group(3)}'
                               f'{p.group(4)}{p.group(5)}', text)
    text = COMPONENT.sub(component, text)
    text = ANCHOR.sub(lambda a: f'{a.group(1)}{number(moved(float(a.group(2))))}{a.group(3)}', text)
    text = ADVANCE.sub(lambda a: f'{a.group(1)}{number(width - left - right)}{a.group(3)}', text, count=1)
    return text, note


def glyph_names(texts):
    return {file: re.search(r'<glyph name="([^"]*)"', text).group(1) for file, text in texts.items()}


def draft_master(small, large, side, output, shared=None):
    """Write the draft of one large master into `output`. Returns (path, report)."""
    target = output / large.name
    if target.exists():
        shutil.rmtree(target)
    shutil.copytree(large, target)
    texts = {path.name: path.read_text() for path in sorted((small / 'glyphs').glob('*.glif'))}
    names = glyph_names(texts)
    glyphs = {names[file]: text for file, text in texts.items()}
    report = {'drafted': 0, 'unchanged': 0, 'notes': []}
    for file, text in texts.items():
        draft, note = draft_glyph(names[file], glyphs, side, shared)
        (target / 'glyphs' / file).write_text(draft)
        report['drafted' if draft != text else 'unchanged'] += 1
        if note:
            report['notes'].append(f'{names[file]}: {note}')
    return target, report


def set_map(root, design, name):
    """Give the opsz axis of a designspace the map of the rule."""
    axis = root.find('axes/axis[@tag="opsz"]')
    if axis is None:
        raise project.ProjectError(f'{name} has no opsz axis')
    for old in axis.findall('map'):
        axis.remove(old)
    low, high, complete = design['from'], design['to'], design['complete']
    for size, location in ((low, low), (complete, high), (high, high)):
        ET.SubElement(axis, 'map', {'input': number(size), 'output': number(location)})


def shared_losses(ufos, side):
    """{glyph name: (left, right)}: the smallest losses of each glyph in the given masters."""
    found = {}
    for ufo in ufos:
        texts = {path.name: path.read_text() for path in (ufo / 'glyphs').glob('*.glif')}
        names = glyph_names(texts)
        glyphs = {names[file]: text for file, text in texts.items()}
        for name in glyphs:
            if advance_of(glyphs[name]) > 2 * side:
                left, right, _ = losses(name, glyphs, side)
                old = found.get(name, (side, side))
                found[name] = (min(old[0], left), min(old[1], right))
    return found


def write_sources(source, design, drafted, replace_all=False, grade_bases=None):
    """Put the drafts into the large masters of the project. Returns (written, kept).

    Each written glyph gets the digest of its outline. A glyph is replaced
    when its outline still has that digest, or when it is still equal to the
    small master. Any other glyph has a correction of its own, and it stays.
    `replace_all` replaces every glyph.
    """
    rgba = source.design().get('colors', {}).get('purple', {}).get('rgba')
    purple = ','.join(number(value) for value in rgba[-1]) if rgba else PURPLE
    written, kept = 0, []
    grade_bases = grade_bases or {}
    # Resolve neutral display advances after writing any neutral drafts.
    for small, large, draft in sorted(drafted, key=lambda item: item[1] in grade_bases):
        for path in sorted((draft / 'glyphs').glob('*.glif')):
            target, origin, text = large / 'glyphs' / path.name, small / 'glyphs' / path.name, path.read_text()
            if not target.is_file():
                continue
            present = target.read_text()
            replace = replace_all or calculated(present) or body(present) == body(origin.read_text())
            if not replace:
                kept.append(f'{large.stem}: {path.stem}')
                text = present
            if large in grade_bases:
                base = grade_bases[large] / 'glyphs' / path.name
                if base.is_file():
                    width = advance_of(base.read_text())
                    if advance_of(text) != width:
                        if ADVANCE.search(text):
                            text = ADVANCE.sub(lambda m: f'{m[1]}{number(width)}{m[3]}', text, count=1)
                        else:
                            text = text.replace('</glyph>', f'\t<advance width="{number(width)}"/>\n</glyph>', 1)
            if replace and (body(present) != body(text) or not calculated(present)):
                target.write_text(stamp(set_purple(text, purple)))
                written += 1
            elif not replace and text != present:
                target.write_text(text)
                written += 1
    tree = ET.parse(source.designspace)
    set_map(tree.getroot(), design, source.designspace.name)
    ET.indent(tree, space='  ')
    tree.write(source.designspace, encoding='UTF-8', xml_declaration=True)
    return written, kept


def main():
    parser = argparse.ArgumentParser(prog='fgtools draft-optical-size', description=__doc__,
                                     formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument('masters', nargs='*', help='the small masters to draft from (default: all)')
    parser.add_argument('--write', action='store_true', help='put the drafts into sources/')
    parser.add_argument('--all', action='store_true', help='with --write: also replace the glyphs that were corrected by hand')
    parser.add_argument('--output', default=OUTPUT, help=f'output directory (default: {OUTPUT})')
    args = parser.parse_args()
    source = project.load()
    design = source.design().get('optical_size')
    if not design:
        raise project.ProjectError(f'{source.design_config} has no [optical_size] table')
    suffix = f' {design["to"]}pt'
    pairs = {name: name + suffix for name in source.masters if name + suffix in source.ufos}
    for name in args.masters:
        if name not in pairs:
            raise project.ProjectError(f'no master named {name}{suffix}')
    output = (source.root / args.output).resolve()
    output.mkdir(parents=True, exist_ok=True)
    drafted = []
    # The masters of one weight, with its grades, lose the same on each side of a glyph.
    weight_of = lambda name: name.split(' GRAD')[0]
    groups = {}
    for name in pairs:
        groups.setdefault(weight_of(name), []).append(source.ufo(name))
    common = {weight: shared_losses(ufos, design['side']) for weight, ufos in groups.items()}
    for name in args.masters or pairs:
        shared = common[weight_of(name)]
        ufo, report = draft_master(source.ufo(name), source.ufo(pairs[name]), design['side'], output, shared)
        print(f'{pairs[name]}: {report["drafted"]} glyphs drafted, {report["unchanged"]} without change')
        for note in report['notes']:
            print(f'  {note}')
        drafted.append((source.ufo(name), source.ufo(pairs[name]), ufo))
    if args.write:
        grade_bases = {
            source.ufo(large): source.ufo(pairs[weight_of(name)])
            for name, large in pairs.items()
            if weight_of(name) != name and weight_of(name) in pairs
        }
        written, kept = write_sources(source, design, drafted, args.all, grade_bases)
        print(f'{written} glyphs written to sources/')
        for line in kept:
            print(f'  kept, corrected by hand: {line}')
    return 0


if __name__ == '__main__':
    sys.exit(main())
