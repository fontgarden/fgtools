#!/usr/bin/env python3
"""Compare two builds of the project with diffenator3.

    fgtools diff                  the sources in the working tree against
                                     the sources of main
    fgtools diff --base REV       against the sources of another revision
    fgtools diff --fontmake       fontc against fontmake, both from the
                                     sources in the working tree

Both sides are built the same way, by `fgtools build` into a temporary
folder, so project steps after the build do not show as differences. For
each font file that both builds have, diffenator3 writes an HTML report to
output/diff/<font>/ and this command prints a summary: the glyph images and
word images that differ at each location, changed kerning, changed tables,
cmap changes and changed language support.

Use it after a source edit: every difference must be one that the edit
explains. The command exits with status 1 when a glyph or word image differs,
so `--fontmake` fails when the two compilers draw differently.
"""
from __future__ import annotations

import argparse
import io
import json
import os
import shutil
import subprocess
import sys
import tarfile
import tempfile
from pathlib import Path

from fgtools import project
from fgtools.build_source_snapshot import build_fonts, tool_path


def sources_at(revision, root, target):
    """Extract the sources folder of a revision into `target`."""
    archive = subprocess.run(['git', 'archive', '--format=tar', revision, 'sources'],
                             cwd=root, capture_output=True, check=True).stdout
    with tarfile.open(fileobj=io.BytesIO(archive)) as tar:
        tar.extractall(target, filter='data')
    return target / 'sources' / 'config.yaml'


def diffenator(old, new, output):
    """Run diffenator3 on two fonts: write HTML and return the JSON result."""
    path = tool_path()
    if shutil.which('diffenator3', path=path) is None:
        sys.exit('diffenator3 is not installed. Install the requirements of the project.')
    locations = ['--instance', '*'] if 'VF' in old.name or '[' in old.name else []
    command = ['diffenator3', *locations, str(old), str(new)]
    env = dict(os.environ, PATH=path)
    output.mkdir(parents=True, exist_ok=True)
    subprocess.run([*command, '--html', '--output', str(output)], check=True, env=env,
                   capture_output=True)
    result = subprocess.run([*command, '--json'], check=True, env=env, capture_output=True, text=True)
    return json.loads(result.stdout or '{}')


def summary(result):
    """Lines that describe a diffenator3 result, and whether an image differs."""
    lines, images = [], False
    for location in result.get('locations', []):
        glyphs, words = location.get('glyphs', []), location.get('words', {})
        word_count = sum(len(v) for v in words.values()) if isinstance(words, dict) else len(words)
        if glyphs or word_count:
            images = True
            names = ', '.join(g.get('string', '') for g in glyphs[:12])
            lines.append(f"  {location.get('location')}: {len(glyphs)} glyph images differ "
                         f"({names}), {word_count} word images differ")
    kerns = result.get('kerns')
    if kerns:
        lines.append(f'  kerning: {kerns.get("error") if isinstance(kerns, dict) and "error" in kerns else len(kerns)} changes')
    if result.get('tables'):
        lines.append(f"  tables: {', '.join(sorted(result['tables']))}")
    if result.get('cmap_diff'):
        lines.append(f"  cmap: {json.dumps(result['cmap_diff'])[:200]}")
    languages = [name for name, v in result.get('languages', {}).items()
                 if (v.get('level_a'), v.get('score_a')) != (v.get('level_b'), v.get('score_b'))]
    if languages:
        lines.append(f"  language support: {len(languages)} changed ({', '.join(languages[:8])})")
    return lines or ['  no differences'], images


def main():
    parser = argparse.ArgumentParser(description=__doc__.split('\n')[0])
    side = parser.add_mutually_exclusive_group()
    side.add_argument('--base', default='main', help='revision to compare with (default main)')
    side.add_argument('--fontmake', action='store_true', help='compare fontc with fontmake')
    args = parser.parse_args()
    source = project.load()
    with tempfile.TemporaryDirectory(prefix='fgtools-diff-') as temporary:
        temporary = Path(temporary)
        if args.fontmake:
            labels = ('fontmake', 'fontc')
            old = build_fonts(source.config_path, temporary / 'old', 'fontmake', quiet=True)
        else:
            labels = (args.base, 'working tree')
            config = sources_at(args.base, source.root, temporary / 'base')
            old = build_fonts(config, temporary / 'old', quiet=True)
        new = build_fonts(source.config_path, temporary / 'new', quiet=True)
        old_by_name = {font.name: font for font in old}
        changed = False
        pages = []
        print(f'{labels[0]} -> {labels[1]}')
        for font in new:
            if font.name not in old_by_name:
                print(f'{font.name}: only in {labels[1]}')
                continue
            output = source.root / 'output/diff' / font.stem
            lines, images = summary(diffenator(old_by_name[font.name], font, output))
            changed |= images
            print(f'{font.name}: output/diff/{font.stem}/')
            print('\n'.join(lines))
            pages.extend(sorted(output.glob('*.html'))[:1])
        for name in sorted(set(old_by_name) - {font.name for font in new}):
            print(f'{name}: only in {labels[0]}')
    for page in pages:
        project.show(page)
    return 1 if changed else 0


if __name__ == '__main__':
    sys.exit(main())
