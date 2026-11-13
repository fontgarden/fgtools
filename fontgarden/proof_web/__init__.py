"""The web proof: the font of a project beside the fonts in its
reference-fonts/ folder, at one em size and weight, in a browser on localhost.

    fgtools proof-web [--current | --snapshot DIR | --directory DIR] [--port N] [--check]
    fgtools proof-web prepare --evidence FILE --output-dir DIR
    fgtools proof-web render-detail --text TEXT --weight N --output FILE

The modules: serve (the server and the modes), prepare (snapshots and the
live folder), reference_fonts (reference-fonts/), samples (the text samples)
and render_detail (a DesignBot PNG). The web app is in app/.
"""
from __future__ import annotations

import importlib
import sys

SUBCOMMANDS = {'prepare': 'prepare', 'render-detail': 'render_detail'}


def main():
    prog, *argv = sys.argv
    if argv and argv[0] in SUBCOMMANDS:
        module = importlib.import_module(f'fontgarden.proof_web.{SUBCOMMANDS[argv[0]]}')
        return module.main(argv[1:], prog=f'{prog} {argv[0]}')
    from fontgarden.proof_web.serve import main as serve
    return serve(argv, prog=prog)
