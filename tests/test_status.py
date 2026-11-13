"""Tests of fontgarden/status.py and fontgarden/glif_lint.py on a small project."""
import contextlib
import io
import tempfile
import unittest
from pathlib import Path

from fontgarden import cli
from fontgarden import glif_lint
from fontgarden import status
from tests import fixture


class Project(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = fixture.write_project(Path(self.temp.name) / 'font')

    def tearDown(self):
        self.temp.cleanup()

    def test_the_status_counts_the_glyphs_that_are_not_green(self):
        text = status.report(self.root)
        self.assertIn('| Regular | Latin and other | composite or empty | 1 | 1 |', text)
        self.assertIn('| Bold | Latin and other | contour | 2 | 0 |', text)
        self.assertIn('Total: 6 of 8 master glyphs are green.', text)
        self.assertIn('- orange (1): `squarecomposite`', text)

    def test_the_status_command_writes_status_md_in_the_project_root(self):
        with fixture.working_directory(self.root / 'sources'), \
                contextlib.redirect_stdout(io.StringIO()):
            self.assertEqual(cli.main(['status']), 0)
        self.assertTrue((self.root / 'STATUS.md').read_text().startswith('# Status'))

    def test_glif_lint_finds_a_missing_component_and_a_master_difference(self):
        with contextlib.redirect_stdout(io.StringIO()):
            self.assertEqual(glif_lint.lint(root=self.root), 0)
        glyph = self.root / 'sources/Test-Bold.ufo/glyphs/squarecomposite.glif'
        glyph.write_text(fixture.glif('squarecomposite', contour=False, components=['missing']))
        output = io.StringIO()
        with contextlib.redirect_stdout(output):
            self.assertEqual(glif_lint.lint(root=self.root), 1)
        self.assertIn("Bold squarecomposite: component base 'missing' does not exist",
                      output.getvalue())
        self.assertIn("squarecomposite: components differ Regular ['square'] vs Bold ['missing']",
                      output.getvalue())

    def test_an_unknown_command_is_refused(self):
        with contextlib.redirect_stderr(io.StringIO()):
            self.assertEqual(cli.main(['unknown']), 2)

    def test_a_command_outside_a_project_is_an_error(self):
        with fixture.working_directory(self.temp.name), contextlib.redirect_stderr(io.StringIO()):
            self.assertEqual(cli.main(['status', '--print']), 1)


if __name__ == '__main__':
    unittest.main()
