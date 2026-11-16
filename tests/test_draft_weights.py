"""Tests of fontgarden/draft_weights.py on a small project."""
import contextlib
import io
import tempfile
import unittest
import xml.etree.ElementTree as ET
from pathlib import Path

from fontgarden import cli
from fontgarden import draft_weights
from tests import fixture

WEIGHTS = '''
[grid]
source = 2

[weights.Thin]
wght = 100
between = ["Regular", "Bold"]
vertical_stem = { Regular = 100, Bold = 140, target = 60 }
horizontal_stroke = { Regular = 100, Bold = 100, target = 100 }

[weights.Black]
wght = 900
between = ["Regular", "Bold"]
vertical_stem = { Regular = 100, Bold = 140, target = 162 }
horizontal_stroke = { Regular = 80, Bold = 120, target = 140 }
'''


class DraftWeights(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = fixture.write_project(Path(self.temp.name) / 'font')
        design = self.root / 'CONTEXT.md'
        design.write_text(design.read_text() + f'\nR2. The weights.\n\n```toml\n{WEIGHTS}```\n')

    def tearDown(self):
        self.temp.cleanup()

    def run_command(self, *arguments):
        output = io.StringIO()
        with fixture.working_directory(self.root), contextlib.redirect_stdout(output):
            try:
                code = cli.main(['draft-weights', *arguments])
            except SystemExit as stop:
                code = stop.code
        return code, output.getvalue()

    def glyph(self, weight, name):
        return (self.root / f'out/weights/Test-{weight}.ufo/glyphs/{name}.glif').read_text()

    def test_a_coordinate_is_on_the_line_through_the_two_masters(self):
        code, output = self.run_command('Black')
        self.assertEqual(code, 0, output)
        # x: 100 + (140 - 100) * 1.55 = 162.
        self.assertIn('<point x="162" y="100" type="line"/>', self.glyph('Black', 'square'))
        self.assertIn('position x +1.55, y +1.50', output)

    def test_a_drafted_glyph_is_purple_and_the_sources_do_not_change(self):
        before = (self.root / 'sources/Test-Bold.ufo/glyphs/square.glif').read_text()
        self.run_command('Black')
        self.assertIn('<string>0.54,0.44,0.88,1</string>', self.glyph('Black', 'square'))
        self.assertEqual(before, (self.root / 'sources/Test-Bold.ufo/glyphs/square.glif').read_text())

    def test_a_glyph_that_is_not_compatible_is_copied_and_reported(self):
        bold = self.root / 'sources/Test-Bold.ufo/glyphs/n.glif'
        bold.write_text(bold.read_text().replace('\t\t\t<point x="0" y="100" type="line"/>\n', ''))
        code, output = self.run_command('Black')
        self.assertEqual(code, 0, output)
        self.assertIn('not compatible: n', output)
        self.assertEqual(self.glyph('Black', 'n'), bold.read_text())

    def test_a_contour_that_turns_inside_out_is_reported(self):
        text = fixture.glif('square', right=100)
        draft = draft_weights.draft_glyph(text, fixture.glif('square', right=140),
                                          {'x': -3.0, 'y': 0.0}, 2, text)
        self.assertIn('<point x="-20" y="0" type="line"/>', draft)
        self.assertTrue(draft_weights.collapsed(text, draft))

    def test_the_designspace_has_the_masters_and_the_drafts(self):
        self.run_command('Black')
        root = ET.parse(self.root / 'out/weights/Test.designspace').getroot()
        self.assertEqual(root.find('axes/axis').get('maximum'), '900')
        self.assertEqual([source.get('filename') for source in root.findall('sources/source')],
                         ['../../sources/Test-Regular.ufo', '../../sources/Test-Bold.ufo',
                          'Test-Black.ufo'])
        self.assertEqual([instance.get('stylename') for instance in root.findall('instances/instance')],
                         ['Regular', 'Medium', 'SemiBold', 'Bold', 'ExtraBold', 'Black'])

    def test_two_masters_with_the_same_stroke_are_an_error(self):
        code, _ = self.run_command('Thin')
        self.assertEqual(code, 1)


if __name__ == '__main__':
    unittest.main()
