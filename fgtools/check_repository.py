"""Check that the repository of a font project stays small and correct.

    fgtools check-repository

- Every tracked file has an allowed place. A worklog, a handoff, a report, a
  receipt or a dated document has none.
- A tracked file has at most 500 KB, because a file stays in every clone of
  the history. A specimen scan can have 8 MB.
- No document names a file, a folder or a `make` target that does not exist:
  relative Markdown links, repository paths in backticks, and `make <target>`
  in backticks. A line with the words "in the Git history" is not checked.
- A document with a chapter `## Contents` lists every other `##` chapter
  there, as a link with the title of the chapter, in the order of the file.

The layout is the same for every Font.Garden project. Change it here, with
the reason in the commit message.
"""
from __future__ import annotations

import re
import subprocess
import sys
from pathlib import Path, PurePosixPath

from fgtools import project

# Allowed paths, as PurePath.full_match patterns. `*` does not match `/`; `**`
# matches any depth. Each of these must match at least one file.
LAYOUT = [
    # Root: the Google Fonts template files, the guide for agents, the design
    # file and the status.
    '.gitignore', 'AGENTS.md', 'AUTHORS.txt', 'CONTEXT.md', 'CONTRIBUTORS.txt', 'Makefile',
    'OFL.txt', 'README.md', 'STATUS.md', 'requirements.in', 'requirements.txt',
    '.github/workflows/*.yaml',
    # Task contracts for unattended runs.
    '.agents/tasks/*.md',
    # Sources.
    'sources/config.yaml', 'sources/held-out-glyphs.toml', 'sources/*.ufo/**',
    # The release document.
    'documentation/*.md',
]

# Allowed paths that a project does not need.
OPTIONAL = [
    # More than one master.
    'sources/*.designspace',
    # The specimen that the font was traced from, and its glyph labels.
    'sources/specimen/*',
    # Text samples of this project for the proofs.
    'sources/proof-samples.toml',
    # Build steps and Fontspector checks that only this font needs.
    'sources/*.py',
    # The Google Fonts article and the DesignBot scripts of the images.
    'documentation/article/**', 'documentation/readme-images/*.rs',
]

# Names that mark a record of work, not a maintained document.
RECORD_NAME = re.compile(r'worklog|handoff|report|receipt|\d{4}-\d{2}-\d{2}', re.I)
# STATUS.md is generated.
GENERATED = {'STATUS.md'}
MAX_FILE_BYTES = 500_000
MAX_SPECIMEN_BYTES = 8_000_000

TOP = ('documentation/', 'sources/', '.agents/', '.github/')
LINK = re.compile(r'\]\(([^)#\s]+)(?:#[^)]*)?\)')
CODE = re.compile(r'`([^`\s]+)`')
MAKE = re.compile(r'`make ([a-z][a-z0-9-]*)')
HISTORY = re.compile(r'Git\s+history', re.I)
CONTENTS = 'Contents'
CONTENTS_LINK = re.compile(r'\[([^\]]+)\]\(#[^)]*\)')


def tracked(root):
    out = subprocess.run(['git', 'ls-files'], cwd=root, capture_output=True, text=True, check=True)
    return [line for line in out.stdout.splitlines() if (root / line).exists()]


def allowed(path, pattern):
    return PurePosixPath(path).full_match(pattern)


def optional(path):
    """The path matches an OPTIONAL pattern, or is a folder of one."""
    path = path.rstrip('/')
    return any(allowed(path, pattern) or pattern.startswith(path + '/') for pattern in OPTIONAL)


def layout_problems(root, files):
    found = []
    for path in files:
        if not any(allowed(path, pattern) for pattern in LAYOUT + OPTIONAL):
            found.append(f'{path}: no allowed place in the layout')
        size = (root / path).stat().st_size
        limit = MAX_SPECIMEN_BYTES if path.startswith('sources/specimen/') else MAX_FILE_BYTES
        if size > limit:
            found.append(f'{path}: {size} bytes, more than {limit}')
        name = PurePosixPath(path).name
        if (path not in GENERATED and name.endswith(('.md', '.txt', '.html'))
                and RECORD_NAME.search(name)):
            found.append(f'{path}: name of a work record')
    for pattern in LAYOUT:
        if not any(allowed(path, pattern) for path in files):
            found.append(f'{pattern}: the layout requires it, and no file matches')
    return found


def reference_problems(root, files):
    paths = set(files)
    for path in files:
        for parent in Path(path).parents:
            paths.add(str(parent) + '/')
    makefile = root / 'Makefile'
    targets = set(re.findall(r'^([a-z][a-z0-9-]*):', makefile.read_text(), re.M)) if makefile.is_file() else set()
    found = []
    for document in (f for f in files if f.endswith('.md') and not (root / f).is_symlink()):
        for number, line in enumerate((root / document).read_text().splitlines(), 1):
            if HISTORY.search(line):
                continue
            where = f'{document}:{number}'
            for link in LINK.findall(line):
                if '://' in link or link.startswith('mailto:'):
                    continue
                target = (root / document).parent.joinpath(link).resolve()
                relative = str(target.relative_to(root)) if target.is_relative_to(root) else None
                if relative is None or not (relative in paths or relative + '/' in paths):
                    found.append(f'{where}: link {link}')
            for code in CODE.findall(line):
                code = code.rstrip('.,:;')
                if not code.startswith(TOP) or any(c in code for c in '*<>{}$') or optional(code):
                    continue
                if not (code in paths or code.rstrip('/') + '/' in paths):
                    found.append(f'{where}: path {code}')
            for target in MAKE.findall(line):
                if target not in targets:
                    found.append(f'{where}: make {target}')
    return found


def contents_problems(root, files):
    found = []
    for document in (f for f in files if f.endswith('.md') and not (root / f).is_symlink()):
        chapters, listed, chapter, in_code = [], [], None, False
        for line in (root / document).read_text().splitlines():
            if line.startswith('```'):
                in_code = not in_code
            elif in_code:
                continue
            elif line.startswith('## '):
                chapter = line[3:].strip()
                if chapter != CONTENTS:
                    chapters.append(chapter)
            elif chapter == CONTENTS:
                listed += CONTENTS_LINK.findall(line)
        if listed != chapters and (listed or CONTENTS in (root / document).read_text()):
            missing = [c for c in chapters if c not in listed]
            extra = [c for c in listed if c not in chapters]
            detail = '; '.join(filter(None, [
                missing and 'not listed: ' + ', '.join(missing),
                extra and 'no such chapter: ' + ', '.join(extra)])) or 'the order differs'
            found.append(f'{document}: the contents differ from the chapters ({detail})')
    return found


def problems(root):
    files = tracked(root)
    return layout_problems(root, files) + reference_problems(root, files) + contents_problems(root, files)


def main():
    if len(sys.argv) > 1:
        sys.exit(__doc__.strip())
    found = problems(project.load().root)
    for line in found:
        print(line)
    if found:
        print(f'{len(found)} problems. The layout is in fgtools/check_repository.py.')
        return 1
    print('The repository layout and the document references are correct.')
    return 0


if __name__ == '__main__':
    sys.exit(main())
