"""Tests of the stroke and component measurements in fontgarden/check_design.py."""
import unittest

from fontgarden import check_design


class CheckDesign(unittest.TestCase):
    def test_strokes_split_by_direction_and_ignore_long_spans(self):
        analysis = {'spans': [
            {'axis': 'horizontal', 'ink': True, 'length': 96},
            {'axis': 'vertical', 'ink': True, 'length': 84},
            {'axis': 'vertical', 'ink': True, 'length': 576},
            {'axis': 'horizontal', 'ink': False, 'length': 90}]}
        self.assertEqual(check_design.strokes(analysis, 180),
                         {'vertical_stem': [96], 'horizontal_stroke': [84]})

    def test_leaves_resolve_nested_components(self):
        glyphs = {'A': {'components': [], 'contours': 1},
                  'acute': {'components': [], 'contours': 1},
                  'acutecomb': {'components': [{'base': 'acute'}], 'contours': 0},
                  'Aacute': {'components': [{'base': 'A'}, {'base': 'acutecomb'}], 'contours': 0},
                  'broken': {'components': [{'base': 'missing'}], 'contours': 0}}
        self.assertEqual(check_design.leaves('Aacute', glyphs), ['A', 'acute'])
        self.assertIsNone(check_design.leaves('broken', glyphs))


    def test_only_new_points_off_the_draft_grid_are_listed(self):
        from fontgarden.check_changes import new_points_off_grid
        base = '<point x="98" y="0" type="line"/>'
        text = base + '<point x="104" y="64"/><point x="130" y="8" type="curve"/><point x="16" y="-3"/>'
        self.assertEqual(new_points_off_grid(text, base, 8), [(16.0, -3.0), (130.0, 8.0)])
        self.assertEqual(new_points_off_grid(text, text, 8), [])

    def test_grid_levels(self):
        from fontgarden.grid_levels import level
        self.assertEqual([level(value, 8, 2) for value in (96, 98, 99, -16, -6)], [0, 1, 2, 0, 1])


if __name__ == '__main__':
    unittest.main()
