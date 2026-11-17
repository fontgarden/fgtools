"""Tests of fgtools/measure_picture.py with a picture made of rectangles."""
import unittest

import numpy

from fgtools import measure_picture


def picture():
    """An H (two stems of 10 and a bar of 8, cap height 100) and a vertical bar that is
    6 wide and extends 10 above and 20 below."""
    ink = numpy.zeros((160, 120), dtype=bool)
    ink[30:130, 10:20] = ink[30:130, 50:60] = True
    ink[76:84, 10:60] = True
    ink[20:150, 80:86] = True
    return ink


class MeasurePicture(unittest.TestCase):
    def test_the_glyphs_are_divided_at_the_empty_columns(self):
        found = measure_picture.glyphs(picture())
        self.assertEqual([(glyph['left'], glyph['right']) for glyph in found], [(10, 60), (80, 86)])
        self.assertEqual(found[0]['across'][0], [10, 10])
        self.assertEqual(found[0]['down'][0], [8])

    def test_the_report_is_in_cap_heights_and_stems_when_the_text_has_an_H(self):
        lines = measure_picture.report(measure_picture.glyphs(picture()), 'H|')
        self.assertIn('cap heights (100 pixels), strokes in H stems (10 pixels)', lines[0])
        self.assertIn('|  width 0.06  top 1.10  bottom -0.20', lines[2])
        self.assertIn('across 0.60 | 0.60', lines[2])

    def test_a_text_of_another_length_gives_numbers_for_names(self):
        lines = measure_picture.report(measure_picture.glyphs(picture()), 'H')
        self.assertIn('2 glyphs and the text has 1 characters', lines[0])
        self.assertIn('pixels', lines[1])


if __name__ == '__main__':
    unittest.main()
