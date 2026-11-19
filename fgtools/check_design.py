#!/usr/bin/env python3
"""Check glyphs against the measurable design specification.

The specification is the `targets` section of
CONTEXT.md. Runebender measures the glyphs
(`runebender agent call analyze_glyph`); this script holds the Font.Garden
policy. It reads the sources and never writes them.

    fgtools check-design n a seen-ar  report on named glyphs, all masters
    fgtools check-design --not-green  report on every glyph that is not green
    fgtools check-design --green      run the checks on green glyphs (measures
                                         how often the checks flag approved work)
    fgtools check-design --observe    print stroke ranges of the green and yellow glyphs
    fgtools check-design --ready      list composites that pass and are not green
    fgtools check-design --queue      rank the glyphs that most composites wait on

A contour glyph passes when its strokes are inside the target range, all
points are on the 2-unit grid, the analyzer reports no kink, all masters
have the same structure, and its color in text is inside the range of the
reference fonts (fgtools/text_color.py). A composite passes when every part is green,
all masters use the same parts, and Runebender's anchor recipe gives the same
placement. A composite without a recipe needs review by eye. A pass is a filter before review, not approval.
"""
from __future__ import annotations

import argparse
import json
import os
import shutil
import subprocess
import sys
import unicodedata
from pathlib import Path

from fgtools import project
from fgtools import source_inventory as inventory
from fgtools import text_color


def cache_dir():
    """The cache of Runebender measurements, in output/ of the current project."""
    return project.load().root / 'output/check-design-cache'


def find_runebender():
    """The path of the Runebender binary: RUNEBENDER, or `runebender` on PATH."""
    for candidate in (os.environ.get('RUNEBENDER'), shutil.which('runebender')):
        if candidate and Path(candidate).exists():
            return str(candidate)
    return None


def runebender():
    return find_runebender() or sys.exit('Runebender not found. Install it with `cargo install --locked --git '
                                     'https://github.com/fontgarden/runebender runebender`, or set RUNEBENDER.')


def script_of(name, record=None):
    """The target class of a glyph. Symbols, icons and combining marks have no
    stroke target: a vowel dot or a dagesh is not a stem."""
    codes = record['unicodes'] if record else []
    if codes and all(unicodedata.category(chr(c)).startswith('M') for c in codes):
        return 'Symbol'
    if '-ar' in name:
        return 'Arabic'
    if '-hb' in name:
        return 'Hebrew'
    if any(unicodedata.category(chr(c))[0] in 'LN' and c < 0xE000 for c in codes):
        return 'Latin'
    return 'Symbol'


def analyze(master, record, root=None):
    """Runebender's measurement of one glyph, cached by the GLIF digest."""
    cached = cache_dir() / f"{record['sha256']}.json"
    if cached.exists():
        return json.loads(cached.read_text())
    root = project.load().root if root is None else Path(root)
    run = subprocess.run(
        [runebender(), 'agent', 'call', 'analyze_glyph', '--font',
         str(project.layout(root).ufo(master, root)),
         '--args', json.dumps({'glyph': record['glyph']})],
        capture_output=True, text=True)
    result = json.loads(run.stdout)['result']
    cached.parent.mkdir(parents=True, exist_ok=True)
    cached.write_text(json.dumps(result))
    return result


def recipes(master, root=None):
    """Runebender's anchor recipes: glyph name to whether the source matches."""
    run = subprocess.run(
        [runebender(), 'compose', str(project.load(root).ufo(master)), '--json'],
        capture_output=True, text=True)
    try:
        return {row['glyph']: row['up_to_date'] for row in json.loads(run.stdout)['derived']}
    except (ValueError, KeyError):
        return {}


def strokes(analysis, limit):
    """Ink spans short enough to be a stroke, by the direction of the stroke."""
    found = {'vertical_stem': [], 'horizontal_stroke': []}
    for span in analysis['spans']:
        if span['ink'] and span['length'] <= limit:
            # A span measured along the horizontal axis crosses a vertical stem.
            key = 'vertical_stem' if span['axis'] == 'horizontal' else 'horizontal_stroke'
            found[key].append(span['length'])
    return found


def leaves(name, glyphs, seen=()):
    """The contour glyphs that a composite resolves to, or None for a broken reference."""
    record = glyphs.get(name)
    if record is None or name in seen:
        return None
    if not record['components']:
        return [name]
    out = [name] if record['contours'] else []
    for component in record['components']:
        below = leaves(component['base'], glyphs, seen + (name,))
        if below is None:
            return None
        out += below
    return out


def check_contour(name, data, targets, root=None, masters=None, colors=None):
    findings = []
    for master in masters or list(data):
        record = data[master][name]
        analysis = analyze(master, record, root)
        if record['off_2_points']:
            findings.append(f"{master}: {record['off_2_points']} points off the 2-unit grid")
        for issue in analysis['nodes']['issues']:
            if issue['level'] == 'kink':
                findings.append(f"{master}: kink at {issue['x']:g}, {issue['y']:g}")
        script = script_of(name, record)
        target = targets.get(master, {}).get(script)
        if not target:
            if script != 'Symbol':
                findings.append(f'{master}: no stroke target for {script} yet')
            continue
        for key, lengths in strokes(analysis, target['stroke_limit']).items():
            low, high = target[key]
            outside = sorted({length for length in lengths if not low <= length <= high})
            if outside:
                findings.append(f'{master}: {key} {outside} outside {low} to {high}')
    for master, (font, references) in (colors or {}).items():
        comparison = text_color.compare(font, name, references)
        line = text_color.finding(master, comparison) if comparison else None
        if line:
            findings.append(line)
    first, *others = (data[m][name] for m in data)
    if any(first['point_types'] != other['point_types'] for other in others):
        findings.append('masters: contour or point structure differs')
    return findings


def color_fonts(source):
    """{master: (font of the sources, reference fonts)} for the color finding."""
    from fgtools import accent_proofs
    from fgtools.accent_placement import Font
    weights = accent_proofs.master_weights(source)
    return {master: (Font.from_ufo(source.ufo(master)), text_color.reference_fonts(source, weights[master]))
            for master in source.masters}


def check_composite(name, data, recipe):
    findings = []
    for master in data:
        glyphs = data[master]
        record = glyphs[name]
        if not record['components']:
            kinds = {unicodedata.category(chr(c)) for c in record['unicodes']}
            if not kinds or not kinds <= {'Zs', 'Zl', 'Zp', 'Cf'}:
                findings.append(f'{master}: empty glyph')
            continue
        parts = leaves(name, glyphs)
        if parts is None:
            findings.append(f'{master}: a component reference does not resolve')
            continue
        not_green = sorted({p for p in parts if p != name and glyphs[p]['color']['name'] != 'green'})
        if not_green:
            findings.append(f"{master}: parts not green: {', '.join(not_green)}")
        if name not in recipe[master]:
            findings.append(f'{master}: no anchor recipe, so placement needs review by eye')
        elif not recipe[master][name]:
            findings.append(f'{master}: placement differs from the anchor recipe')
    bases = [[c['base'] for c in data[m][name]['components']] for m in data]
    if any(other != bases[0] for other in bases[1:]):
        findings.append('masters: component lists differ')
    return findings


def queue(data):
    """Contour glyphs that are not green, ranked by the composites that wait on them."""
    for master in data:
        glyphs = data[master]
        blocked = {}
        for name, record in glyphs.items():
            if record['components'] and record['color']['name'] != 'green':
                for part in set(leaves(name, glyphs) or []) - {name}:
                    if glyphs[part]['color']['name'] != 'green':
                        blocked.setdefault(part, []).append(name)
        print(f'{master}: glyph (color), composites that wait on it')
        for part, waiting in sorted(blocked.items(), key=lambda item: -len(item[1]))[:25]:
            print(f"  {part} ({glyphs[part]['color']['name']}) {len(waiting)}")


# Yellow is close to green, so both are evidence for the stroke ranges.
REFERENCE_COLORS = ('green', 'yellow')


def observe(data, limit):
    """Stroke ranges of the green glyphs: the evidence for the targets."""
    for master in limit:
        for script in ['Latin', 'Arabic', 'Hebrew']:
            pool = {'vertical_stem': [], 'horizontal_stroke': []}
            count = 0
            for name, record in data[master].items():
                if (script_of(name, record) == script and record['contours']
                        and record['color']['name'] in REFERENCE_COLORS):
                    count += 1
                    for key, lengths in strokes(analyze(master, record), limit[master]).items():
                        pool[key] += lengths
            for key, lengths in pool.items():
                if lengths:
                    lengths.sort()
                    pick = lambda q: lengths[min(len(lengths) - 1, int(q * len(lengths)))]
                    print(f'{master} {script} {key}: {count} glyphs, {len(lengths)} strokes, '
                          f'5% {pick(.05)}, median {pick(.5)}, 95% {pick(.95)}')


def main():
    parser = argparse.ArgumentParser(description=__doc__.split('\n')[0])
    parser.add_argument('glyphs', nargs='*')
    parser.add_argument('--not-green', action='store_true')
    parser.add_argument('--green', action='store_true')
    parser.add_argument('--observe', action='store_true')
    parser.add_argument('--ready', action='store_true')
    parser.add_argument('--queue', action='store_true')
    parser.add_argument('--json', action='store_true')
    args = parser.parse_args()

    source = project.load()
    masters = source.masters
    contract = source.design()
    targets = contract.get('targets', {})
    data = {m: inventory.load_master(source.root, m, contract) for m in masters}
    if args.observe:
        # The longest span that counts as a stroke: the largest stroke_limit
        # of the master. A master without targets has no limit to observe with.
        limit = {m: max(t['stroke_limit'] for t in targets[m].values())
                 for m in masters if targets.get(m)}
        observe(data, limit)
        return 0
    if args.queue:
        queue(data)
        return 0

    names = [n for n in data[masters[0]] if all(n in data[m] for m in masters)]
    is_green = lambda n: all(data[m][n]['color']['name'] == 'green' for m in masters)
    is_composite = lambda n: all(not data[m][n]['contours'] for m in masters)
    if args.glyphs:
        missing = [n for n in args.glyphs if n not in names]
        if missing:
            which = 'both' if len(masters) == 2 else 'all'
            sys.exit(f"Not in {which} masters: {', '.join(missing)}")
        names = args.glyphs
    elif args.green:
        names = [n for n in names if is_green(n)]
    elif args.not_green:
        names = [n for n in names if not is_green(n)]
    elif args.ready:
        names = [n for n in names if is_composite(n) and not is_green(n)]
    else:
        parser.error('name glyphs or pass --not-green, --green, --ready, --queue or --observe')

    recipe = {m: recipes(m) for m in masters} if any(is_composite(n) for n in names) else {}
    colors = color_fonts(source) if any(not is_composite(n) for n in names) else {}
    report = {}
    for name in names:
        if is_composite(name):
            report[name] = check_composite(name, data, recipe)
        else:
            report[name] = check_contour(name, data, targets, colors=colors)

    passed = [n for n, findings in report.items() if not findings]
    if args.json:
        print(json.dumps(report, indent=1))
    elif args.ready:
        print(' '.join(passed))
    else:
        for name, findings in report.items():
            if findings:
                print(name)
                for finding in findings:
                    print(f'  {finding}')
    print(f'{len(passed)} of {len(report)} pass', file=sys.stderr)
    return 0


if __name__ == '__main__':
    sys.exit(main())
