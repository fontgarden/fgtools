#!/usr/bin/env python3
"""Report the grid level of the points, advances and kerning of each master.

    fgtools report-grid-levels [--master NAME] [--glyphs "NAMES"]

The grid of a Font.Garden source is dyadic: every point is on the 2-unit
grid, and the 8-unit grid is the default for structure and spacing. A point
on the 2-unit grid and off the 8-unit grid records a fine correction. The
report counts the points at each level, by script and mark color, so that
the share of corrections and the faults (points off the 2-unit grid) show.
It reads the sources and changes nothing.

With --glyphs, it lists each named glyph with its points off the 8-unit grid.
"""
from __future__ import annotations

import argparse
import plistlib
import sys
from collections import defaultdict

from fgtools import project
from fgtools import source_inventory as inventory
from fgtools.check_changes import POINT
from fgtools.status import script_of


def level(value, coarse, fine):
    """0 on the coarse grid, 1 on the fine grid only, 2 off both."""
    return 0 if value % coarse == 0 else 1 if value % fine == 0 else 2


def report(root=None, master=None, glyphs=None):
    source = project.load(root)
    contract = source.design()
    grid = contract.get('grid', {})
    coarse, fine = grid.get('machine_draft', 8), grid.get('source', 2)
    status = 0
    for name in [master] if master else source.masters:
        records = inventory.load_master(source.root, name, contract)
        groups = defaultdict(lambda: [0, 0, 0, 0, 0])   # glyphs, points by level, advances off coarse
        print(f'{name}: points on the {coarse}-unit grid, on the {fine}-unit grid only, and off both')
        for glyph, record in records.items():
            if not record['contours']:
                continue
            points = POINT.findall((source.root / record['path']).read_text())
            levels = [max(level(float(x), coarse, fine), level(float(y), coarse, fine))
                      for x, y in points]
            group = groups[script_of(glyph), record['color']['name']]
            group[0] += 1
            for value in levels:
                group[1 + value] += 1
            group[4] += bool(record['advance'] and record['advance'] % coarse)
            if glyphs and glyph in glyphs:
                off = [f'{float(x):g},{float(y):g}' for (x, y), value in zip(points, levels) if value]
                print(f'  {glyph} ({record["color"]["name"]}): {len(points)} points, '
                      f'{len(off)} off {coarse}: {" ".join(off) or "none"}; advance {record["advance"]:g}')
        if not glyphs:
            print(f'  {"script":<16} {"color":<8} {"glyphs":>6} {"on " + str(coarse):>8} '
                  f'{str(fine) + " only":>8} {"off " + str(fine):>6}  advances off {coarse}')
            for (script, color), (count, on, corrections, faults, advances) in sorted(groups.items()):
                total = on + corrections + faults
                print(f'  {script:<16} {color:<8} {count:>6} {on / total:>8.0%} {corrections:>8} '
                      f'{faults:>6}  {advances}')
                status = status or bool(faults)
        kerning = source.ufo(name) / 'kerning.plist'
        if kerning.is_file() and not glyphs:
            values = [value for pairs in plistlib.loads(kerning.read_bytes()).values()
                      for value in pairs.values()]
            print(f'  kerning: {len(values)} pairs, {sum(1 for value in values if value % coarse)} '
                  f'off the {coarse}-unit grid, {sum(1 for value in values if value % fine)} off the '
                  f'{fine}-unit grid')
    return int(status)


def main():
    parser = argparse.ArgumentParser(prog='fgtools report-grid-levels', description=__doc__.split('\n')[0])
    parser.add_argument('--master', help='one master (default: all)')
    parser.add_argument('--glyphs', default='', help='list these glyphs, space-separated')
    args = parser.parse_args()
    return report(master=args.master, glyphs=set(args.glyphs.split()))


if __name__ == '__main__':
    sys.exit(main())
