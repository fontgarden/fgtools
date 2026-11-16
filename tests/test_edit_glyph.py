"""Tests of fgtools/edit_glyph.py on the small project."""
import contextlib
import io
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from fgtools import edit_glyph, project
from tests import fixture


class EditGlyph(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = fixture.write_project(Path(self.temp.name) / 'font')
        project._load.cache_clear()

    def tearDown(self):
        self.temp.cleanup()

    def run_command(self, *arguments):
        output = io.StringIO()
        with fixture.working_directory(self.root), mock.patch.object(sys, 'argv', ['edit', *arguments]), \
                contextlib.redirect_stdout(output):
            status = edit_glyph.main()
        return status, output.getvalue()

    def text(self, name, master='Regular'):
        return (self.root / f'sources/Test-{master}.ufo/glyphs/{name}.glif').read_text()

    def write(self, name, text, master='Regular'):
        (self.root / f'sources/Test-{master}.ufo/glyphs/{name}.glif').write_text(text)

    def test_a_green_glyph_is_not_changed(self):
        before = self.text('square')
        status, output = self.run_command('square', '--master', 'Regular', 'set-coordinate',
                                          '--axis', 'y', '--from', '100', '--to', '120')
        self.assertEqual(status, 1)
        self.assertIn('is green', output)
        self.assertEqual(self.text('square'), before)

    def test_an_edge_moves_once_and_the_glyph_becomes_purple(self):
        self.write('square', fixture.glif('square', fixture.YELLOW))
        arguments = ('square', '--master', 'Regular', 'set-coordinate', '--axis', 'y', '--from', '100', '--to', '120')
        self.run_command(*arguments)
        text = self.text('square')
        self.assertEqual(text.count('y="120"'), 2)
        self.assertNotIn('y="100"', text)
        self.assertIn(fixture.PURPLE, text)
        _, output = self.run_command(*arguments)
        self.assertIn('unchanged', output)
        self.assertEqual(self.text('square'), text)

    def test_sidebearings_are_set_to_the_values(self):
        self.write('square', fixture.glif('square', fixture.YELLOW))
        self.run_command('square', '--master', 'Regular', 'set-sidebearings', '--left', '20', '--right', '30')
        text = self.text('square')
        self.assertIn('<point x="20" y="0" type="line"/>', text)
        self.assertIn('<point x="120" y="0" type="line"/>', text)
        self.assertIn('<advance width="150"/>', text)
        _, output = self.run_command('square', '--master', 'Regular', 'set-sidebearings', '--left', '20', '--right', '30')
        self.assertIn('unchanged', output)

    def test_a_copy_mirrors_in_the_advance_and_keeps_the_direction(self):
        donor = fixture.glif('square', fixture.GREEN, right=100, advance=300)
        self.write('square', donor)
        self.write('n', fixture.glif('n', fixture.YELLOW))
        self.run_command('n', '--master', 'Regular', 'copy', 'square', '--mirror', 'horizontal')
        text = self.text('n')
        self.assertIn('<advance width="300"/>', text)
        points = [(float(x), float(y)) for x, y in
                  __import__('re').findall(r'<point x="([^"]*)" y="([^"]*)"', text)]
        self.assertEqual(sorted({x for x, _ in points}), [200, 300])
        area = sum(x0 * y1 - x1 * y0 for (x0, y0), (x1, y1) in zip(points, points[1:] + points[:1]))
        self.assertGreater(area, 0)       # the donor is counter-clockwise, and so is the copy


if __name__ == '__main__':
    unittest.main()
