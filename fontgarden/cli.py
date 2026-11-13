"""The `fgtools` command. Each subcommand runs the main() of one module
with the remaining arguments, so `fgtools status --print` is the same as
`python -m fontgarden.status --print`.

The commands find the project from the current directory: the current
directory or the nearest parent that contains sources/config.yaml.
"""
from __future__ import annotations

import importlib
import sys

from fontgarden.project import ProjectError

# Subcommand: (module, arguments put before the user's arguments, description).
COMMANDS = {
    'status': ('status', [], 'Write STATUS.md from the mark colors of the masters'),
    'queue': ('check_design', ['--queue'], 'Rank the glyphs that most composites wait on'),
    'check-design': ('check_design', [], 'Check glyphs against sources/design.toml'),
    'check-changes': ('check_changes', [], 'Check source changes against a base revision'),
    'lint-glifs': ('glif_lint', [], 'Find structural faults in the GLIF files'),
    'lint-curves': ('curve_lint', [], 'Curve fairness checks of one master'),
    'evaluate-drafting': ('evaluate_drafting', [], 'Prepare, score and compare drafting evaluations'),
    'corrections': ('list_corrections', [], 'List the reviews of purple drafts from the Git history'),
    'build': ('build_source_snapshot', [], 'Build the fonts from a copy of the sources'),
    'qa': ('qa', [], 'Run Fontspector with the Font.Garden profile on the built fonts'),
    'diff': ('diff', [], 'Compare two builds with diffenator3'),
    'proof-web': ('proof_web', [], 'Serve the font beside reference-fonts/ in a browser'),
    'install-tools': ('install_tools', [], 'Install the pinned fontc and Fontspector binaries'),
}


def usage():
    width = max(map(len, COMMANDS))
    lines = ['usage: fgtools <command> [arguments]', '', 'commands:']
    lines += [f'  {name:<{width}}  {text}' for name, (_, _, text) in COMMANDS.items()]
    lines += ['', 'Run `fgtools <command> --help` for the arguments of a command.']
    return '\n'.join(lines)


def main(argv=None):
    argv = sys.argv[1:] if argv is None else argv
    if not argv or argv[0] in ('-h', '--help'):
        print(usage())
        return 0 if argv else 2
    name, *rest = argv
    if name not in COMMANDS:
        print(f'fgtools: unknown command {name!r}\n\n{usage()}', file=sys.stderr)
        return 2
    module, before, _ = COMMANDS[name]
    sys.argv = [f'fgtools {name}', *before, *rest]
    try:
        return importlib.import_module(f'fontgarden.{module}').main() or 0
    except ProjectError as error:
        print(f'fgtools: {error}', file=sys.stderr)
        return 1
