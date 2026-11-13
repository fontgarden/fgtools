#!/usr/bin/env python3
"""Build the fonts with gftools builder from a copy of the sources.

The masters of a variable font must have the same glyph order, because
fontTools merges their GPOS tables. Font editors can save a different order
in each master. The build copies the sources to a temporary folder, gives
every master the glyph order of the first master, and builds from the copy.
The sources themselves do not change.

    fontgarden build    remove the fonts directory, build the fonts into it,
                        and list them

The fonts directory is `outputDir` in sources/config.yaml.
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
def build_snapshot(config_path):
    """Copy the sources and yield the path of the copied config.yaml."""
    config_path = Path(config_path).resolve()
    config = yaml.safe_load(config_path.read_text())
    source_root = config_path.parent
    with tempfile.TemporaryDirectory(prefix='fontgarden-build-') as temporary:
        target = (Path(temporary) / 'sources').resolve()
        shutil.copytree(source_root, target, ignore=shutil.ignore_patterns(*BUILD_FILES))
        for designspace in config['sources']:
            path = target / designspace
            if path.suffix != '.designspace':
                raise ValueError('The build needs designspace sources')
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
        config['outputDir'] = str((source_root / config.get('outputDir', '../fonts')).resolve())
        copied = target / config_path.name
        copied.write_text(yaml.safe_dump(config, sort_keys=False))
        yield copied


def main():
    parser = argparse.ArgumentParser(description=__doc__.split('\n')[0])
    parser.parse_args()
    source = project.load()
    # gftools and fontmake are installed next to this Python, which need not
    # be on PATH.
    path = os.pathsep.join([str(Path(sys.executable).parent), os.environ.get('PATH', '')])
    if shutil.which('gftools', path=path) is None:
        sys.exit('gftools is not installed. Install the requirements of the project.')
    shutil.rmtree(source.fonts, ignore_errors=True)
    with build_snapshot(source.config_path) as config:
        subprocess.run(['gftools', 'builder', str(config)], check=True,
                       env=dict(os.environ, PATH=path))
    fonts = sorted(source.fonts.rglob('*.ttf'))
    if not fonts:
        sys.exit('gftools builder produced no TTF files.')
    print('\n'.join(str(font.relative_to(source.root)) for font in fonts))


if __name__ == '__main__':
    main()
