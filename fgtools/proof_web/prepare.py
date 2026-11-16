"""Prepare a snapshot of the web proof from a comparison file.

    fgtools proof-web prepare --comparison FILE --output-dir DIR

The comparison file is a JSON file:

    {"study": {"id": ..., "status": ..., "note": ..., "language": ...,
               "readingDefault": ..., "glyphs": [...], "presets": {...}},
     "fonts": {"before": {"family": ..., "label": ..., "path": ..., "sha256": ...},
               "after": {...}}}

`after` is the Candidate font and is required. `before` is optional; without
it, Toggle is not available. A font record can have `faces`, a list of
records with `path` and `sha256`, in place of its own. Relative paths are
relative to the manifest. The command copies the fonts after a check of
their hashes, copies the fonts of reference-fonts/, selects the text samples
for the scripts that the Candidate covers and writes the web app.

`study.glyphs` is a list of {key, char, name}: the heading of the proof and
one sample for each glyph. `study.presets` maps keys to [text, label]
samples. Both come before the samples of the project.
"""
from __future__ import annotations

import argparse
import hashlib
import html
import json
import shutil
from pathlib import Path

from fontTools.ttLib import TTFont

from fgtools import project
from fgtools.proof_web import samples
from fgtools.proof_web.reference_fonts import FOLDER, ReferenceCache, collect, read_review_data

APP = Path(__file__).with_name('app')
APP_FILES = ['index.html', 'review.css', 'review.js', 'reference-selection.js']
ROLES = ('before', 'after')


def font_record(path, digest, name):
    """The axes and weight of a font file, for the web app."""
    with TTFont(path) as font:
        axes = {a.axisTag: [a.minValue, a.defaultValue, a.maxValue] for a in font['fvar'].axes} if 'fvar' in font else {}
        weight = f'{axes["wght"][0]:g} {axes["wght"][2]:g}' if 'wght' in axes else str(font['OS/2'].usWeightClass)
        return set(font.getBestCmap()), dict(url=f'fonts/{name}', sha256=digest, axes=axes, weight=weight)


def install_app(target, data):
    """Write review-data.js and the web app into `target`. The URLs of the app
    files carry a hash, so that a browser does not mix cached and new files."""
    target = Path(target)
    (target / 'review-data.js').write_text(
        'window.REVIEW_DATA = ' + json.dumps(data, ensure_ascii=False) + ';\n')
    for name in APP_FILES:
        shutil.copy2(APP / name, target / name)
    after = data['fonts']['after']
    css = target / 'review.css'
    css.write_text(css.read_text().replace('fonts/labels.ttf', 'fonts/labels.ttf?v=' + after['sha256'][:12]))
    page = (target / 'index.html').read_text().replace('{{family}}', html.escape(after['family']))
    for name in ['review.css', 'review.js', 'review-data.js', 'reference-selection.js']:
        version = hashlib.sha256((target / name).read_bytes()).hexdigest()[:12]
        page = page.replace(f'"{name}"', f'"{name}?v={version}"')
    (target / 'index.html').write_text(page)


def prepare(comparison_path, output, frozen_references=False, source=None):
    """Prepare a snapshot in `output` and return its path."""
    source = source or project.load()
    comparison_path = Path(comparison_path).resolve()
    comparison = json.loads(comparison_path.read_text())
    target = Path(output).resolve()
    (target / 'fonts').mkdir(parents=True, exist_ok=True)
    records = {}
    for role, record in comparison['fonts'].items():
        if role not in ROLES and not frozen_references:
            continue
        faces, coverage = [], None
        for item in record.get('faces', [record]):
            path = comparison_path.parent / item['path']
            digest = hashlib.sha256(path.read_bytes()).hexdigest()
            if digest != item['sha256']:
                raise ValueError(f'{role}: {path} differs from the hash in the comparison')
            name = f'{role}-{digest[:12]}.ttf'
            if path.resolve() != (target / 'fonts' / name).resolve():
                shutil.copy2(path, target / 'fonts' / name)
            if role == 'after':
                shutil.copy2(path, target / 'fonts/labels.ttf')
            cmap, face = font_record(path, digest, name)
            if 'weight' in item:
                face['weight'] = str(item['weight'])
            coverage = cmap if coverage is None else coverage & cmap
            faces.append(face)
        label = record.get('label', {'before': 'Before', 'after': 'Candidate'}.get(role, 'Reference'))
        records[role] = dict(family=record['family'], label=label, codepoints=sorted(coverage))
        if 'faces' in record:
            records[role]['faces'] = faces
        else:
            records[role].update(faces[0])
    if 'after' not in records:
        raise ValueError('The comparison has no `after` font')
    if not frozen_references:
        references = collect(source.root / FOLDER, target)
        if references['errors']:
            raise ValueError('Reference fonts: ' + '; '.join(references['errors']))
        records.update(references['fonts'])
    chosen = samples.select(records['after']['codepoints'], source.sources)
    install_app(target, dict(study=comparison.get('study'), fonts=records, samples=chosen['samples'],
                             reading={**chosen['reading'], **comparison.get('reading', {})}))
    (target / 'live-fonts.json').write_text(json.dumps(records, indent=2, ensure_ascii=False) + '\n')
    return target


def prepare_live(snapshot, target, source=None):
    """Prepare the live proof in `target`: the Before and Candidate fonts of a
    prepared snapshot, the current web app and the current reference fonts.
    The snapshot does not change. Return the ReferenceCache that serves the
    references."""
    source = source or project.load()
    snapshot, target = Path(snapshot).resolve(), Path(target)
    data = read_review_data(snapshot)
    target.mkdir(parents=True, exist_ok=True)
    data['fonts'] = {key: value for key, value in data['fonts'].items() if key in ROLES}
    for record in data['fonts'].values():
        for face in record.get('faces', [record]):
            path = (snapshot / face['url']).resolve()
            if not path.is_relative_to(snapshot):
                raise ValueError('A snapshot font is outside the snapshot folder')
            raw = path.read_bytes()
            if hashlib.sha256(raw).hexdigest() != face['sha256']:
                raise ValueError(f'{path} differs from the hash in the snapshot')
            destination = target / face['url']
            destination.parent.mkdir(parents=True, exist_ok=True)
            destination.write_bytes(raw)
    shutil.copy2(snapshot / 'fonts/labels.ttf', target / 'fonts/labels.ttf')
    if 'samples' not in data:
        # A snapshot from before the samples were data has no line samples.
        data['samples'] = samples.select(data['fonts']['after']['codepoints'], source.sources)['samples']
    cache = ReferenceCache(source.root / FOLDER, target, dict(data['fonts']))
    references = cache.get()
    data['fonts'].update(references['fonts'])
    data.update(referenceErrors=references['errors'], referenceRevision=references['revision'],
                referenceEndpoint='references.json')
    install_app(target, data)
    (target / 'live-fonts.json').write_text(json.dumps(data['fonts'], indent=2) + '\n')
    # Remove old reference copies only after both manifests are new.
    cache.prune = True
    return cache


def main(argv=None, prog=None):
    parser = argparse.ArgumentParser(prog=prog, description=__doc__.split('\n')[0],
                                     epilog='The format of the manifest is in the docstring of fgtools.proof_web.prepare.')
    parser.add_argument('--comparison', type=Path, required=True, help='the comparison file (JSON)')
    parser.add_argument('--output-dir', type=Path, required=True, help='the snapshot folder to write')
    parser.add_argument('--frozen-references', action='store_true',
                        help='use the reference fonts of the comparison, not those of reference-fonts/')
    args = parser.parse_args(argv)
    try:
        print(prepare(args.comparison, args.output_dir, args.frozen_references))
    except (OSError, ValueError, KeyError) as error:
        parser.exit(1, f'{parser.prog}: {error}\n')
