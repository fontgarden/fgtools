#!/usr/bin/env python3
"""Rename a project made from the Font.Garden project template.

    fgtools customize --family "My Face" --designer "Name" --email me@example.com
                      [--repository https://github.com/owner/my-face]

The template (https://github.com/fontgarden/font-project-template) uses these
placeholder values. The command replaces them in every tracked text file and
in file and folder names:

    Font Garden Template     the family name
    FontGardenTemplate       the family name without spaces, in file names
    fontgardentemplate       the same in lower case, the google/fonts directory
    font-project-template    the repository name, the family name with hyphens
    https://github.com/fontgarden/font-project-template   the repository URL
    Designer Name, designer@example.com                   the designer

Run it once, in a new project, before the first glyph. It does nothing when
the placeholders are gone.
"""
from __future__ import annotations

import argparse
import re
import subprocess
import sys
from pathlib import Path

from fontgarden import project

FAMILY, FILE, SLUG = 'Font Garden Template', 'FontGardenTemplate', 'font-project-template'
URL = f'https://github.com/fontgarden/{SLUG}'
DESIGNER, EMAIL = 'Designer Name', 'designer@example.com'


def replacements(family, designer, email, repository=None):
    """Placeholder and value pairs, longest placeholder first."""
    file_name = re.sub(r'[^A-Za-z0-9]', '', family)
    slug = re.sub(r'[^a-z0-9]+', '-', family.lower()).strip('-')
    pairs = [(URL, repository or f'https://github.com/fontgarden/{slug}'),
             (FAMILY, family), (FILE, file_name), (FILE.lower(), file_name.lower()),
             (SLUG, slug), (EMAIL, email), (DESIGNER, designer)]
    return sorted(pairs, key=lambda pair: -len(pair[0]))


def apply(text, pairs):
    for old, new in pairs:
        text = text.replace(old, new)
    return text


def customize(root, pairs):
    """Replace the placeholders under `root`. Returns the changed paths."""
    tracked = subprocess.run(['git', 'ls-files'], cwd=root, capture_output=True, text=True,
                             check=True).stdout.splitlines()
    changed = []
    for name in tracked:
        path = root / name
        if path.is_symlink() or not path.is_file():
            continue
        try:
            text = path.read_text()
        except UnicodeDecodeError:
            continue
        if apply(text, pairs) != text:
            path.write_text(apply(text, pairs))
            changed.append(name)
    # Rename the deepest paths first, so that a folder keeps its files.
    for path in sorted(root.rglob(f'*{FILE}*'), key=lambda p: -len(p.parts)):
        if '.git' in path.parts or '.venv' in path.parts:
            continue
        target = path.with_name(apply(path.name, pairs))
        path.rename(target)
        changed.append(f'{path.relative_to(root)} -> {target.name}')
    return changed


def main():
    parser = argparse.ArgumentParser(description=__doc__.split('\n')[0])
    parser.add_argument('--family', required=True)
    parser.add_argument('--designer', required=True)
    parser.add_argument('--email', required=True)
    parser.add_argument('--repository', help='URL of the repository of the new font')
    args = parser.parse_args()
    if not re.search(r'[A-Za-z]', args.family):
        sys.exit('The family name needs letters.')
    root = project.find_root()
    changed = customize(root, replacements(args.family, args.designer, args.email, args.repository))
    print('\n'.join(changed) if changed else 'No placeholders found. The project is already named.')


if __name__ == '__main__':
    main()
