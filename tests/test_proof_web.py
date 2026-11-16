"""Tests of fgtools.proof_web, with small fonts made by FontBuilder."""
import contextlib
import hashlib
import io
import json
import shutil
import subprocess
import tempfile
import threading
import unittest
from http.server import ThreadingHTTPServer
from pathlib import Path
from unittest.mock import patch
from urllib.error import URLError
from urllib.request import urlopen

from fontTools.fontBuilder import FontBuilder
from fontTools.pens.ttGlyphPen import TTGlyphPen

from fgtools import project
from fgtools.proof_web import prepare, reference_fonts, render_detail, samples, serve
from fgtools.proof_web.reference_fonts import CACHE_GRACE_SECONDS, ReferenceCache, prune_reference_cache

from tests.fixture import working_directory, write_project  # noqa: E402

LATIN = [ord(c) for c in 'ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz ']
HEBREW = [ord(c) for c in samples.ALPHABETS['Hebrew'][0]]


def font(path, weight=400, family='Test', italic=False, characters=(65,), axis=None):
    """Write a font with an empty glyph for each character. With `axis`
    (minimum, default, maximum), the font has a wght axis."""
    builder = FontBuilder(1000, isTTF=True)
    order = ['.notdef', *[f'u{cp:04X}' for cp in characters]]
    builder.setupGlyphOrder(order)
    builder.setupCharacterMap(dict(zip(characters, order[1:])))
    builder.setupGlyf({name: TTGlyphPen(None).glyph() for name in order})
    builder.setupHorizontalMetrics({name: (500, 0) for name in order})
    builder.setupHorizontalHeader(ascent=800, descent=-200)
    builder.setupOS2(usWeightClass=weight, usWidthClass=5, fsSelection=1 if italic else 0)
    builder.setupNameTable({'familyName': family, 'styleName': 'Italic' if italic else 'Regular'})
    builder.setupPost()
    builder.font['head'].macStyle = 2 if italic else 0
    if axis:
        builder.setupFvar([('wght', *axis, 'Weight')], [])
    Path(path).parent.mkdir(parents=True, exist_ok=True)
    builder.save(path)


@contextlib.contextmanager
def font_project(characters=LATIN):
    """A project with a variable and a static build and one reference font."""
    with tempfile.TemporaryDirectory() as temporary:
        root = write_project(Path(temporary).resolve() / 'project')
        config = root / 'sources/config.yaml'
        config.write_text('familyName: "Test Sans"\n' + config.read_text())
        font(root / 'fonts/ttf/TestSans-Regular.ttf', characters=characters)
        font(root / 'fonts/variable/TestSans[wght].ttf', characters=characters, axis=(400, 400, 700))
        font(root / 'reference-fonts/reference.ttf', family='Reference', characters=characters)
        with working_directory(root):
            yield root


class Samples(unittest.TestCase):
    def test_scripts_follow_the_coverage_of_the_font(self):
        self.assertEqual(samples.covered_scripts(LATIN), {'Latin'})
        self.assertEqual(samples.covered_scripts(LATIN + HEBREW[:10]), {'Latin'})
        self.assertEqual(samples.covered_scripts(LATIN + HEBREW), {'Latin', 'Hebrew'})

    def test_a_latin_font_gets_latin_samples_and_its_repertoire(self):
        with tempfile.TemporaryDirectory() as sources:
            chosen = samples.select(LATIN, sources)
        self.assertEqual({s['key'] for s in chosen['samples']}, {'latin-words', 'latin-spacing'})
        self.assertEqual(set(chosen['reading']), {'latin', 'all-scripts', 'encoded-repertoire'})
        labels = [p['label'] for p in chosen['reading']['all-scripts']['paragraphs']]
        self.assertNotIn('Hebrew · Text', labels)
        self.assertEqual(chosen['reading']['latin']['paragraphs'][0]['dir'], 'ltr')

    def test_a_hebrew_font_gets_right_to_left_paragraphs(self):
        with tempfile.TemporaryDirectory() as sources:
            chosen = samples.select(LATIN + HEBREW, sources)
        self.assertIn('hebrew-words', {s['key'] for s in chosen['samples']})
        paragraph = chosen['reading']['hebrew']['paragraphs'][0]
        self.assertEqual((paragraph['lang'], paragraph['dir']), ('he', 'rtl'))

    def test_project_samples_add_and_replace(self):
        with tempfile.TemporaryDirectory() as sources:
            (Path(sources) / samples.PROJECT_FILE).write_text(
                '[sample.latin-words]\nlabel = "Own words"\ntext = "nonon"\n\n'
                '[sample.figures]\nlabel = "Figures"\ntext = "0123"\n\n'
                '[text.own]\nlabel = "Own text"\nparagraphs = [{ text = "Hello", lang = "he" }]\n')
            chosen = samples.select(LATIN, sources)
            lines = {s['key']: s for s in chosen['samples']}
            self.assertEqual(list(lines), ['latin-words', 'latin-spacing', 'figures'])
            self.assertEqual(lines['latin-words']['text'], 'nonon')
            self.assertEqual(chosen['reading']['own']['paragraphs'][0]['dir'], 'rtl')

    def test_without_defaults_only_the_project_samples_remain(self):
        with tempfile.TemporaryDirectory() as sources:
            (Path(sources) / samples.PROJECT_FILE).write_text(
                'defaults = false\n\n[sample.only]\nlabel = "Only"\ntext = "n"\n')
            chosen = samples.select(LATIN, sources)
        self.assertEqual([s['key'] for s in chosen['samples']], ['only'])
        self.assertEqual(list(chosen['reading']), ['encoded-repertoire'])

    def test_an_unknown_script_is_an_error(self):
        with tempfile.TemporaryDirectory() as sources:
            (Path(sources) / samples.PROJECT_FILE).write_text(
                '[sample.greek]\nlabel = "Greek"\nscripts = ["Greek"]\ntext = "α"\n')
            with self.assertRaisesRegex(ValueError, 'unknown script'):
                samples.select(LATIN, sources)

    def test_marks_in_the_repertoire_have_a_carrier(self):
        paragraphs = samples.repertoire([0x41, 0x5B4, 0x5D0])
        self.assertEqual([p['label'] for p in paragraphs], ['Latin · U+0041–U+0041', 'Hebrew · U+05B4–U+05D0'])
        self.assertEqual(paragraphs[1]['runs'][0]['text'], '◌ִ א')


class CurrentBuild(unittest.TestCase):
    def test_check_prepares_the_variable_font_and_the_references(self):
        with font_project() as root:
            self.assertEqual(serve.current_font(project.load()).name, 'TestSans[wght].ttf')
            with contextlib.redirect_stdout(io.StringIO()):
                self.assertEqual(serve.main(['--current', '--check']), 0)
            live = root / 'output/proof-web/live'
            data = reference_fonts.read_review_data(live)
            self.assertEqual(data['fonts']['after']['family'], 'Test Sans')
            self.assertEqual(data['fonts']['after']['weight'], '400 700')
            self.assertEqual(data['fonts']['reference-0']['family'], 'Reference')
            self.assertIn('latin-words', {s['key'] for s in data['samples']})
            page = (live / 'index.html').read_text()
            self.assertIn('<title>Test Sans · Web proof</title>', page)
            self.assertRegex(page, r'"review-data\.js\?v=[0-9a-f]{12}"')
            for name in prepare.APP_FILES:
                self.assertTrue((live / name).is_file(), name)
            self.assertEqual(set(json.loads((live / 'live-fonts.json').read_text())), {'after', 'reference-0'})

    def test_without_a_variable_font_the_first_ttf_is_used(self):
        with font_project() as root:
            shutil.rmtree(root / 'fonts/variable')
            self.assertEqual(serve.current_font(project.load()).name, 'TestSans-Regular.ttf')

    def test_a_snapshot_is_remembered_relative_to_the_project(self):
        with font_project() as root:
            with self.assertRaises(SystemExit):
                serve.selected_snapshot(root)
            serve.remember(root, root / 'output/study/snapshot')
            self.assertEqual(json.loads((root / serve.SELECTION).read_text()), {'snapshot': 'output/study/snapshot'})
            self.assertEqual(serve.selected_snapshot(root), root / 'output/study/snapshot')
            self.assertEqual(serve.selected_snapshot(root, Path('/explicit')), Path('/explicit').resolve())

    def test_prepare_checks_the_hashes_of_the_comparison(self):
        with font_project() as root:
            comparison = root / 'output/comparison.json'
            path = root / 'fonts/variable/TestSans[wght].ttf'
            record = {'family': 'Test Sans', 'path': str(path), 'sha256': '0' * 64}
            comparison.parent.mkdir()
            comparison.write_text(json.dumps({'fonts': {'after': record}}))
            with self.assertRaisesRegex(ValueError, 'differs from the hash'):
                prepare.prepare(comparison, root / 'output/snapshot')
            record['sha256'] = hashlib.sha256(path.read_bytes()).hexdigest()
            comparison.write_text(json.dumps({'fonts': {'before': record, 'after': {**record, 'label': 'New'}}}))
            data = reference_fonts.read_review_data(prepare.prepare(comparison, root / 'output/snapshot'))
            self.assertEqual((data['fonts']['before']['label'], data['fonts']['after']['label']), ('Before', 'New'))


class Server(unittest.TestCase):
    def test_reuses_only_a_matching_server_with_the_same_fonts(self):
        identity = serve.server_identity(Path('/project'), Path('/project/output/live'), True)
        fonts = {'before': {'sha256': 'frozen'}}

        def responses(other_identity, other_fonts):
            return [io.BytesIO(json.dumps(item).encode()) for item in (other_identity, other_fonts)]

        with patch.object(serve, 'urlopen', side_effect=responses(identity, fonts)):
            self.assertTrue(serve.matching_server('http://localhost/', fonts, identity))
        for key, value in [('project', '/other'), ('directory', '/archive'), ('live', False), ('implementation', 'older')]:
            with self.subTest(key=key), patch.object(serve, 'urlopen', side_effect=responses({**identity, key: value}, fonts)):
                self.assertFalse(serve.matching_server('http://localhost/', fonts, identity))
        with patch.object(serve, 'urlopen', side_effect=responses(identity, {})):
            self.assertFalse(serve.matching_server('http://localhost/', fonts, identity))
        for response in [URLError('unavailable'), io.BytesIO(b'<html>other server</html>')]:
            kwargs = {'side_effect': response} if isinstance(response, Exception) else {'return_value': response}
            with self.subTest(response=response), patch.object(serve, 'urlopen', **kwargs):
                self.assertFalse(serve.matching_server('http://localhost/', {}, {}))

    def test_serves_files_identity_and_references(self):
        with font_project() as root, contextlib.redirect_stderr(io.StringIO()):
            source = project.load()
            live = root / 'output/live'
            cache = prepare.prepare_live(serve.prepare_current(source), live, source)
            identity = serve.server_identity(root, live, True)
            server = ThreadingHTTPServer(('127.0.0.1', 0), serve.handler(live, identity, cache))
            threading.Thread(target=server.serve_forever, daemon=True).start()
            try:
                url = f'http://127.0.0.1:{server.server_address[1]}/'
                self.assertTrue(serve.matching_server(url, serve.verify(live), identity))
                with urlopen(url + 'references.json') as response:
                    self.assertEqual(list(json.load(response)['fonts']), ['reference-0'])
                with urlopen(url) as response:
                    self.assertIn(b'Test Sans', response.read())
            finally:
                server.shutdown()
                server.server_close()


class ReferenceFonts(unittest.TestCase):
    def test_prepare_live_keeps_the_snapshot_and_its_labels(self):
        with font_project() as root:
            snapshot = root / 'proof'
            font(snapshot / 'fonts/drawing.ttf')
            font(snapshot / 'fonts/labels.ttf')
            face = {'family': 'Test Sans', 'url': 'fonts/drawing.ttf', 'label': 'Candidate', 'codepoints': [65],
                    'sha256': hashlib.sha256((snapshot / 'fonts/drawing.ttf').read_bytes()).hexdigest()}
            original = 'window.REVIEW_DATA = ' + json.dumps({'fonts': {'before': face, 'after': face}}) + ';\n'
            (snapshot / 'review-data.js').write_text(original)
            prepare.prepare_live(snapshot, root / 'live')
            data = reference_fonts.read_review_data(root / 'live')
            self.assertEqual(data['fonts']['after']['label'], 'Candidate')
            self.assertIn('samples', data)
            self.assertEqual((snapshot / 'review-data.js').read_text(), original)

    def test_families_coverage_refresh_and_removal(self):
        with tempfile.TemporaryDirectory() as temporary:
            folder, target = Path(temporary) / 'reference-fonts', Path(temporary) / 'out'
            folder.mkdir()
            cache = ReferenceCache(folder, target)
            self.assertFalse(cache.get()['fonts'])
            font(folder / 'regular.TTF')
            font(folder / 'bold.ttf', 700, characters=(65, 66))
            font(folder / 'italic.ttf', italic=True)
            (folder / 'broken.otf').write_text('invalid')
            (folder / 'ignored.txt').write_text('not a font')
            result = cache.get()
            self.assertEqual(len(result['fonts']), 2)
            family = result['fonts']['reference-0']
            self.assertEqual(len(family['faces']), 2)
            self.assertEqual(family['faces'][0]['codepoints'], [65, 66])
            self.assertEqual(len(result['errors']), 1)
            old = result['revision']
            (folder / 'bold.ttf').unlink()
            self.assertNotEqual(cache.get()['revision'], old)
            self.assertEqual(len(cache.get()['fonts']['reference-0']['faces']), 1)
            font(folder / 'regular.TTF', 500, characters=(66,))
            self.assertEqual(cache.get()['fonts']['reference-0']['faces'][0]['minWeight'], 500)

    def test_duplicate_files_and_symbolic_links(self):
        with tempfile.TemporaryDirectory() as temporary:
            folder = Path(temporary) / 'references'
            font(folder / 'a.ttf')
            (folder / 'b.ttf').write_bytes((folder / 'a.ttf').read_bytes())
            (folder / 'cycle').symlink_to(folder, target_is_directory=True)
            cache = ReferenceCache(folder, Path(temporary) / 'out')
            self.assertEqual(len(cache.get()['fonts']['reference-0']['faces']), 1)

    def test_refresh_keeps_newly_prepared_fonts(self):
        with tempfile.TemporaryDirectory() as temporary:
            folder, target = Path(temporary) / 'references', Path(temporary) / 'out'
            font(folder / 'a.ttf')
            target.mkdir()
            cache = ReferenceCache(folder, target, {'before': {'sha256': 'old'}})
            cache.get()
            manifest = target / 'live-fonts.json'
            manifest.write_text(json.dumps({'before': {'sha256': 'new'}}))
            font(folder / 'b.ttf', 700)
            cache.get()
            self.assertEqual(json.loads(manifest.read_text())['before']['sha256'], 'new')

    def test_pruning_keeps_manifest_fonts_and_other_files(self):
        with tempfile.TemporaryDirectory() as temporary:
            target = Path(temporary)
            folder = target / 'fonts'
            folder.mkdir()

            def copy(raw):
                path = folder / f'reference-{hashlib.sha256(raw).hexdigest()}.ttf'
                path.write_bytes(raw)
                return path

            old, startup, current, before = [copy(raw) for raw in (b'old', b'startup', b'current', b'before')]
            record = lambda p: {'url': f'fonts/{p.name}'}
            (target / 'live-fonts.json').write_text(json.dumps({'before': record(before), 'reference': {'faces': [record(current)]}}))
            (target / 'review-data.js').write_text('window.REVIEW_DATA = ' + json.dumps({'fonts': {'reference': {'faces': [record(startup)]}}}) + ';')
            other = folder / 'labels.ttf'
            other.write_bytes(b'labels')
            altered = copy(b'changed')
            altered.write_bytes(b'human replacement')
            external = target / 'outside.ttf'
            external.write_bytes(b'outside')
            link = folder / f'reference-{hashlib.sha256(b"outside").hexdigest()}.ttf'
            link.symlink_to(external)
            stale = {}
            self.assertEqual(prune_reference_cache(target, stale, 0), [])
            self.assertEqual(prune_reference_cache(target, stale, CACHE_GRACE_SECONDS - 1), [])
            self.assertEqual(prune_reference_cache(target, stale, CACHE_GRACE_SECONDS), [old.name])
            for path in (startup, current, before, other, altered, link, external):
                self.assertTrue(path.exists(), path)
            # A file that the manifest uses again loses its grace time.
            (target / 'live-fonts.json').write_text('{}')
            prune_reference_cache(target, stale, 400)
            (target / 'live-fonts.json').write_text(json.dumps({'reference': record(current)}))
            prune_reference_cache(target, stale, 500)
            self.assertNotIn(current.name, stale)
            (target / 'live-fonts.json').write_text('{}')
            prune_reference_cache(target, stale, 600)
            prune_reference_cache(target, stale, 800)
            self.assertTrue(current.exists())

    def test_pruning_stops_on_an_incomplete_manifest(self):
        with tempfile.TemporaryDirectory() as temporary:
            target = Path(temporary)
            (target / 'fonts').mkdir()
            path = target / 'fonts' / f'reference-{hashlib.sha256(b"old").hexdigest()}.ttf'
            path.write_bytes(b'old')
            (target / 'live-fonts.json').write_text('{}')
            (target / 'review-data.js').write_text('incomplete')
            self.assertEqual(prune_reference_cache(target, {path.name: 0}, 999), [])
            self.assertTrue(path.exists())

    def test_pruning_runs_on_each_poll_only_when_enabled(self):
        with tempfile.TemporaryDirectory() as temporary:
            (Path(temporary) / 'references').mkdir()
            cache = ReferenceCache(Path(temporary) / 'references', Path(temporary) / 'out')
            with patch.object(reference_fonts, 'prune_reference_cache') as prune:
                cache.get()
                prune.assert_not_called()
                cache.prune = True
                cache.get()
                cache.get()
                self.assertEqual(prune.call_count, 2)


FACE = lambda low, high=None, path='face': dict(
    minWeight=low, maxWeight=high or low, path=path, url=path, weight=str(low),
    axes={} if high is None else {'wght': [low, low, high]})


class FaceSelection(unittest.TestCase):
    def test_python_selection(self):
        choose = lambda faces, weight: render_detail.nearest_face({'faces': faces}, weight)
        self.assertEqual(choose([FACE(600), FACE(500)], 550)['minWeight'], 500)
        self.assertEqual(choose([FACE(500), FACE(600)], 560)['minWeight'], 600)
        self.assertEqual(choose([FACE(400), FACE(100, 900)], 400)['maxWeight'], 900)
        self.assertEqual(choose([FACE(400, path='b'), FACE(400, path='a')], 400)['path'], 'a')

    @unittest.skipIf(shutil.which('node') is None, 'node is not installed')
    def test_javascript_selection(self):
        script = Path(prepare.APP / 'reference-selection.js')
        test = f'''
const assert = require('node:assert/strict');
const {{choose}} = require({json.dumps(str(script))});
const face = (min, max = min, path = 'face') => ({{minWeight: min, maxWeight: max, path, axes: min === max ? {{}} : {{wght: [min, min, max]}}}});
assert.equal(choose([face(600), face(500)], 550).weight, 500);
assert.equal(choose([face(500), face(600)], 560).weight, 600);
assert.equal(choose([face(400, 700)], 900).weight, 700);
assert.equal(choose([face(400), face(100, 900)], 400).variable, true);
assert.equal(choose([face(400, 400, 'b'), face(400, 400, 'a')], 400).face.path, 'a');
'''
        subprocess.run(['node', '-e', test], check=True)

    def test_render_detail_reports_a_missing_designbot(self):
        with patch.object(shutil, 'which', return_value=None), contextlib.redirect_stderr(io.StringIO()) as error:
            with self.assertRaises(SystemExit) as stop:
                render_detail.main(['--output', 'x.png', '--text', 'a', '--weight', '400'])
        self.assertEqual(stop.exception.code, 1)
        self.assertIn('designbot', error.getvalue())


if __name__ == '__main__':
    unittest.main()
