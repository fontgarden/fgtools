#!/usr/bin/env python3
"""Download a shared collection of OFL reference fonts from Google Fonts.

    fgtools fetch-reference-fonts [DIRECTORY] [--family NAME ...]
    fgtools fetch-reference-fonts --project

The collection is for comparison and measurement: the accent placement
evaluation, proofs and checks. It is not a source of outlines. Each family
of fgtools/reference_fonts.toml, the trusted list,
goes to DIRECTORY/<family>/ with its OFL.txt, under the file names of
https://github.com/google/fonts. A family with variable fonts gets those;
another family gets its Regular, Italic, Bold and Bold Italic.

DIRECTORY is the argument, or the environment variable
FONTGARDEN_REFERENCE_FONTS. Commands that take reference fonts use the same
variable. A family that is already present is not downloaded again.

With --project, the command gets the reference fonts of one font project.
The families are the keys of `[reference_fonts.families]` in
CONTEXT.md, each with the reason that it is a reference. They go
to the folder reference-fonts/ of the project, which Git ignores. The web
proof and Runebender read that folder. Italic fonts are left out.

A family comes from the first place that has it:

1. the shared collection of FONTGARDEN_REFERENCE_FONTS;
2. a local clone of https://github.com/google/fonts, named by the
   environment variable FONTGARDEN_GOOGLE_FONTS;
3. https://github.com/google/fonts, by download.

The name of a family is its directory name in google/fonts/ofl, so its
upstream is https://github.com/google/fonts/tree/main/ofl/<name>.
"""
from __future__ import annotations

import argparse
import json
import os
import re
import shutil
import sys
import tomllib
import urllib.request
from pathlib import Path

VARIABLE = 'FONTGARDEN_REFERENCE_FONTS'
CLONE = 'FONTGARDEN_GOOGLE_FONTS'
FOLDER = 'reference-fonts'
API = 'https://api.github.com/repos/google/fonts/contents/ofl/'
LIST = Path(__file__).with_name('reference_fonts.toml')
STATIC = re.compile(r'-(Regular|Italic|Bold|BoldItalic)\.ttf$')


def families():
    """The trusted families: directory name in google/fonts/ofl to the reason."""
    return tomllib.loads(LIST.read_text())['families']


def directory(value=None):
    """The collection directory, from the argument or the environment."""
    value = value or os.environ.get(VARIABLE)
    if not value:
        sys.exit(f'Give a directory, or set {VARIABLE}.')
    return Path(value).expanduser()


def fonts(value=None, italic=False):
    """The font files of the collection, without the italics by default."""
    return sorted(path for path in directory(value).glob('*/*.ttf')
                  if italic or 'Italic' not in path.name)


def one_for_each_family(value=None):
    """One upright font for each family: the variable font, or else the Regular."""
    families = {}
    for path in fonts(value):
        rank = 0 if '[' in path.name else 1 if 'Regular' in path.name else 2
        families[path.parent] = min(families.get(path.parent, (9, path)), (rank, path))
    return [path for _, path in sorted(families.values(), key=lambda item: item[1])]


def request(url):
    headers = {'User-Agent': 'fgtools'}
    if os.environ.get('GITHUB_TOKEN'):
        headers['Authorization'] = 'Bearer ' + os.environ['GITHUB_TOKEN']
    with urllib.request.urlopen(urllib.request.Request(url, headers=headers), timeout=60) as response:
        return response.read()


def wanted_files(names, italic=True):
    """The font files to take from a family: the variable fonts, or else the
    Regular, Italic, Bold and Bold Italic."""
    names = [name for name in names if italic or 'Italic' not in name]
    return [name for name in names if name.endswith('.ttf') and '[' in name] \
        or [name for name in names if STATIC.search(name)]


def local_sources(target):
    """(label, directory) of the local places that can hold a family."""
    found = []
    shared = os.environ.get(VARIABLE)
    if shared and Path(shared).expanduser().resolve() != Path(target).resolve():
        found.append(('the shared collection', Path(shared).expanduser()))
    if os.environ.get(CLONE):
        found.append(('the local clone', Path(os.environ[CLONE]).expanduser() / 'ofl'))
    return found


def fetch(target, family, italic=True):
    """Get one family. Returns (number of fonts written, where they came from)."""
    folder = target / family
    if any(folder.glob('*.ttf')):
        return 0, 'present'
    for label, directory in local_sources(target):
        names = [path.name for path in (directory / family).glob('*')]
        wanted = wanted_files(names, italic)
        if wanted and 'OFL.txt' in names:
            folder.mkdir(parents=True, exist_ok=True)
            for name in (*wanted, 'OFL.txt'):
                shutil.copyfile(directory / family / name, folder / name)
            return len(wanted), label
    entries = json.loads(request(API + family))
    names = [entry['name'] for entry in entries]
    wanted = wanted_files(names, italic)
    if not wanted or 'OFL.txt' not in names:
        raise LookupError(f'{family}: no fonts or no OFL.txt in google/fonts/ofl/{family}')
    folder.mkdir(parents=True, exist_ok=True)
    for entry in entries:
        if entry['name'] in (*wanted, 'OFL.txt'):
            (folder / entry['name']).write_bytes(request(entry['download_url']))
    return len(wanted), 'github.com/google/fonts'


def project_families(root=None):
    """(the reference-fonts folder of the project, {family: reason})."""
    from fgtools import project
    source = project.load(root)
    design = source.design() if source.design_config.is_file() else {}
    return source.root / FOLDER, design.get('reference_fonts', {}).get('families', {})


def main():
    parser = argparse.ArgumentParser(prog='fgtools fetch-reference-fonts',
                                     description=__doc__.split('\n')[0])
    parser.add_argument('directory', nargs='?', help=f'default: ${VARIABLE}')
    parser.add_argument('--family', action='append',
                        help='a directory name in google/fonts/ofl (default: the families of reference_fonts.toml)')
    parser.add_argument('--project', action='store_true',
                        help='get the families of CONTEXT.md into reference-fonts/ of the project')
    args = parser.parse_args()
    status = 0
    if args.project:
        target, listed = project_families()
        if not listed and not args.family:
            sys.exit('CONTEXT.md names no family in [reference_fonts.families].')
    else:
        target, listed = directory(args.directory), families()
    for family in args.family or listed:
        try:
            count, origin = fetch(target, family, italic=not args.project)
            print(f'{family}: {count} fonts from {origin}' if count else f'{family}: present')
        except Exception as error:   # report the family and continue with the others
            print(f'{family}: {error}', file=sys.stderr)
            status = 1
    if args.project and target.is_dir():
        extra = sorted(path.name for path in target.iterdir()
                       if path.name not in listed and not path.name.startswith('.'))
        if extra:
            print('Not in CONTEXT.md: ' + ', '.join(extra))
    print(f'{len(fonts(target, italic=True))} fonts in {target}')
    return status


if __name__ == '__main__':
    sys.exit(main())
