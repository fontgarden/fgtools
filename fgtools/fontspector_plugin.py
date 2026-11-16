#!/usr/bin/env python3
"""Fontspector plugin with the Font.Garden profile.

The profile `fontgarden` includes the Google Fonts profile and adds the
Font.Garden requirements:

    fontgarden/unitsperem  the em is 1024 units
    fontgarden/grid        every master of a variable font, or a static font
                           without a variable font, has its on-curve points
                           and advance widths on the 2-unit grid
    fontgarden/vendor_id   the OS/2 vendor ID is FTGD
    fontgarden/license     the name table gives the OFL 1.1 and its URL
    fontgarden/visible_ink         every visible character has ink
    fontgarden/mark_glyphs         combining marks have the mark class and no advance
    fontgarden/marks_attach        combining marks attach to their bases
    fontgarden/static_stat_weight  a static font has its own weight in STAT
    fontgarden/stacked_marks       stacked marks do not touch
    fontgarden/arabic_joins        Arabic letters join without gaps
    fontgarden/hebrew_marks_clear  Hebrew accents and meteg clear the vowel point
    fontgarden/precomposed_match   a precomposed letter matches its sequence

A project adds the checks that only its font needs in
sources/fontspector_checks.py, written as the checks here. They run in the
same profile, in the section "This font".

`fgtools qa` runs Fontspector with this plugin. Add a requirement as a check
here, with the reason in its rationale. The Rust version of this profile is
https://github.com/fontgarden/fontspector-fontgarden.
"""
from __future__ import annotations

import importlib.util
import io
import itertools
import os
from pathlib import Path
import unicodedata

from fontspectorapi import FAIL, PASS, SKIP, CheckContext, CheckStatuses, Message, Plugin
from fontspectorapi import ProfileDefinition, check, plugin_main
from fontTools.ttLib import TTFont
from fontTools.varLib import instancer

from fgtools import shaped_font

UNITS_PER_EM = 1024
GRID = 2
VENDOR_ID = 'FTGD'
LICENSE = 'SIL Open Font License, Version 1.1'
LICENSE_URL = 'https://openfontlicense.org'
ARTICLE = 'https://elih.net/blog/virtua-grotesk/'
# Minimum distances between marks, in units of the 1024-unit em.
STACKED_MARK_GAP = 16
CANTILLATION_GAP = 30
METEG_GAP = 24
LATIN_ABOVE = [0x0300, 0x0301, 0x0302, 0x0303, 0x0304, 0x0306, 0x0307, 0x0308, 0x030A, 0x030B, 0x030C]
TATWEEL = '\u0640'
DOTTED_CIRCLE = '\u25CC'
# `fgtools qa` gives the plugin the root of the project in this variable. A
# project can add its own checks in this file.
PROJECT_ROOT = 'FGTOOLS_PROJECT'
PROJECT_CHECKS = 'sources/fontspector_checks.py'


@check(id='fontgarden/unitsperem', title='The em is 1024 units',
       rationale='The Font.Garden grid divides the em by powers of two. 1024 is 2 to the '
                 'power 10, so the grids of 2, 8 and 64 units and the vertical metrics '
                 'are whole numbers.',
       proposal=ARTICLE)
def units_per_em(font_path: Path, context: CheckContext) -> CheckStatuses:
    upm = TTFont(font_path)['head'].unitsPerEm
    if upm == UNITS_PER_EM:
        yield PASS, Message('ok', f'unitsPerEm is {upm}.')
    else:
        yield FAIL, Message('wrong-upm', f'unitsPerEm is {upm}, not {UNITS_PER_EM}.')


@check(id='fontgarden/vendor_id', title='The OS/2 vendor ID is FTGD',
       rationale='FTGD is the registered vendor ID of Font.Garden.')
def vendor_id(font_path: Path, context: CheckContext) -> CheckStatuses:
    found = TTFont(font_path)['OS/2'].achVendID
    if found == VENDOR_ID:
        yield PASS, Message('ok', f'The vendor ID is {found}.')
    else:
        yield FAIL, Message('wrong-vendor-id', f'The vendor ID is "{found}", not {VENDOR_ID}.')


@check(id='fontgarden/license', title='The name table gives the OFL 1.1',
       rationale='Font.Garden fonts are licensed under the SIL Open Font License 1.1. '
                 'Name ID 13 gives the license and name ID 14 its URL.',
       proposal=LICENSE_URL)
def license_names(font_path: Path, context: CheckContext) -> CheckStatuses:
    name = TTFont(font_path)['name']
    description, url = name.getDebugName(13) or '', name.getDebugName(14) or ''
    failed = False
    if LICENSE not in description:
        failed = True
        yield FAIL, Message('license-description', f'Name ID 13 does not contain "{LICENSE}".')
    if url != LICENSE_URL:
        failed = True
        yield FAIL, Message('license-url', f'Name ID 14 is "{url}", not {LICENSE_URL}.')
    if not failed:
        yield PASS, Message('ok', 'The name table gives the OFL 1.1 and its URL.')


def master_locations(font):
    """User-space locations of the masters of a variable font: the default
    location and the peak of each gvar tuple."""
    axes = {a.axisTag: a for a in font['fvar'].axes}
    avar = font['avar'].segments if 'avar' in font else {}
    peaks = {tuple(sorted((tag, value[1]) for tag, value in v.axes.items()))
             for variations in font['gvar'].variations.values() for v in variations}
    locations = [{tag: a.defaultValue for tag, a in axes.items()}]
    for peak in sorted(peaks):
        location = {tag: a.defaultValue for tag, a in axes.items()}
        for tag, value in peak:
            value = invert(avar.get(tag), value)
            a = axes[tag]
            span = a.maxValue - a.defaultValue if value > 0 else a.defaultValue - a.minValue
            location[tag] = a.defaultValue + value * span
        locations.append(location)
    return locations


def invert(segments, value):
    """The normalized value that the avar segment map maps to `value`."""
    if not segments:
        return value
    pairs = sorted(segments.items(), key=lambda pair: pair[1])
    for (a, b), (c, d) in zip(pairs, pairs[1:]):
        if b <= value <= d:
            return a if d == b else a + (value - b) * (c - a) / (d - b)
    return value


def off_grid(font):
    """Glyphs with an on-curve point or an advance width off the grid."""
    glyf, hmtx, found = font['glyf'], font['hmtx'], {}
    for name in font.getGlyphOrder():
        problems = []
        if hmtx[name][0] % GRID:
            problems.append(f'advance {hmtx[name][0]}')
        glyph = glyf[name]
        if glyph.numberOfContours > 0:
            coordinates, _, flags = glyph.getCoordinates(glyf)
            # Optimized gvar deltas leave a master up to half a unit off its
            # source, so compare the rounded coordinates.
            points = [(round(x), round(y)) for (x, y), flag in zip(coordinates, flags)
                      if flag & 1 and (round(x) % GRID or round(y) % GRID)]
            if points:
                problems.append(f'{len(points)} points, for example {points[0]}')
        if problems:
            found[name] = ', '.join(problems)
    return found


@check(id='fontgarden/grid', title='The masters are on the 2-unit grid',
       rationale='Every point of a Font.Garden source is on the 2-unit grid, so that a '
                 'coordinate tells its grid level. The quadratic conversion moves the '
                 'off-curve points, so this check reads the on-curve points and the '
                 'advance widths of every master of the variable font. Static fonts '
                 'beside a variable font are instances, mostly between masters, so '
                 'they are not checked. A static font without a variable font is '
                 'checked as the master.',
       proposal=ARTICLE)
def grid(font_path: Path, context: CheckContext) -> CheckStatuses:
    font = TTFont(font_path)
    if 'fvar' in font:
        masters = [(str(location), instancer.instantiateVariableFont(copy(font), location))
                   for location in master_locations(font)]
    elif any(Path(font_path).parent.parent.glob('variable/*.ttf')):
        yield SKIP, Message('static', 'A static font is an instance; the masters are checked '
                                      'in the variable font.')
        return
    else:
        # A family without a variable font: the static font is the master.
        masters = [('the static font', font)]
    failed = False
    for where, master in masters:
        found = off_grid(master)
        if found:
            failed = True
            lines = '\n'.join(f'- {name}: {problem}' for name, problem in sorted(found.items()))
            yield FAIL, Message('off-grid', f'At {where}, {len(found)} glyphs are off the '
                                            f'{GRID}-unit grid:\n{lines}')
    if not failed:
        yield PASS, Message('ok', f'All masters are on the {GRID}-unit grid.')


def report(problems, code, what):
    """One FAIL with the first problems, or a PASS."""
    if problems:
        shown = '\n'.join(f'- {line}' for line in problems[:20])
        more = f'\n- and {len(problems) - 20} more' if len(problems) > 20 else ''
        yield FAIL, Message(code, f'{len(problems)} {what}:\n{shown}{more}')
    else:
        yield PASS, Message('ok', f'No {what}.')


def character(code):
    return f'U+{code:04X}'


@check(id='fontgarden/visible_ink', title='Every visible character has ink',
       rationale='A character that is not a space, a control or a format character must '
                 'draw something at every weight. An empty glyph is a drawing that was '
                 'lost, for example by a script that collapsed a contour.')
def visible_ink(font_path: Path, context: CheckContext) -> CheckStatuses:
    problems = []
    for instance in shaped_font.instances(font_path):
        for code, name in instance.cmap.items():
            category = unicodedata.category(chr(code))
            if category.startswith('Z') or category in ('Cc', 'Cf'):
                continue
            if instance.bounds(name) is None:
                problems.append(f'{instance.name}: {character(code)} {name}')
    yield from report(problems, 'no-ink', 'visible characters without ink')


@check(id='fontgarden/mark_glyphs', title='Combining marks have the mark class and no advance',
       rationale='A combining mark is in the mark class of GDEF and has an advance of 0. '
                 'Otherwise the shaper treats it as a letter, and it moves the text.')
def mark_glyphs(font_path: Path, context: CheckContext) -> CheckStatuses:
    font = TTFont(font_path)
    classes = font['GDEF'].table.GlyphClassDef.classDefs if 'GDEF' in font else {}
    problems = []
    for code, name in font.getBestCmap().items():
        if unicodedata.category(chr(code)) != 'Mn':
            continue
        if classes.get(name) != 3:
            problems.append(f'{character(code)} {name}: not in the mark class')
        if font['hmtx'][name][0] != 0:
            problems.append(f'{character(code)} {name}: advance {font["hmtx"][name][0]}')
    yield from report(problems, 'not-a-mark', 'faults of combining marks')


@check(id='fontgarden/static_stat_weight', title='A static font has its own weight in STAT',
       rationale='The STAT table of a static font names one weight: the weight class of '
                 'that font. Otherwise applications put the font at the wrong place in '
                 'the family.')
def static_stat_weight(font_path: Path, context: CheckContext) -> CheckStatuses:
    font = TTFont(font_path)
    if 'fvar' in font or 'STAT' not in font:
        yield SKIP, Message('not-static', 'The font is variable, or has no STAT table.')
        return
    stat = font['STAT'].table
    tags = [axis.AxisTag for axis in stat.DesignAxisRecord.Axis]
    found = [value.Value for value in stat.AxisValueArray.AxisValue
             if tags[value.AxisIndex] == 'wght']
    weight = font['OS/2'].usWeightClass
    if found == [weight]:
        yield PASS, Message('ok', f'STAT names the weight {weight}.')
    else:
        yield FAIL, Message('wrong-weight', f'STAT names the weights {found}; the font is {weight}.')


def mark_bases(code):
    """The bases that a combining mark is tested on."""
    if code in (0x05C1, 0x05C2):
        return DOTTED_CIRCLE, 'ש'
    if 0x0590 <= code <= 0x05FF:
        return DOTTED_CIRCLE, 'ב'
    if 0x0600 <= code <= 0x06FF:
        return DOTTED_CIRCLE, 'ب'
    if 0x0300 <= code <= 0x036F:
        return DOTTED_CIRCLE, 'a', 'x'
    return (DOTTED_CIRCLE,)


@check(id='fontgarden/marks_attach', title='Combining marks attach to their bases',
       rationale='A mark attaches when the mark feature moves it. A mark that the feature '
                 'does not move sits where its glyph is drawn, which is wrong on most '
                 'bases. A base and a mark that HarfBuzz composes into one glyph need no '
                 'attachment.')
def marks_attach(font_path: Path, context: CheckContext) -> CheckStatuses:
    problems = []
    for instance in shaped_font.instances(font_path):
        for code in instance.cmap:
            if unicodedata.category(chr(code)) != 'Mn':
                continue
            for base in mark_bases(code):
                if ord(base) not in instance.cmap:
                    continue
                on = instance.shape(base + chr(code))
                if len(on) == 1:
                    continue
                off = instance.shape(base + chr(code), {'mark': False})
                if ([(p.x_offset, p.y_offset) for _, _, p in on]
                        == [(p.x_offset, p.y_offset) for _, _, p in off]):
                    problems.append(f'{instance.name}: {character(code)} on {character(ord(base))}')
    yield from report(problems, 'not-attached', 'marks that do not attach')


@check(id='fontgarden/stacked_marks', title='Stacked marks do not touch',
       rationale=f'Two marks above a Latin letter keep at least {STACKED_MARK_GAP} units '
                 'between them, so that they stay two marks at text sizes.')
def stacked_marks(font_path: Path, context: CheckContext) -> CheckStatuses:
    problems = []
    for instance in shaped_font.instances(font_path):
        marks = [code for code in LATIN_ABOVE if code in instance.cmap]
        for base in 'oOn':
            if ord(base) not in instance.cmap:
                continue
            for first, second in itertools.product(marks, repeat=2):
                rows = instance.shape(base + chr(first) + chr(second))
                if len(rows) < 3 or not rows[1][1] or not rows[2][1]:
                    continue
                gap = rows[2][1][1] - rows[1][1][3]
                if gap < STACKED_MARK_GAP:
                    problems.append(f'{instance.name}: {base} {character(first)} {character(second)}, gap {gap:g}')
    yield from report(problems, 'marks-touch', 'stacks of marks that are too close')


@check(id='fontgarden/arabic_joins', title='Arabic letters join without gaps',
       rationale='A joining form meets the kashida without a gap. The shaped glyphs are '
                 'in visual order: a final or medial form joins the glyph on its right, '
                 'an initial or medial form joins the glyph on its left.')
def arabic_joins(font_path: Path, context: CheckContext) -> CheckStatuses:
    problems = []
    checked = False
    for instance in shaped_font.instances(font_path):
        if ord(TATWEEL) not in instance.cmap:
            continue
        checked = True
        tatweel = instance.cmap[ord(TATWEEL)]
        letters = [code for code in instance.cmap
                   if 0x0620 <= code <= 0x06FF and unicodedata.category(chr(code)) == 'Lo']
        for code in letters:
            for text in (TATWEEL + chr(code) + TATWEEL, TATWEEL + chr(code)):
                rows = instance.shape(text)
                for (left, a, _), (right, b, _) in zip(rows, rows[1:]):
                    if tatweel not in (left, right) or a is None or b is None:
                        continue
                    letter = right if left == tatweel else left
                    joins = (letter.endswith(('.fina', '.medi')) if letter == left
                             else letter.endswith(('.init', '.medi')))
                    if joins and b[0] - a[2] > 1:
                        problems.append(f'{instance.name}: {letter} beside the kashida, gap {b[0] - a[2]:g}')
    if not checked:
        yield SKIP, Message('no-arabic', 'The font has no Arabic kashida.')
        return
    yield from report(problems, 'join-gap', 'Arabic joins with a gap')


@check(id='fontgarden/hebrew_marks_clear', title='Hebrew accents and meteg clear the vowel point',
       rationale=f'A cantillation accent sits on one side of the vowel point and keeps '
                 f'{CANTILLATION_GAP} units from it. A meteg keeps {METEG_GAP} units from '
                 'the vowel point on its right.')
def hebrew_marks_clear(font_path: Path, context: CheckContext) -> CheckStatuses:
    right_below = {0x059A, 0x05AD}
    left_above = {0x0592, 0x0599, 0x05A9, 0x05AE}
    problems = []
    checked = False
    for instance in shaped_font.instances(font_path):
        cmap = instance.cmap
        if 0x05D1 not in cmap:
            continue
        for code in (*range(0x0591, 0x05B0), 0x05C4, 0x05C5):
            below = unicodedata.combining(chr(code)) in (220, 222)
            point = 0x05B2 if below else 0x05B9
            if code not in cmap or point not in cmap:
                continue
            checked = True
            boxes = {name: box for name, box, _ in instance.shape('ב' + chr(point) + chr(code))}
            accent, vowel = boxes.get(cmap[code]), boxes.get(cmap[point])
            if not accent or not vowel:
                continue
            on_right = code in right_below if below else code not in left_above
            gap = accent[0] - vowel[2] if on_right else vowel[0] - accent[2]
            if gap < CANTILLATION_GAP:
                problems.append(f'{instance.name}: {character(code)} and {character(point)}, gap {gap:g}')
        if 0x05BD not in cmap:
            continue
        vowels = [code for code in (*range(0x05B0, 0x05B9), 0x05BB, 0x05C7) if code in cmap]
        for base, vowel in itertools.product('אבכפעת', vowels):
            if ord(base) not in cmap:
                continue
            checked = True
            boxes = {name: box for name, box, _ in instance.shape(base + chr(vowel) + 'ֽ')}
            point, meteg = boxes.get(cmap[vowel]), boxes.get(cmap[0x05BD])
            if point and meteg and point[0] - meteg[2] < METEG_GAP:
                problems.append(f'{instance.name}: meteg and {character(vowel)} on {character(ord(base))}, '
                                f'gap {point[0] - meteg[2]:g}')
    if not checked:
        yield SKIP, Message('no-hebrew-marks', 'The font has no Hebrew accents or meteg.')
        return
    yield from report(problems, 'marks-collide', 'Hebrew marks that are too close to the vowel point')


@check(id='fontgarden/precomposed_match', title='Precomposed letters match their decomposed sequences',
       rationale='A web font subset can be without a precomposed letter. The shaper then '
                 'builds it from the base and the mark with the mark anchors. The ink of '
                 'both forms must agree within 2 units, or the letter changes shape with '
                 'the subset. The advance can differ by design, so only the ink is compared.')
def precomposed_match(font_path: Path, context: CheckContext) -> CheckStatuses:
    reduced = shaped_font.without_precomposed(font_path)
    problems = []
    seen = set()
    for full, fallback in zip(shaped_font.instances(font_path),
                              shaped_font.instances(font_path, reduced)):
        for code in shaped_font.precomposed(full.cmap):
            expected = shaped_font.union(box for _, box, _ in full.shape(chr(code)))
            actual = shaped_font.union(box for _, box, _ in fallback.shape(chr(code)))
            if any(abs(a - b) > 2 for a, b in zip(expected, actual)) and code not in seen:
                seen.add(code)
                problems.append(f'{full.name}: {character(code)} composite {expected}, anchors {actual}')
    yield from report(problems, 'composite-differs', 'precomposed letters that differ from their sequences')


def project_checks():
    """The checks of the project itself: the functions with @check in
    sources/fontspector_checks.py of the project, if the file exists."""
    root = os.environ.get(PROJECT_ROOT)
    path = Path(root) / PROJECT_CHECKS if root else None
    if path is None or not path.is_file():
        return []
    spec = importlib.util.spec_from_file_location('project_fontspector_checks', path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return [value for value in vars(module).values() if hasattr(value, '_fontspector_check')
            and getattr(value, '__module__', None) == module.__name__]


def copy(font):
    buffer = io.BytesIO()
    font.save(buffer)
    return TTFont(buffer)


def register(plugin: Plugin) -> None:
    checks = [units_per_em, grid, vendor_id, license_names, visible_ink, mark_glyphs, marks_attach,
              stacked_marks, static_stat_weight, arabic_joins, hebrew_marks_clear, precomposed_match]
    own = project_checks()
    for fn in checks + own:
        plugin.register_check(fn)
    # An included profile does not bring its exclusions and configuration, so
    # these are copied from the googlefonts profile of Fontspector 1.9.0.
    plugin.register_profile('fontgarden', ProfileDefinition(
        sections={'Font.Garden': [fn._fontspector_check['id'] for fn in checks],
                  'This font': [fn._fontspector_check['id'] for fn in own]},
        include_profiles=['googlefonts'],
        exclude_checks=['cmap/format_12', 'empty_letters', 'inconsistencies_between_fvar_STAT',
                        'no_mac_entries', 'typographic_family_name', 'vtt_volt_data'],
        configuration_defaults={
            'file_size': {'WARN_SIZE': 1048576, 'FAIL_SIZE': 9437184, 'FATAL_SIZE': 10485760},
            'googlefonts/family/file_size': {'FATAL_SIZE': 26214400}}))


def main():
    return plugin_main(register, plugin_name='fontgarden')


if __name__ == '__main__':
    raise SystemExit(main())
