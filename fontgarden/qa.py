#!/usr/bin/env python3
"""Run Fontspector with the Font.Garden profile on the built fonts.

    fgtools qa                    the built fonts, offline, without the checks
                                  that sources/design.toml excludes
    fgtools qa --full             the built fonts, all checks
    fgtools qa --package DIR      an assembled google/fonts package

The profile includes the Google Fonts profile; see fontspector_plugin.py.
Reports go to out/qa/<mode>/. A FAIL gives a failing exit status.

A project lists its known development debt in sources/design.toml, each
check with the reason it is excluded:

    [qa.exclude]
    "googlefonts/glyph_coverage" = "The glyph set is not complete."

`--full` and `--package` ignore the list. Do not add a check to the list to
hide a new failure.
"""
from __future__ import annotations

import argparse
import os
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

from fontgarden import project

PLUGIN = '#!{python}\nimport sys\nfrom fontgarden.fontspector_plugin import main\nsys.exit(main())\n'


def main():
    parser = argparse.ArgumentParser(description=__doc__.split('\n')[0])
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument('--full', action='store_true', help='all checks, with network checks')
    mode.add_argument('--package', type=Path, metavar='DIR', help='a google/fonts package')
    args = parser.parse_args()
    source = project.load()
    path = os.pathsep.join([str(Path(sys.executable).parent), os.environ.get('PATH', '')])
    fontspector = shutil.which('fontspector', path=path)
    if fontspector is None:
        sys.exit('Fontspector is not installed. Run `fgtools install-tools`.')
    name = 'package' if args.package else 'full' if args.full else 'development'
    if args.package:
        # Fontspector checks the article references only in its input set.
        inputs = sorted(args.package.glob('*.ttf')) + [args.package / 'METADATA.pb', args.package / 'OFL.txt']
        inputs += sorted(p for p in (args.package / 'article').rglob('*') if p.is_file())
    else:
        inputs = sorted(source.fonts.rglob('*.ttf'))
        if not inputs:
            sys.exit(f'No fonts in {source.fonts}. Run `fgtools build`.')
    missing = [str(p) for p in inputs if not p.is_file()]
    if missing:
        sys.exit(f'Missing: {", ".join(missing)}')
    reports = source.root / 'out/qa' / name
    reports.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix='fontgarden-qa-') as temporary:
        plugin = Path(temporary) / 'fontgarden-fontspectorplugin'
        plugin.write_text(PLUGIN.format(python=sys.executable))
        plugin.chmod(0o755)
        command = [fontspector, '--plugin', str(plugin), '-p', 'fontgarden',
                   '--error-code-on', 'fail', '--loglevel', 'warn', '--succinct']
        if name == 'development':
            excluded = source.design().get('qa', {}).get('exclude', {}) if source.design_config.exists() else {}
            for check in excluded:
                command += ['--exclude-checkid', check]
            command.append('--skip-network')
        command += ['--json', str(reports / 'fontspector.json'),
                    '--ghmarkdown', str(reports / 'fontspector.md'), *map(str, inputs)]
        return subprocess.run(command, env=dict(os.environ, PATH=path)).returncode


if __name__ == '__main__':
    sys.exit(main())
