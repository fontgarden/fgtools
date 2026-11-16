"""Tests of fontgarden/accented_letters.py and fontgarden/accent_proofs.py."""
import contextlib
import io
import json
import plistlib
import re
import tempfile
import unittest
from pathlib import Path

from fontgarden import accent_placement, accent_proofs, accented_letters, project
from tests.test_accent_placement import write_font, write_ufo

PURPLE_LIB = ('\t<lib>\n\t\t<dict>\n\t\t\t<key>public.markColor</key>\n'
              '\t\t\t<string>0.54,0.44,0.88,1</string>\n\t\t</dict>\n\t</lib>\n')


def quiet(function, *args, **kwargs):
    output = io.StringIO()
    with contextlib.redirect_stdout(output), contextlib.redirect_stderr(output):
        status = function(*args, **kwargs)
    return status, output.getvalue()


def remove(root, name):
    """Remove one glyph from the test project."""
    ufo = root / 'sources/Test-Regular.ufo'
    contents = plistlib.loads((ufo / 'glyphs/contents.plist').read_bytes())
    (ufo / 'glyphs' / contents.pop(name)).unlink()
    (ufo / 'glyphs/contents.plist').write_bytes(plistlib.dumps(contents))


def offsets(root):
    font = accent_placement.Font.from_ufo(root / 'sources/Test-Regular.ufo')
    return {row['glyph']: (row['dx'], row['dy']) for row in accent_placement.observations(font)}


class AccentedLetters(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = write_ufo(Path(self.temp.name) / 'font')
        self.ufo = self.root / 'sources/Test-Regular.ufo'
        project._load.cache_clear()

    def tearDown(self):
        self.temp.cleanup()

    def test_unicode_gives_the_parts(self):
        self.assertEqual(accented_letters.parts_of('é'), ('e', 0x0301, 'top'))
        self.assertEqual(accented_letters.parts_of('ç'), ('c', 0x0327, 'bottom'))
        # Unicode gives a cedilla, and the letter has a comma accent.
        self.assertEqual(accented_letters.parts_of('ķ'), ('k', 0x0326, 'bottom'))
        for character in 'ďťľĽģấ':
            self.assertIsInstance(accented_letters.parts_of(character), str, character)

    def test_place_anchors_writes_only_with_write(self):
        before = (self.ufo / 'glyphs/a.glif').read_text()
        _, text = quiet(accented_letters.place_anchors, self.root, characters='áÁ')
        self.assertIn('Nothing is written', text)
        self.assertEqual((self.ufo / 'glyphs/a.glif').read_text(), before)

    def test_placed_anchors_agree_with_the_accented_letters(self):
        quiet(accented_letters.place_anchors, self.root, characters='áäàéëèÁÄÀóöò', write=True)
        text = (self.ufo / 'glyphs/a.glif').read_text()
        self.assertIn('\t</outline>\n\t<anchor name="top" x="70" y="500"/>\n', text)
        self.assertIn('<anchor name="_top" x="20" y="500"/>',
                      (self.ufo / 'glyphs/acute.glif').read_text())
        project._load.cache_clear()
        _, text = quiet(accent_placement.check, root=self.root)
        self.assertNotIn('anchors', text.split('listed')[1].split('anchors are missing')[0])
        # A second run finds nothing to add for these letters.
        project._load.cache_clear()
        _, text = quiet(accented_letters.place_anchors, self.root, characters='áäàéëèÁÄÀóöò')
        self.assertIn('0 anchors to add', text)

    def test_a_removed_letter_is_built_at_the_position_of_the_designer(self):
        expected = offsets(self.root)
        for name in ('eacute', 'Adieresis'):
            remove(self.root, name)
        (self.ufo / 'lib.plist').write_text(
            '<plist version="1.0">\n<dict>\n\t<key>public.glyphOrder</key>\n\t<array>\n'
            '\t\t<string>a</string>\n\t</array>\n</dict>\n</plist>\n')
        _, text = quiet(accented_letters.build_accented_letters, self.root, characters='éÄá', write=True)
        self.assertIn('2 accented letters added', text)
        self.assertIn('1 accented letters are in the sources', text)
        project._load.cache_clear()
        found = offsets(self.root)
        self.assertEqual(found['eacute'], expected['eacute'])
        self.assertEqual(found['Adieresis'], expected['Adieresis'])
        glif = (self.ufo / 'glyphs/A_dieresis.glif').read_text()
        self.assertIn('<unicode hex="00C4"/>', glif)
        self.assertIn('<advance width="200"/>', glif)
        self.assertIn('<string>0.54,0.44,0.88,1</string>', glif)
        self.assertIn('\t\t<string>a</string>\n\t\t<string>eacute</string>\n\t\t<string>Adieresis</string>\n\t</array>',
                      (self.ufo / 'lib.plist').read_text())
        self.assertIn('Adieresis', plistlib.loads((self.ufo / 'glyphs/contents.plist').read_bytes()))

    def test_only_purple_letters_are_set_again(self):
        path = self.ufo / 'glyphs/eacute.glif'
        moved = re.sub(r'xOffset="[^"]*"', 'xOffset="99"', path.read_text())
        path.write_text(moved)
        quiet(accented_letters.build_accented_letters, self.root, characters='é',
              replace_drafts=True, write=True)
        self.assertEqual(path.read_text(), moved)       # no color: the letter is not a draft
        path.write_text(moved.replace('</glyph>', PURPLE_LIB + '</glyph>'))
        project._load.cache_clear()
        quiet(accented_letters.build_accented_letters, self.root, characters='é',
              replace_drafts=True, write=True)
        self.assertIn('<component base="acute" xOffset="30"/>', path.read_text())
        self.assertIn('0.54,0.44,0.88,1', path.read_text())

    def test_a_letter_without_a_drawn_mark_is_listed(self):
        _, text = quiet(accented_letters.build_accented_letters, self.root, characters='ã')
        self.assertIn('atilde ã: the mark U+0303 is not drawn', text)


class AccentProofs(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = write_ufo(Path(self.temp.name) / 'font', moved='eacute')
        self.references = Path(self.temp.name) / 'references'
        for family in ('one', 'two', 'three'):
            (self.references / family).mkdir(parents=True)
            write_font(self.references / family / 'Test-Regular.ttf')
        project._load.cache_clear()

    def tearDown(self):
        self.temp.cleanup()

    def test_a_displaced_mark_differs_from_the_reference_fonts(self):
        out = self.root / 'output/accent-proofs'
        status, text = quiet(accent_proofs.render, self.root, references=str(self.references))
        self.assertEqual(status, 0, text)
        data = json.loads((out / 'review.json').read_text())['Regular']
        self.assertEqual(data['reference_fonts'], ['one', 'three', 'two'])
        first = data['letters'][0]
        self.assertEqual(first['glyph'], 'eacute')
        self.assertEqual(first['kinds'], ['position', 'project'])
        self.assertEqual(first['reference']['position'], [0.5, 0.5])
        self.assertEqual([letter['glyph'] for letter in data['letters'] if letter['findings']], ['eacute'])
        self.assertTrue((out / first['sheet']).is_file())

    def test_a_glyph_is_filled_with_the_nonzero_rule(self):
        # A box with a counter in the other direction: the counter stays empty.
        shape = accent_placement.Shape([], 100, [[(0, 0), (100, 0), (100, 100), (0, 100)],
                                                 [(40, 40), (40, 60), (60, 60), (60, 40)]])
        cover = accent_proofs.rasterize(shape, 1, 20, width=140, rows=140, baseline=120)
        self.assertEqual(cover[110, 30], 1)     # the stroke
        self.assertEqual(cover[70, 70], 0)      # the counter
        self.assertEqual(cover[10, 10], 0)      # outside



class ProjectReferenceFonts(unittest.TestCase):
    def test_a_project_gets_its_families_from_a_local_clone(self):
        import os
        import sys
        from unittest import mock
        from fontgarden import reference_fonts
        with tempfile.TemporaryDirectory() as temp:
            root = write_ufo(Path(temp) / 'font')
            (root / 'CONTEXT.md').write_text(
                '```toml\n[reference_fonts.families]\nheebo = "A Hebrew sans."\n```\n')
            family = Path(temp) / 'clone/ofl/heebo'
            family.mkdir(parents=True)
            for name in ('Heebo[wght].ttf', 'OFL.txt', 'METADATA.pb'):
                (family / name).write_text(name)
            project._load.cache_clear()
            environment = {reference_fonts.CLONE: str(Path(temp) / 'clone')}
            with mock.patch.dict(os.environ, environment), mock.patch.object(sys, 'argv', ['x', '--project']), \
                    mock.patch.object(Path, 'cwd', return_value=root):
                os.environ.pop(reference_fonts.VARIABLE, None)
                status, text = quiet(reference_fonts.main)
            self.assertEqual(status, 0, text)
            self.assertIn('heebo: 1 fonts from the local clone', text)
            self.assertEqual(sorted(path.name for path in (root / 'reference-fonts/heebo').iterdir()),
                             ['Heebo[wght].ttf', 'OFL.txt'])


if __name__ == '__main__':
    unittest.main()
