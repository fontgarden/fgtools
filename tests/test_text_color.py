"""Tests of fgtools/text_color.py with fonts made of rectangles."""
import unittest

from fgtools import text_color


class Shape:
    def __init__(self, contours, advance=600):
        self.contours, self.advance, self.empty = contours, advance, not contours


class Font:
    """A font with the parts that text_color reads."""
    units_per_em = 1024

    def __init__(self, shapes):
        self.shapes = shapes
        self.glyph_set = shapes
        self.code_points = {'H': ord('H'), 'numbersign': ord('#')}
        self.names = {code: name for name, code in self.code_points.items()}
        self.advances = {name: shape.advance for name, shape in shapes.items()}

    def shape(self, name):
        return self.shapes[name]


def box(left, bottom, right, top):
    return [(left, bottom), (right, bottom), (right, top), (left, top)]


def font(stroke):
    """H is one full box. The number sign is a frame with strokes of `stroke` units."""
    frame = [box(0, 0, 400, 400), box(stroke, stroke, 400 - stroke, 400 - stroke)[::-1]]
    return Font({'H': Shape([box(0, 0, 400, 700)]), 'numbersign': Shape(frame)})


class TextColor(unittest.TestCase):
    def test_the_fill_of_a_box_is_one_and_a_frame_has_less(self):
        self.assertAlmostEqual(text_color.fill(font(100), 'H'), 1, delta=0.02)
        self.assertAlmostEqual(text_color.color(font(100), 'numbersign'), 0.75, delta=0.02)

    def test_a_glyph_darker_than_every_reference_font_is_a_finding(self):
        references = [(name, font(stroke)) for name, stroke in (('a', 60), ('b', 70), ('c', 80))]
        heavy = text_color.compare(font(120), 'numbersign', references)
        self.assertIn('darker than in all 3 reference fonts', text_color.finding('Regular', heavy))
        light = text_color.compare(font(30), 'numbersign', references)
        self.assertIn('lighter', text_color.finding('Regular', light))
        self.assertIsNone(text_color.finding('Regular', text_color.compare(font(70), 'numbersign', references)))

    def test_fewer_than_three_reference_fonts_give_no_comparison(self):
        self.assertIsNone(text_color.compare(font(70), 'numbersign', [('a', font(60))]))

    def test_the_strip_sets_the_glyph_between_the_control_letters(self):
        names = text_color.sequence(font(70), 'numbersign')
        self.assertEqual(names[:4], ['H', 'numbersign', 'H', 'numbersign'])
        sharp, blurred = text_color.strip(font(70), 'numbersign', 800, -200)
        self.assertEqual(sharp.shape, blurred.shape)
        self.assertGreater(sharp.max(), blurred.max() - 0.01)


if __name__ == '__main__':
    unittest.main()
