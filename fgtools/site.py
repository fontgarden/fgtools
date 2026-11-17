"""Collect the print proof and the marketing media into one folder for GitHub Pages.

    fgtools site

It copies the print specimen, `output/proof/proof.pdf` and the renders of `output/media/` into
`output/site/` and writes `output/site/index.html`, which links to both. The
CI of a project publishes this folder on GitHub Pages, so that the README and
other pages can show the pictures and no rendered file is tracked in Git.
Run `make proof` and `make media` first. The command copies what exists.
"""
from __future__ import annotations

import argparse
import shutil
from html import escape

from fgtools import project
from fgtools.media import FOLDERS

PAGE = """<!doctype html>
<html lang="en">
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>{name}: proofs and media</title>
<style>
  body {{ margin: 0; padding: 32px; background: #1c1c1c; color: #c8c8c8; font: 16px/1.6 system-ui, sans-serif; }}
  a {{ color: #c8c8c8; }}
  p {{ color: #9a9a9a; }}
</style>
<h1>{name}</h1>
<p>Rendered from the sources by the CI of the project.</p>
<ul>
{links}
</ul>
</html>
"""


def build(layout):
    """Write output/site/ and return the list of the parts that it holds."""
    site = layout.root / 'output/site'
    if site.exists():
        shutil.rmtree(site)
    site.mkdir(parents=True)
    parts = []
    proof = layout.root / 'output/proof/proof.pdf'
    if proof.is_file():
        shutil.copy(proof, site / 'proof.pdf')
        parts.append(('proof.pdf', 'The print proof (PDF)'))
    media = layout.root / 'output/media'
    if (media / 'index.html').is_file():
        (site / 'media').mkdir()
        shutil.copy(media / 'index.html', site / 'media/index.html')
        for folder in FOLDERS:      # only the folders of the three kinds: no build files, no old renders
            if (media / folder).is_dir():
                shutil.copytree(media / folder, site / 'media' / folder, ignore=shutil.ignore_patterns('*_safe-areas*'))
        parts.append(('media/', 'The marketing media: every format on each of its canvases'))
    for specimen in sorted((layout.root / 'output/specimen').glob('*.pdf')):
        shutil.copy(specimen, site / 'specimen.pdf')
        parts.insert(0, ('specimen.pdf', 'The print specimen (PDF)'))
    name = layout.config.get('familyName') or layout.root.name
    links = '\n'.join(f'  <li><a href="{escape(path)}">{escape(text)}</a></li>' for path, text in parts)
    (site / 'index.html').write_text(PAGE.format(name=escape(str(name)), links=links))
    return parts


def main(argv=None):
    parser = argparse.ArgumentParser(prog='fgtools site', description=__doc__.split('\n')[0])
    parser.parse_args(argv)
    layout = project.load()
    parts = build(layout)
    if not parts:
        print('output/site/ has only the index: run `make proof` and `make media` first.')
    for path, text in parts:
        print(f'output/site/{path}  {text}')


if __name__ == '__main__':
    main()
