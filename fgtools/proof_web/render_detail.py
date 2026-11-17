"""Render a DesignBot PNG of a sample in each font of a prepared web proof.

    fgtools proof-web render-detail --text TEXT --weight 700 --output FILE

The fonts are those of the live proof (output/proof-web/live), or of
--proof-dir. Each font uses the face nearest to the weight, at one em size.
The command checks the font hashes and stops when a font does not cover the
text: it does not use fallback fonts. It writes the PNG and, next to it, a
JSON record of the fonts, hashes and settings. It needs the `designbot`
command.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import shutil
import subprocess
from pathlib import Path

from fontTools.ttLib import TTFont

from fgtools import project

RECIPE = Path(__file__).with_name('render_detail.rs')
# Joining controls are shaping instructions, not visible characters.
INVISIBLE = {0x200C, 0x200D}


def rendered_weight(face, weight):
    """The weight that a face renders for a requested weight."""
    axis = face.get('axes', {}).get('wght')
    return max(axis[0], min(axis[2], weight)) if axis else int(face.get('weight', weight))


def nearest_face(font, weight):
    """The face of a font record nearest to `weight`: a lower weight on a tie,
    a variable face on an exact tie. The same rule as reference-selection.js."""
    faces = font.get('faces')
    if not faces:
        return font
    return min(faces, key=lambda f: (abs(rendered_weight(f, weight) - weight), rendered_weight(f, weight),
                                     -int('wght' in f.get('axes', {})), f.get('path', f['url'])))


def main(argv=None, prog=None):
    parser = argparse.ArgumentParser(prog=prog, description=__doc__.split('\n')[0])
    parser.add_argument('--proof-dir', type=Path, help='default output/proof-web/live')
    parser.add_argument('--output', type=Path, required=True, help='the PNG file')
    parser.add_argument('--text', required=True)
    parser.add_argument('--title', default='Detail')
    parser.add_argument('--weight', type=int, required=True)
    parser.add_argument('--size', type=int, default=144, help='px/em, default 144')
    args = parser.parse_args(argv)
    if not 8 <= args.size <= 512:
        parser.error('The size must be between 8 and 512 px/em')
    from fgtools.media import designbot
    if designbot() is None:
        parser.exit(1, 'render-detail needs the `designbot` command. `fgtools install-tools` installs it. '
                       'The web proof works without it.\n')
    root = (args.proof_dir or project.load().root / 'output/proof-web/live').resolve()
    manifest = json.loads((root / 'live-fonts.json').read_text())
    after = manifest['after']
    axis = after.get('axes', {}).get('wght')
    if axis and not axis[0] <= args.weight <= axis[2]:
        parser.error(f'The weight must be between {axis[0]:g} and {axis[2]:g}')
    command = [designbot(), '--raw', str(RECIPE), '--output', str(args.output.resolve()), '--',
               str(args.weight), str(args.size), args.text, args.title, str(root / after['url']),
               after['family']]
    required = {ord(c) for c in args.text if not c.isspace() and ord(c) not in INVISIBLE}
    inputs = []
    roles = [role for role in ('before', 'after') if role in manifest]
    roles += [role for role in manifest if role not in ('before', 'after')]
    for role in roles:
        font = manifest[role]
        face = nearest_face(font, args.weight)
        path = root / face['url']
        digest = hashlib.sha256(path.read_bytes()).hexdigest()
        if digest != face['sha256']:
            parser.exit(1, f'{path} differs from the hash in the proof\n')
        with TTFont(path) as tt:
            missing = sorted(required - set(tt.getBestCmap()))
        if missing:
            parser.exit(1, f'{font["family"]} ({role}) does not cover '
                           + ', '.join(f'U+{cp:04X}' for cp in missing) + '\n')
        weight = rendered_weight(face, args.weight)
        label = font['label'] if role in ('before', 'after') else font['family']
        if weight != args.weight:
            label += f' · {weight:g} (nearest supplied weight)'
        command += [str(path), font.get('sourceFamily', font['family']), label, f'{weight:g}']
        inputs.append(dict(role=role, family=font['family'], file=face['url'], sha256=digest,
                           rendered_weight=weight))
    args.output.parent.mkdir(parents=True, exist_ok=True)
    subprocess.run(command, check=True)
    record = dict(renderer='DesignBot --raw', weight=args.weight, size_px_em=args.size,
                  text=args.text, title=args.title, fonts=inputs,
                  recipe_sha256=hashlib.sha256(RECIPE.read_bytes()).hexdigest(),
                  image_sha256=hashlib.sha256(args.output.read_bytes()).hexdigest())
    args.output.with_suffix('.json').write_text(json.dumps(record, ensure_ascii=False, indent=2) + '\n')
    print(args.output.resolve())
