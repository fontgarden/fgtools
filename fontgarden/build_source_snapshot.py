#!/usr/bin/env python3
"""Build the fonts with gftools builder from a copy of the sources.

The masters of a variable font must have the same glyph order, because
fontTools merges their GPOS tables. Font editors can save a different order
in each master. The build copies the sources to a temporary folder, gives
every master the glyph order of the first master, and builds from the copy.
The sources themselves do not change.

    fgtools build                 remove the fonts directory, build the fonts
                                     into it with fontc, and list them
    fgtools build --compiler fontmake
                                     build with fontmake

The fonts directory is `outputDir` in sources/config.yaml. fontc is the
compiler of Google Fonts that replaces fontmake; `fgtools install-tools`
installs it. `fgtools diff --fontmake` compares the output of the two.
"""
from __future__ import annotations

import argparse
import os
import plistlib
import re
import shutil
import subprocess
import sys
import tempfile
import xml.etree.ElementTree as ET
from contextlib import contextmanager
from pathlib import Path

import yaml

from fontgarden import project

GLYPH_ORDER = re.compile(r'(<key>public.glyphOrder</key>\s*<array>)(.*?)(\n\t</array>)', re.S)
# Build output that gftools writes into the sources folder.
BUILD_FILES = ('archive', 'instance_ufos', 'build.ninja', '.ninja_log')


@contextmanager
def build_snapshot(config_path, output=None):
    """Copy the sources and yield the path of the copied config.yaml. The fonts
    go to `output`, or to the outputDir of config.yaml."""
    config_path = Path(config_path).resolve()
    config = yaml.safe_load(config_path.read_text())
    source_root = config_path.parent
    with tempfile.TemporaryDirectory(prefix='fontgarden-build-') as temporary:
        target = (Path(temporary) / 'sources').resolve()
        shutil.copytree(source_root, target, ignore=shutil.ignore_patterns(*BUILD_FILES))
        for designspace in config['sources']:
            path = target / designspace
            if path.suffix == '.ufo':
                continue  # one master: no glyph orders to unify
            if path.suffix != '.designspace':
                raise ValueError('The build needs designspace or UFO sources')
            masters = [(path.parent / s.get('filename')).resolve()
                       for s in ET.parse(path).findall('sources/source')]
            if not masters or any(not m.is_relative_to(target) for m in masters):
                raise ValueError('The designspace sources must be in the sources folder')
            # The first source is the default master. Keep its order, and
            # add the glyphs that only other masters have.
            first = plistlib.loads((masters[0] / 'lib.plist').read_bytes())['public.glyphOrder']
            names = set()
            for master in masters:
                names.update(plistlib.loads((master / 'glyphs/contents.plist').read_bytes()))
            order = list(dict.fromkeys(first)) + sorted(names - set(first))
            values = ''.join(f'\n\t\t<string>{name}</string>' for name in order)
            for master in masters:
                lib = master / 'lib.plist'
                text = lib.read_text()
                match = GLYPH_ORDER.search(text)
                if not match:
                    raise ValueError(f'No glyph order in {lib}')
                lib.write_text(text[:match.end(1)] + values + text[match.end(2):])
        # Change only the outputDir line, so that gftools reads the text of
        # the project's config.yaml and rejects what it would reject there.
        output = Path(output or source_root / config.get('outputDir', '../fonts')).resolve()
        text = re.sub(r'^outputDir:.*\n?', '', config_path.read_text(), flags=re.M)
        copied = target / config_path.name
        copied.write_text(f'{text.rstrip()}\noutputDir: {output}\n')
        yield copied


def tool_path():
    """PATH with the directory of this Python first: gftools, fontmake and the
    installed fontc are there, and it need not be on PATH."""
    return os.pathsep.join([str(Path(sys.executable).parent), os.environ.get('PATH', '')])


def build_fonts(config_path, output, compiler='fontc', quiet=False):
    """Build the fonts of a project into `output` and return their paths.
    With `quiet`, the gftools log is printed only when the build fails."""
    path = tool_path()
    command = ['gftools', 'builder']
    if compiler == 'fontc':
        fontc = shutil.which('fontc', path=path)
        if fontc is None:
            sys.exit('fontc is not installed. Run `fgtools install-tools`.')
        command += ['--experimental-fontc', fontc]
    if shutil.which('gftools', path=path) is None:
        sys.exit('gftools is not installed. Install the requirements of the project.')
    shutil.rmtree(output, ignore_errors=True)
    with build_snapshot(config_path, output) as config:
        result = subprocess.run([*command, str(config)], env=dict(os.environ, PATH=path),
                                capture_output=quiet, text=True)
        if result.returncode:
            if quiet:
                print(result.stdout + result.stderr, file=sys.stderr)
            sys.exit(f'gftools builder failed with {compiler}.')
    fonts = sorted(Path(output).rglob('*.ttf'))
    if not fonts:
        sys.exit('gftools builder produced no TTF files.')
    return fonts


def main():
    parser = argparse.ArgumentParser(description=__doc__.split('\n')[0])
    parser.add_argument('--compiler', choices=['fontc', 'fontmake'], default='fontc')
    args = parser.parse_args()
    source = project.load()
    fonts = build_fonts(source.config_path, source.fonts, args.compiler)
    print('\n'.join(str(font.relative_to(source.root)) for font in fonts))


if __name__ == '__main__':
    main()
