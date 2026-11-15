#!/usr/bin/env python3
"""Place the accent anchors and build the accented letters of a project.

    fgtools place-anchors [--set NAME | --characters TEXT] [--master NAME]
                          [--include-green] [--write]
    fgtools build-accented-letters [--set NAME | --characters TEXT]
                                   [--glyphs "NAMES"] [--replace-drafts] [--write]

Both commands print what they will do. They change the sources only with
--write.

`place-anchors` adds the anchors that are missing: `top` and `bottom` on the
base letters of the set, `_top` and `_bottom` on the marks. An anchor that is in
the sources is the designer's and does not change. A missing anchor comes
from the accented letters that are in the sources: the offset of a mark is
`anchor of the base - anchor of the mark`, and the two anchors are fitted to
the offsets with medians. A glyph that no accented letter uses gets its
anchor from the outline: the center of the top or the bottom of a base on
its metric line, and the center of a mark on the line it is drawn over.
Purple and red accented letters are not used as evidence.

`build-accented-letters` adds the accented letters of a set that are not in
the sources. Each one is a composite of the base and the mark, at the offset
that the anchors give, and is marked purple. It is added to every master, to
`contents.plist` and to `public.glyphOrder`. With --replace-drafts, the
command also sets the components of the accented letters that are purple in
every master. It does not change a glyph of another color.

The command does not build these letters, and lists them:

- a letter with two marks;
- a caron on d, t, l or L, which is an apostrophe form beside the letter;
- a comma accent on g, which is a turned comma over the letter.
"""
from __future__ import annotations

import argparse
import plistlib
import re
import statistics
import sys
import tomllib
import unicodedata
from collections import Counter
from pathlib import Path

from fontTools.ufoLib.filenames import userNameToFileName

from fontgarden import project
from fontgarden.accent_placement import CARON_BESIDE, DOTLESS, LINE_TOLERANCE, MARKS, Font, observations
from fontgarden.status import color_name

SETS = Path(__file__).with_name('accented_letters.toml')
DEFAULT_SET = 'google-fonts-latin-core'
PURPLE = '0.54,0.44,0.88,1'
# Unicode gives a cedilla for these letters, and fonts draw a comma accent.
COMMA_FOR_CEDILLA = 'GgKkLlNnRr'
SIDES = ('top', 'bottom')
# The names of the marks in glyph names: Aacute, kcommaaccent.
MARK_NAMES = {0x0300: 'grave', 0x0301: 'acute', 0x0302: 'circumflex', 0x0303: 'tilde',
              0x0304: 'macron', 0x0306: 'breve', 0x0307: 'dotaccent', 0x0308: 'dieresis',
              0x030A: 'ring', 0x030B: 'hungarumlaut', 0x030C: 'caron', 0x0323: 'dotbelow',
              0x0326: 'commaaccent', 0x0327: 'cedilla', 0x0328: 'ogonek'}


def sets():
    return tomllib.loads(SETS.read_text())['sets']


def parts_of(character):
    """(base character, combining mark, side) of an accented letter, or the
    reason that the command does not build it."""
    base, *marks = unicodedata.normalize('NFD', character)
    if not marks or not unicodedata.name(base, '').startswith('LATIN'):
        return 'not a Latin letter with a mark'
    if len(marks) > 1:
        return 'two marks'
    mark = ord(marks[0])
    if mark not in MARKS:
        return f'mark U+{mark:04X} is not in the mark table'
    if mark == 0x0327 and base in COMMA_FOR_CEDILLA:
        mark = 0x0326
    if mark == 0x030C and base in CARON_BESIDE:
        return 'the caron is an apostrophe form beside the letter'
    if mark == 0x0326 and base == 'g':
        return 'the comma accent is a turned comma over the letter'
    return base, mark, MARKS[mark][0]


class Master:
    """One master: its font, its colors and the anchors of its accents."""

    def __init__(self, name, ufo, colors, grid, characters=''):
        self.name, self.ufo, self.colors, self.grid = name, Path(ufo), colors, grid
        # The base letters that the accented letters of the set use.
        self.wanted = set()
        for character in characters:
            parts = parts_of(character)
            if isinstance(parts, tuple):
                self.wanted.add(DOTLESS.get(parts[0], parts[0]) if parts[2] == 'top' else parts[0])
        self.font = Font.from_ufo(ufo)
        self.contents = plistlib.loads((self.ufo / 'glyphs/contents.plist').read_bytes())
        self.rows = [row for row in observations(self.font)
                     if self.color(row['glyph']) not in ('purple', 'red')]
        self.anchors = {side: self.fit(side) for side in SIDES}

    def color(self, glyph):
        return color_name(self.font.mark_colors.get(glyph), self.colors)

    def snap(self, value):
        return int(round(value / self.grid) * self.grid)

    def bases(self):
        """The glyphs of the base letters that the set uses."""
        for name, code_point in self.font.code_points.items():
            if chr(code_point) in self.wanted and not self.font.shape(name).empty:
                yield name

    def marks(self, side):
        """The glyphs that are a mark of this side: a combining mark, or a
        glyph that an accented letter uses as its mark."""
        found = {row['mark'] for row in observations(self.font) if row['side'] == side}
        for name, code_point in self.font.code_points.items():
            if MARKS.get(code_point, (None,))[0] == side and not self.font.shape(name).empty:
                found.add(name)
        return found

    def outline_anchor(self, glyph, side, mark):
        """The anchor of a glyph from its outline only."""
        font, shape = self.font, self.font.shape(glyph)
        if not mark:
            return font.reference_x(glyph, side, 'band'), font.reference_y(glyph, side, 'line')
        x = (shape.left + shape.right) / 2
        if side == 'bottom':
            return x, 0
        tolerance = LINE_TOLERANCE * font.units_per_em
        return x, max((line for line in font.lines if line <= shape.bottom + tolerance),
                      default=min(font.lines, default=0))

    def fit(self, side):
        """{glyph: (x, y, source)} for the bases and the marks of one side.

        The key of a mark has the prefix "_". The source is "sources",
        "N accented letters" or "outline".
        """
        font = self.font
        members = [row for row in self.rows if row['side'] == side]
        bases = set(self.bases()) | {row['base'] for row in members}
        marks = self.marks(side) | {row['mark'] for row in members}
        base, mark, fixed_base, fixed_mark = {}, {}, set(), set()
        for name in bases:
            if side in font.anchors.get(name, {}):
                base[name] = font.anchors[name][side]
                fixed_base.add(name)
            else:
                base[name] = self.outline_anchor(name, side, mark=False)
        for name in marks:
            if '_' + side in font.anchors.get(name, {}):
                mark[name] = font.anchors[name]['_' + side]
                fixed_mark.add(name)
            else:
                mark[name] = self.outline_anchor(name, side, mark=True)
        for _ in range(4):
            for name in marks - fixed_mark:
                found = [row for row in members if row['mark'] == name]
                if found:
                    mark[name] = tuple(statistics.median(base[row['base']][axis] - row[key]
                                                         for row in found)
                                       for axis, key in enumerate(('dx', 'dy')))
            for name in bases - fixed_base:
                found = [row for row in members if row['base'] == name]
                if found:
                    base[name] = tuple(statistics.median(row[key] + mark[row['mark']][axis]
                                                         for row in found)
                                       for axis, key in enumerate(('dx', 'dy')))
        result = {}
        for prefix, values, fixed, key in (('', base, fixed_base, 'base'), ('_', mark, fixed_mark, 'mark')):
            for name, (x, y) in values.items():
                count = sum(1 for row in members if row[key] == name)
                source = ('sources' if name in fixed
                          else f'{count} accented letter{"s" if count > 1 else ""}' if count
                          else 'outline')
                result[prefix + name] = (self.snap(x), self.snap(y), source)
        return result

    def missing_anchors(self, include_green=False):
        """[(glyph, anchor name, x, y, source)] to write, and the green glyphs left out."""
        found, green = [], []
        for side in SIDES:
            for key, (x, y, source) in sorted(self.anchors[side].items()):
                if source == 'sources':
                    continue
                glyph = key.lstrip('_') if key.startswith('_') else key
                anchor = ('_' if key.startswith('_') else '') + side
                if self.color(glyph) == 'green' and not include_green:
                    green.append(f'{glyph} `{anchor}`')
                else:
                    found.append((glyph, anchor, x, y, source))
        return found, green

    def mark_glyph(self, base_character, mark, side):
        """The glyph that the font uses for a combining mark on a letter of this case."""
        upper = base_character.isupper()
        counts = Counter()
        for row in self.rows:
            parts = parts_of(chr(self.font.code_points[row['glyph']]))
            if isinstance(parts, tuple) and parts[1] == mark:
                counts[row['mark'], parts[0].isupper() == upper] += 1
        for same_case in (True, False):
            choice = [(count, name) for (name, case), count in counts.items() if case == same_case]
            if choice:
                return max(choice)[1]
        names = self.font.names
        for code_point in (mark, MARKS[mark][1]):
            name = names.get(code_point)
            if name and not self.font.shape(name).empty:
                if upper and name + '.case' in self.font.advances:
                    return name + '.case'
                return name
        return None

    def composite(self, character):
        """(base glyph, mark glyph, dx, dy) of an accented letter, or the reason it cannot be built."""
        parts = parts_of(character)
        if isinstance(parts, str):
            return parts
        base_character, mark, side = parts
        if side == 'top':
            base_character = DOTLESS.get(base_character, base_character)
        base = self.font.names.get(ord(base_character))
        if base is None or self.font.shape(base).empty:
            return f'the base {base_character} (U+{ord(base_character):04X}) is not drawn'
        mark_glyph = self.mark_glyph(parts[0], mark, side)
        if mark_glyph is None:
            return f'the mark U+{mark:04X} is not drawn'
        anchors = self.anchors[side]
        if base not in anchors or '_' + mark_glyph not in anchors:
            return f'no `{side}` anchors for {base} and {mark_glyph}'
        (base_x, base_y, _), (mark_x, mark_y, _) = anchors[base], anchors['_' + mark_glyph]
        return base, mark_glyph, base_x - mark_x, base_y - mark_y


def masters(root=None, only=None, characters=''):
    layout = project.load(root)
    design = layout.design() if layout.design_config.is_file() else {}
    colors = design.get('colors', {'purple': {'rgba': [[0.54, 0.44, 0.88, 1]]}})
    grid = design.get('grid', {}).get('source', 1)
    return [Master(name, layout.ufo(name), colors, grid, characters)
            for name in ([only] if only else layout.masters)], design


def number(value):
    return str(int(value)) if float(value) == int(value) else str(value)


def add_anchor(path, name, x, y):
    """Add one anchor element to a GLIF file, after the outline and the other anchors."""
    text = path.read_text()
    line = f'\t<anchor name="{name}" x="{number(x)}" y="{number(y)}"/>\n'
    anchors = list(re.finditer(r'\t<anchor [^>]*/>\n', text))
    if anchors:
        position = anchors[-1].end()
    elif '</outline>\n' in text:
        position = text.index('</outline>\n') + len('</outline>\n')
    elif re.search(r'\t<outline/>\n', text):
        position = re.search(r'\t<outline/>\n', text).end()
    else:
        raise ValueError(f'{path}: no outline element')
    path.write_text(text[:position] + line + text[position:])


def place_anchors(root=None, master=None, characters='', include_green=False, write=False):
    """Add the `top`, `bottom`, `_top` and `_bottom` anchors that are missing
    on the base letters and the marks of a set of accented letters."""
    found, _ = masters(root, master, characters)
    for item in found:
        anchors, green = item.missing_anchors(include_green)
        print(f'{item.name}: {len(anchors)} anchors {"added" if write else "to add"}')
        for glyph, anchor, x, y, source in anchors:
            print(f'  {glyph} `{anchor}` {x}, {y}  (from {"the " if source == "outline" else ""}{source})')
            if write:
                add_anchor(item.ufo / 'glyphs' / item.contents[glyph], anchor, x, y)
        if green:
            print(f'  {len(green)} anchors of green glyphs are left out (--include-green adds them): '
                  + ', '.join(green))
    if not write:
        print('Nothing is written. Use --write to change the sources.')
    return 0


def component_lines(base, mark, dx, dy):
    offset = ''.join(f' {key}="{number(value)}"' for key, value in (('xOffset', dx), ('yOffset', dy))
                     if value)
    return f'\t\t<component base="{base}"/>\n\t\t<component base="{mark}"{offset}/>\n'


def glif_text(name, code_point, advance, components, purple, label):
    lib = (f'\t\t\t<key>com.runebender.markLabel</key>\n\t\t\t<string>purple</string>\n' if label else '') \
        + f'\t\t\t<key>public.markColor</key>\n\t\t\t<string>{purple}</string>\n'
    return ('<?xml version="1.0" encoding="UTF-8"?>\n'
            f'<glyph name="{name}" format="2">\n'
            f'\t<unicode hex="{code_point:04X}"/>\n'
            f'{advance}'
            f'\t<outline>\n{components}\t</outline>\n'
            f'\t<lib>\n\t\t<dict>\n{lib}\t\t</dict>\n\t</lib>\n</glyph>\n')


def register(ufo, name, file_name):
    """Add a glyph to contents.plist and to public.glyphOrder, as text."""
    path = ufo / 'glyphs/contents.plist'
    text = path.read_text()
    keys = re.findall(r'<key>(.*?)</key>', text)
    entry = f'\t<key>{name}</key>\n\t<string>{file_name}</string>\n'
    following = next((key for key in keys if key > name), None) if keys == sorted(keys) else None
    position = text.index(f'\t<key>{following}</key>') if following else text.rindex('</dict>')
    path.write_text(text[:position] + entry + text[position:])
    path = ufo / 'lib.plist'
    if not path.is_file():
        return
    text = path.read_text()
    order = re.search(r'<key>public\.glyphOrder</key>\s*<array>.*?(\n[ \t]*)</array>', text, re.S)
    if order:
        indent = re.search(r'\n([ \t]*)<string>', order.group(0))
        line = f'\n{indent.group(1) if indent else "\t\t"}<string>{name}</string>'
        path.write_text(text[:order.start(1)] + line + text[order.start(1):])


def plan(found, characters, glyphs=None, replace_drafts=False):
    """Decide what to do with each character.

    Returns (new, replaced, present, skipped). `new` and `replaced` hold
    (glyph name, character, {master name: (base, mark, dx, dy)}).
    """
    first = found[0]
    new, replaced, present, skipped = [], [], [], []
    taken = set().union(*(item.contents for item in found))
    for character in dict.fromkeys(characters):
        code_point = ord(character)
        existing = first.font.names.get(code_point)
        parts = parts_of(character)
        name = existing or (parts[0] + MARK_NAMES[parts[1]] if isinstance(parts, tuple) else None)
        if not name or (not existing and name in taken):
            name = f'uni{code_point:04X}'
        if glyphs and name not in glyphs:
            continue
        if existing:
            draft = all(item.color(existing) == 'purple' for item in found)
            if not (replace_drafts and draft):
                present.append(existing)
                continue
        parts = {item.name: item.composite(character) for item in found}
        reason = next((value for value in parts.values() if isinstance(value, str)), None)
        if reason:
            skipped.append((character, name, reason))
        elif existing:
            replaced.append((name, character, parts))
        else:
            new.append((name, character, parts))
    return new, replaced, present, skipped


def build_accented_letters(root=None, characters=None, glyphs=None, replace_drafts=False, write=False):
    """Add the accented letters of a set as purple composites."""
    found, design = masters(root, characters=characters)
    purple = ','.join(number(value) for value in design['colors']['purple']['rgba'][0]) \
        if design.get('colors', {}).get('purple', {}).get('rgba') else PURPLE
    new, replaced, present, skipped = plan(found, characters, glyphs, replace_drafts)
    for title, rows in ((f'accented letters {"added" if write else "to add"}', new),
                        (f'purple drafts {"set again" if write else "to set again"}', replaced)):
        print(f'{len(rows)} {title}')
        for name, character, parts in rows:
            print(f'  {name} {character}: ' + '; '.join(
                f'{master} {base} + {mark} at {number(dx)}, {number(dy)}'
                for master, (base, mark, dx, dy) in parts.items()))
    print(f'{len(present)} accented letters are in the sources and do not change')
    if skipped:
        print(f'{len(skipped)} accented letters are not built:')
        for character, name, reason in skipped:
            print(f'  {name} {character}: {reason}')
    if not write:
        print('Nothing is written. Use --write to change the sources.')
        return 0
    for item in found:
        files = {value.lower() for value in item.contents.values()}
        for name, character, parts in new:
            base, mark, dx, dy = parts[item.name]
            base_text = (item.ufo / 'glyphs' / item.contents[base]).read_text()
            advance = re.search(r'\t<advance [^>]*/>\n', base_text)
            file_name = userNameToFileName(name, existing=files, suffix='.glif')
            files.add(file_name.lower())
            (item.ufo / 'glyphs' / file_name).write_text(glif_text(
                name, ord(character), advance.group(0) if advance else '',
                component_lines(base, mark, dx, dy), purple,
                'com.runebender.markLabel' in base_text))
            register(item.ufo, name, file_name)
        for name, character, parts in replaced:
            path = item.ufo / 'glyphs' / item.contents[name]
            text = path.read_text()
            outline = re.search(r'\t<outline>\n.*?\t</outline>\n', text, re.S)
            path.write_text(text[:outline.start()] + '\t<outline>\n' + component_lines(*parts[item.name])
                            + '\t</outline>\n' + text[outline.end():])
    return 0


def add_set(parser):
    parser.add_argument('--set', default=DEFAULT_SET, choices=sorted(sets()),
                        help=f'a set of accented_letters.toml (default: {DEFAULT_SET})')
    parser.add_argument('--characters', help='the accented letters, in place of a set')


def main_place():
    parser = argparse.ArgumentParser(prog='fgtools place-anchors', description=place_anchors.__doc__)
    parser.add_argument('--master', help='one master (default: all)')
    add_set(parser)
    parser.add_argument('--include-green', action='store_true',
                        help='also add anchors to green glyphs')
    parser.add_argument('--write', action='store_true', help='change the sources')
    args = parser.parse_args()
    return place_anchors(master=args.master, characters=args.characters or sets()[args.set],
                         include_green=args.include_green, write=args.write)


def main_build():
    parser = argparse.ArgumentParser(prog='fgtools build-accented-letters',
                                     description=build_accented_letters.__doc__)
    add_set(parser)
    parser.add_argument('--glyphs', default='', help='build only these glyph names, space-separated')
    parser.add_argument('--replace-drafts', action='store_true',
                        help='also set the components of the purple accented letters again')
    parser.add_argument('--write', action='store_true', help='change the sources')
    args = parser.parse_args()
    characters = args.characters or sets()[args.set]
    return build_accented_letters(characters=characters, glyphs=set(args.glyphs.split()),
                                  replace_drafts=args.replace_drafts, write=args.write)


if __name__ == '__main__':
    sys.exit(main_build())
