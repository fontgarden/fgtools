#!/usr/bin/env python3
"""Run the Fontspector checks on the built fonts.

    fgtools qa                        every check: Google Fonts, Font.Garden and this font
    fgtools qa --checks google-fonts  the checks of the Google Fonts profile only
    fgtools qa --checks fontgarden    the Font.Garden checks and the checks of this font only
    fgtools qa --package DIR          every check, on an assembled google/fonts package

The Font.Garden checks are in fontspector_plugin.py, and the checks of a font
in sources/fontspector_checks.py of its project. Reports go to
output/qa/<checks>/. A FAIL gives a failing exit status.

A project lists its known faults in CONTEXT.md, each check with the reason:

    [qa.exclude]
    "googlefonts/glyph_coverage" = "The glyph set is not complete."

Every mode except `--package` leaves these checks out, so that a run shows
new faults only. The font is ready for release when the list is empty. Do
not add a check to the list to hide a new fault.
"""
from __future__ import annotations

import argparse
import os
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

from fgtools import project

# A group of checks and the Fontspector profile that has it.
PROFILES = {'all': 'fontgarden', 'google-fonts': 'googlefonts', 'fontgarden': 'fontgarden-only'}

PLUGIN = '#!{python}\nimport sys\nfrom fgtools.fontspector_plugin import main\nsys.exit(main())\n'


def main():
    parser = argparse.ArgumentParser(description=__doc__.split('\n')[0])
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument('--checks', choices=sorted(PROFILES), default='all',
                      help='one group of checks; the default is all')
    mode.add_argument('--package', type=Path, metavar='DIR', help='a google/fonts package, with every check')
    args = parser.parse_args()
    source = project.load()
    path = os.pathsep.join([str(Path(sys.executable).parent), os.environ.get('PATH', '')])
    fontspector = shutil.which('fontspector', path=path)
    if fontspector is None:
        sys.exit('Fontspector is not installed. Run `fgtools install-tools`.')
    name = 'package' if args.package else args.checks
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
    reports = source.root / 'output/qa' / name
    reports.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix='fgtools-qa-') as temporary:
        plugin = Path(temporary) / 'fontgarden-fontspectorplugin'
        plugin.write_text(PLUGIN.format(python=sys.executable))
        plugin.chmod(0o755)
        command = [fontspector, '--plugin', str(plugin), '-p', PROFILES['all' if args.package else args.checks],
                   '--error-code-on', 'fail', '--loglevel', 'warn', '--succinct']
        if not args.package:
            excluded = source.design().get('qa', {}).get('exclude', {}) if source.design_config.exists() else {}
            for check in excluded:
                command += ['--exclude-checkid', check]
        command += ['--json', str(reports / 'fontspector.json'),
                    '--ghmarkdown', str(reports / 'fontspector.md'), *map(str, inputs)]
        environment = dict(os.environ, PATH=path, FGTOOLS_PROJECT=str(source.root))
        return subprocess.run(command, env=environment).returncode


if __name__ == '__main__':
    sys.exit(main())
