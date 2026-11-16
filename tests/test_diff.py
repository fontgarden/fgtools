"""Tests of the summary in fgtools/diff.py and the pins in install_tools.py."""
import re
import unittest

from fgtools.diff import summary
from fgtools.install_tools import TOOLS


class DiffSummary(unittest.TestCase):
    def test_no_differences(self):
        self.assertEqual(summary({}), (['  no differences'], False))

    def test_a_glyph_image_difference_counts_as_an_image_change(self):
        result = {'locations': [{'location': 'wght=700', 'glyphs': [{'string': 'a'}], 'words': {}}],
                  'tables': {'GPOS': {}}}
        lines, images = summary(result)
        self.assertTrue(images)
        self.assertIn('1 glyph images differ (a)', lines[0])
        self.assertEqual(lines[1], '  tables: GPOS')

    def test_table_differences_alone_are_not_image_changes(self):
        lines, images = summary({'tables': {'name': {}, 'head': {}}, 'locations': []})
        self.assertFalse(images)
        self.assertEqual(lines, ['  tables: head, name'])

    def test_unchanged_language_support_is_not_listed(self):
        same = {'level_a': 'Supported', 'score_a': 1, 'level_b': 'Supported', 'score_b': 1}
        self.assertEqual(summary({'languages': {'German': same}}), (['  no differences'], False))


class Pins(unittest.TestCase):
    def test_every_pinned_archive_has_a_sha256_checksum(self):
        for name, tool in TOOLS.items():
            for platform, (target, checksum) in tool['targets'].items():
                with self.subTest(tool=name, platform=platform):
                    self.assertRegex(checksum, r'^[0-9a-f]{64}$')


if __name__ == '__main__':
    unittest.main()
