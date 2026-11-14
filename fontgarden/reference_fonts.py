#!/usr/bin/env python3
"""Download a shared collection of OFL reference fonts from Google Fonts.

    fgtools fetch-reference-fonts [DIRECTORY] [--family NAME ...]

The collection is for comparison and measurement: the accent placement
evaluation, proofs and checks. It is not a source of outlines. Each family
goes to DIRECTORY/<family>/ with its OFL.txt, under the file names of
https://github.com/google/fonts. A family with variable fonts gets those;
another family gets its Regular, Italic, Bold and Bold Italic.

DIRECTORY is the argument, or the environment variable
FONTGARDEN_REFERENCE_FONTS. Commands that take reference fonts use the same
variable. A family that is already present is not downloaded again.
"""
from __future__ import annotations

import argparse
import json
import os
import re
import sys
import urllib.request
from pathlib import Path

VARIABLE = 'FONTGARDEN_REFERENCE_FONTS'
API = 'https://api.github.com/repos/google/fonts/contents/ofl/'
# Directory names in google/fonts/ofl: sans and serif text families with wide Latin coverage.
FAMILIES = '''archivo bitter crimsonpro dmsans ebgaramond epilogue figtree firasans ibmplexsans
inter karla lato lexend librefranklin lora manrope merriweather montserrat mulish notosans
nunito opensans outfit playfairdisplay plusjakartasans poppins publicsans raleway roboto sora
sourcesans3 sourceserif4 spacegrotesk worksans'''.split()
STATIC = re.compile(r'-(Regular|Italic|Bold|BoldItalic)\.ttf$')


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
    headers = {'User-Agent': 'fontgarden-tools'}
    if os.environ.get('GITHUB_TOKEN'):
        headers['Authorization'] = 'Bearer ' + os.environ['GITHUB_TOKEN']
    with urllib.request.urlopen(urllib.request.Request(url, headers=headers), timeout=60) as response:
        return response.read()


def fetch(target, family):
    """Download one family. Returns the number of files written."""
    folder = target / family
    if any(folder.glob('*.ttf')):
        return 0
    entries = json.loads(request(API + family))
    names = [entry['name'] for entry in entries]
    wanted = [name for name in names if name.endswith('.ttf') and '[' in name] \
        or [name for name in names if STATIC.search(name)]
    if not wanted or 'OFL.txt' not in names:
        raise LookupError(f'{family}: no fonts or no OFL.txt in google/fonts/ofl/{family}')
    folder.mkdir(parents=True, exist_ok=True)
    for entry in entries:
        if entry['name'] in (*wanted, 'OFL.txt'):
            (folder / entry['name']).write_bytes(request(entry['download_url']))
    return len(wanted)


def main():
    parser = argparse.ArgumentParser(prog='fgtools fetch-reference-fonts',
                                     description=__doc__.split('\n')[0])
    parser.add_argument('directory', nargs='?', help=f'default: ${VARIABLE}')
    parser.add_argument('--family', action='append',
                        help='a directory name in google/fonts/ofl (default: the standard list)')
    args = parser.parse_args()
    target, status = directory(args.directory), 0
    for family in args.family or FAMILIES:
        try:
            count = fetch(target, family)
            print(f'{family}: {count} fonts' if count else f'{family}: present')
        except Exception as error:   # report the family and continue with the others
            print(f'{family}: {error}', file=sys.stderr)
            status = 1
    print(f'{len(fonts(target, italic=True))} fonts in {target}')
    return status


if __name__ == '__main__':
    sys.exit(main())
