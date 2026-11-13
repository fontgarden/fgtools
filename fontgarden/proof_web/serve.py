"""Serve the web proof on localhost.

    fgtools proof-web --current            the current build beside reference-fonts/
    fgtools proof-web --snapshot DIR       a prepared Before and Candidate snapshot;
                                              the command remembers DIR
    fgtools proof-web                      the remembered snapshot
    fgtools proof-web --directory DIR      a prepared folder as it is
    fgtools proof-web prepare ...          prepare a snapshot (see prepare --help)
    fgtools proof-web render-detail ...    a DesignBot PNG of the live proof

The proof shows the font beside the fonts in reference-fonts/ at one em size
and weight. The current build is the variable font in the fonts directory.
Except with --directory, the server reads reference-fonts/ again when its
files change. It does not read the UFO sources: build again after an edit.
Generated files go to out/proof-web/.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import subprocess
import threading
from functools import partial
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.error import URLError
from urllib.request import urlopen

from fontTools.ttLib import TTFont

from fontgarden import project
from fontgarden.proof_web.prepare import prepare, prepare_live

OUTPUT = 'out/proof-web'
SELECTION = f'{OUTPUT}/selection.json'
DEFAULT_PORT = 60272


def current_font(source):
    """The variable font of the build: a TTF with an fvar table in
    <fonts>/variable/, else the first TTF in the fonts directory."""
    candidates = sorted((source.fonts / 'variable').glob('*.ttf'))
    for path in candidates:
        with TTFont(path, lazy=True) as font:
            if 'fvar' in font:
                return path
    fonts = sorted(source.fonts.rglob('*.ttf'))
    if not fonts:
        raise SystemExit(f'No TTF in {source.fonts}. Run `fgtools build` first.')
    return fonts[0]


def prepare_current(source):
    """Prepare a snapshot of the current build with no Before font."""
    font = current_font(source)
    git = partial(subprocess.run, cwd=source.root, capture_output=True, text=True)
    revision = git(['git', 'rev-parse', '--short', 'HEAD']).stdout.strip() or 'unknown'
    changed = git(['git', 'status', '--porcelain', '--', 'sources']).stdout.strip()
    note = f'Built from sources at {revision}' + (' with uncommitted source changes' if changed else '')
    target = source.root / OUTPUT / 'current'
    target.mkdir(parents=True, exist_ok=True)
    family = source.config.get('familyName') or font.stem.split('[')[0].split('-')[0]
    comparison = target / 'comparison.json'
    comparison.write_text(json.dumps({
        'study': {'id': 'Current build', 'status': 'Current build', 'note': note},
        'fonts': {'after': {'family': family, 'label': 'Current', 'path': str(font),
                            'sha256': hashlib.sha256(font.read_bytes()).hexdigest()}},
    }, indent=2, ensure_ascii=False) + '\n')
    return prepare(comparison, target / 'snapshot', source=source)


def selected_snapshot(root, requested=None):
    """The snapshot of --snapshot, else the remembered snapshot."""
    if requested is not None:
        return Path(requested).resolve()
    selection = root / SELECTION
    if selection.exists():
        return (root / json.loads(selection.read_text())['snapshot']).resolve()
    raise SystemExit('No remembered snapshot. Use --current or --snapshot DIR.')


def remember(root, snapshot):
    """Write the snapshot to SELECTION, relative to the project root if it is in it."""
    selection = root / SELECTION
    selection.parent.mkdir(parents=True, exist_ok=True)
    path = snapshot.relative_to(root) if snapshot.is_relative_to(root) else snapshot
    temporary = selection.with_suffix('.partial')
    temporary.write_text(json.dumps({'snapshot': path.as_posix()}) + '\n')
    temporary.replace(selection)


def server_identity(root, folder, live):
    """Identify the project, the folder and the version of this code, so that
    a running server is used again only when it serves the same proof."""
    code = sorted(Path(__file__).parent.glob('*.py'))
    return dict(project=str(root), directory=str(folder), live=live,
                implementation=hashlib.sha256(b''.join(p.read_bytes() for p in code)).hexdigest())


def matching_server(url, fonts, identity):
    """True when the server at `url` has this identity and these fonts."""
    try:
        with urlopen(url + 'proof-server.json', timeout=2) as response:
            if json.load(response) != identity:
                return False
        with urlopen(url + 'live-fonts.json', timeout=2) as response:
            return json.load(response) == fonts
    except (URLError, OSError, ValueError):
        return False


def verify(folder):
    """Check the files of a proof folder and the hashes of its fonts. Return
    the font records."""
    folder = Path(folder).resolve()
    for name in ['index.html', 'review.css', 'review.js', 'review-data.js', 'fonts/labels.ttf']:
        if not (folder / name).is_file():
            raise ValueError(f'Missing {name}')
    fonts = json.loads((folder / 'live-fonts.json').read_text())
    for role, font in fonts.items():
        for face in font.get('faces', [font]):
            path = (folder / face['url']).resolve()
            if not path.is_relative_to(folder):
                raise ValueError(f'{role}: a font path is outside the proof folder')
            if hashlib.sha256(path.read_bytes()).hexdigest() != face['sha256']:
                raise ValueError(f'{role}: a font differs from its recorded hash')
    return fonts


def handler(folder, identity, cache):
    """The request handler: the files of `folder`, proof-server.json and,
    with a cache, references.json."""
    lock = threading.Lock()

    class Handler(SimpleHTTPRequestHandler):
        def log_request(self, code='-', size='-'):
            if not (self.path.split('?')[0] == '/references.json' and code == 200):
                super().log_request(code, size)

        def end_headers(self):
            self.send_header('Cache-Control', 'no-store')
            super().end_headers()

        def send_json(self, value):
            data = json.dumps(value).encode()
            self.send_response(200)
            self.send_header('Content-Type', 'application/json')
            self.send_header('Content-Length', str(len(data)))
            self.end_headers()
            self.wfile.write(data)

        def do_GET(self):
            endpoint = self.path.split('?')[0]
            if endpoint == '/proof-server.json':
                self.send_json(identity)
            elif cache is not None and endpoint == '/references.json':
                with lock:
                    self.send_json(cache.get())
            else:
                super().do_GET()

    return partial(Handler, directory=str(folder))


def main(argv=None, prog=None):
    parser = argparse.ArgumentParser(prog=prog, description=__doc__.split('\n')[0],
                                     epilog=__doc__.split('\n\n', 1)[1],
                                     formatter_class=argparse.RawDescriptionHelpFormatter)
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument('--current', action='store_true', help='serve the current build in the fonts directory')
    mode.add_argument('--snapshot', type=Path, help='serve and remember a prepared snapshot')
    mode.add_argument('--directory', type=Path, help='serve a prepared folder as it is')
    parser.add_argument('--port', type=int, default=DEFAULT_PORT, help=f'default {DEFAULT_PORT}')
    parser.add_argument('--check', action='store_true', help='prepare and check the files, then exit')
    args = parser.parse_args(argv)
    if not 1 <= args.port <= 65535:
        parser.error('--port must be between 1 and 65535')
    source = project.load()
    output = source.root / OUTPUT
    cache = None
    if args.directory:
        folder = args.directory.resolve()
    else:
        folder = output / 'live'
        snapshot = prepare_current(source) if args.current else selected_snapshot(source.root, args.snapshot)
        try:
            cache = prepare_live(snapshot, folder, source)
        except (OSError, ValueError, KeyError) as error:
            parser.exit(1, f'The snapshot is not available: {error}\n')
    try:
        fonts = verify(folder)
    except (OSError, ValueError, KeyError) as error:
        parser.exit(1, f'The proof files are not ready: {error}\n'
                       'Do not use the current build in place of a missing Before or Candidate font.\n')
    print(f'Verified {len(fonts)} fonts in {folder}', flush=True)
    if args.snapshot:
        remember(source.root, snapshot)
    if args.check:
        return 0
    url = f'http://127.0.0.1:{args.port}/'
    identity = server_identity(source.root, folder, cache is not None)
    if matching_server(url, fonts, identity):
        print(f'The same proof is already served at {url}')
        return 0
    try:
        server = ThreadingHTTPServer(('127.0.0.1', args.port), handler(folder, identity, cache))
    except OSError as error:
        parser.exit(1, f'Could not serve the proof at {url}: {error}\n'
                       'If an older proof of this project uses the port, stop it and run the command again. '
                       'Use --port for a separate proof.\n')
    served = 'the current build' if args.current else str(folder if args.directory else snapshot)
    print(f'Web proof: {url}\nServing {served}. Ctrl-C stops the server.', flush=True)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()
    return 0
