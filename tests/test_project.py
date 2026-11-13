"""Tests of the project layout in fontgarden/project.py."""
import os
import tempfile
import unittest
from pathlib import Path

from fontgarden import project
from tests import fixture


class Layout(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = fixture.write_project(Path(self.temp.name) / 'font').resolve()

    def tearDown(self):
        self.temp.cleanup()

    def test_the_root_is_found_from_a_subdirectory(self):
        folder = self.root / 'sources/Test-Bold.ufo/glyphs'
        self.assertEqual(project.find_root(folder), self.root)
        with fixture.working_directory(folder):
            self.assertEqual(project.load().root, self.root)

    def test_no_project_is_an_error(self):
        with self.assertRaises(project.ProjectError):
            project.find_root(Path(self.temp.name))

    def test_masters_are_the_designspace_sources_in_order(self):
        source = project.load(self.root)
        self.assertEqual(source.masters, ['Regular', 'Bold'])
        self.assertEqual(source.ufo('Bold'), self.root / 'sources/Test-Bold.ufo')
        self.assertEqual(source.ufo_relative('Regular'), 'sources/Test-Regular.ufo')
        self.assertEqual(source.ufo('Regular', '/copy'), Path('/copy/sources/Test-Regular.ufo'))
        self.assertEqual(source.fonts, self.root / 'fonts')
        self.assertEqual(source.design_config, self.root / 'sources/design.toml')
        self.assertEqual(source.held_out, self.root / 'sources/held-out-glyphs.toml')
        self.assertIn('green', source.design()['colors'])

    def test_a_copy_of_the_sources_has_the_layout_of_the_current_project(self):
        with fixture.working_directory(self.root):
            self.assertEqual(project.layout(Path(self.temp.name)).root, self.root)

    def test_a_config_without_a_designspace_is_an_error(self):
        (self.root / 'sources/config.yaml').write_text('sources: [Test-Regular.ufo]\n')
        with self.assertRaises(project.ProjectError):
            project.Project(self.root)


@unittest.skipUnless(os.environ.get('FONTGARDEN_TEST_PROJECT'),
                     'set FONTGARDEN_TEST_PROJECT to a font project to run these')
class RealProject(unittest.TestCase):
    def test_every_master_has_a_ufo(self):
        source = project.load(os.environ['FONTGARDEN_TEST_PROJECT'])
        self.assertTrue(source.masters)
        for master in source.masters:
            self.assertTrue((source.ufo(master) / 'glyphs/contents.plist').is_file(), master)


if __name__ == '__main__':
    unittest.main()
