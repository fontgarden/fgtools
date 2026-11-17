"""The `fgtools` command. Each subcommand runs the main() of one module
with the remaining arguments, so `fgtools status --print` is the same as
`python -m fgtools.status --print`.

The commands find the project from the current directory: the current
directory or the nearest parent that contains sources/config.yaml.
"""
from __future__ import annotations

import importlib
import sys

from fgtools.project import ProjectError

# Subcommand: (module, arguments put before the user's arguments, description).
# A module name with a colon names the function to run in place of main().
COMMANDS = {
    'status': ('status', [], 'Write STATUS.md from the mark colors of the masters'),
    'queue': ('check_design', ['--queue'], 'Rank the glyphs that most composites wait on'),
    'check-design': ('check_design', [], 'Check glyphs against CONTEXT.md'),
    'check-changes': ('check_changes', [], 'Check source changes against a base revision'),
    'report-grid-levels': ('grid_levels', [],
                           'Count the points, advances and kerning at each level of the grid'),
    'lint-glifs': ('glif_lint', [], 'Find structural faults in the GLIF files'),
    'lint-curves': ('curve_lint', [], 'Curve fairness checks of one master'),
    'evaluate-drafting': ('evaluate_drafting', [], 'Prepare, score and compare drafting evaluations'),
    'check-accents': ('accent_placement:main_check', [],
                      'List the accented letters whose marks are not where the others predict'),
    'evaluate-accent-placement': ('accent_placement:main_evaluate', [],
                                  'Test the accent placement rules on compiled fonts'),
    'place-anchors': ('accented_letters:main_place', [],
                      'Add the accent anchors that are missing on base letters and marks'),
    'build-accented-letters': ('accented_letters:main_build', [],
                               'Add the accented letters of a set as purple composites'),
    'render-accent-proofs': ('accent_proofs', [],
                             'Draw each accented letter beside the reference fonts, and measure it against them'),
    'draft-weights': ('draft_weights', [],
                      'Draft the masters of more weights from two masters'),
    'corrections': ('list_corrections', [], 'List the reviews of purple drafts from the Git history'),
    'build': ('build_source_snapshot', [], 'Build the fonts from a copy of the sources'),
    'qa': ('qa', [], 'Run Fontspector with the Font.Garden profile on the built fonts'),
    'edit': ('edit_glyph', [], 'Change a glyph with a calculated operation: an edge, the sidebearings, a mirrored copy'),
    'render': ('render_glyphs', [], 'Draw glyphs large: change, fill, points, donors, reference fonts and the glyph in a block of text'),
    'measure-picture': ('measure_picture', [], 'Measure the glyphs in a picture of text, for example a screenshot'),
    'media': ('media', [], 'Render the marketing media of the project with DesignBot: images, carousels and video'),
    'site': ('site', [], 'Collect the print proof and the media into output/site/ for GitHub Pages'),
    'check-repository': ('check_repository', [], 'Check the file layout and the references of the documents'),
    'diff': ('diff', [], 'Compare two builds with diffenator3'),
    'proof-web': ('proof_web', [], 'Serve the font beside reference-fonts/ in a browser'),
    'customize': ('customize', [], 'Rename a project made from the Font.Garden project template'),
    'fetch-reference-fonts': ('reference_fonts', [],
                              'Download the shared OFL reference fonts from Google Fonts'),
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
        module, _, function = module.partition(':')
        return getattr(importlib.import_module(f'fgtools.{module}'), function or 'main')() or 0
    except ProjectError as error:
        print(f'fgtools: {error}', file=sys.stderr)
        return 1
