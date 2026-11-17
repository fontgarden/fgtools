"""Tests of fgtools/media.py: the outputs and the arguments, without DesignBot."""
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace

from fgtools import media


def project_with(formats, scripts):
    root = Path(tempfile.mkdtemp())
    folder = root / 'documentation/media'
    folder.mkdir(parents=True)
    for name in scripts:
        (folder / f'{name}.rs').write_text('fn main() {}\n')
    return SimpleNamespace(root=root), {'format': formats}


class Media(unittest.TestCase):
    def test_every_canvas_has_a_size_and_a_safe_area_inside_it(self):
        for name, canvas in media.canvases().items():
            safe = canvas['safe']
            self.assertGreater(canvas['width'] - safe['left'] - safe['right'], canvas['width'] / 2, name)
            self.assertGreater(canvas['height'] - safe['top'] - safe['bottom'], canvas['height'] / 3, name)

    def test_one_output_is_one_format_on_one_canvas(self):
        layout, brand = project_with({'poster': {'kind': 'image', 'canvases': ['portrait', 'square']},
                                      'loop': {'kind': 'video', 'canvases': ['vertical']}}, ['poster', 'loop'])
        found = media.outputs(layout, brand)
        self.assertEqual([(name, canvas) for name, _, canvas, _ in found],
                         [('poster', 'portrait'), ('poster', 'square'), ('loop', 'vertical')])
        self.assertEqual(len(media.outputs(layout, brand, ['poster'], 'square')), 1)

    def test_a_format_without_a_script_or_with_an_unknown_canvas_stops_the_command(self):
        layout, brand = project_with({'poster': {'canvases': ['portrait']}}, [])
        with self.assertRaises(SystemExit):
            media.outputs(layout, brand)
        layout, brand = project_with({'poster': {'canvases': ['poster-size']}}, ['poster'])
        with self.assertRaises(SystemExit):
            media.outputs(layout, brand)

    def test_the_arguments_carry_the_canvas_the_font_and_the_brand(self):
        canvas = media.canvases()['vertical']
        brand = {'colors': {'ground': '#000000'}, 'text': {'words': ['Grid', 'Type']}}
        metrics = {'upm': 1024, 'x_height': 0.5625, 'ascender': 1.0, 'descender': -0.25, 'version': '1.000',
                   'glyphs': 900, 'characters': 690}
        facts = (Path('fonts/variable/Font[wght].ttf'), 'A Font', 400.0, 700.0, 0.75, metrics)
        values = dict(item.split('=', 1) for item in media.arguments(brand, {}, canvas, facts, 'out.mp4', True))
        self.assertEqual((values['width'], values['height'], values['safe']), ('1080', '1920', '270,195,672,120'))
        self.assertEqual((values['family'], values['weight'], values['words']), ('A Font', '400,700', 'Grid|Type'))
        self.assertEqual((values['ground'], values['overlay']), ('#000000', '1'))
        self.assertEqual((values['upm'], values['grid'], values['glyphs']), ('1024', '64', '900'))

    def test_a_character_without_a_glyph_is_reported(self):
        from fontTools.fontBuilder import FontBuilder
        from fontTools.pens.ttGlyphPen import TTGlyphPen
        path = Path(tempfile.mkdtemp()) / 'Font-Regular.ttf'
        builder = FontBuilder(1000, isTTF=True)
        builder.setupGlyphOrder(['.notdef', 'A', 'space'])
        builder.setupCharacterMap({ord('A'): 'A', ord(' '): 'space'})
        builder.setupGlyf({name: TTGlyphPen(None).glyph() for name in ['.notdef', 'A', 'space']})
        builder.setupHorizontalMetrics({name: (500, 0) for name in ['.notdef', 'A', 'space']})
        builder.setupHorizontalHeader()
        builder.setupNameTable({'familyName': 'A A', 'styleName': 'Regular'})
        builder.setupOS2()
        builder.setupPost()
        builder.save(path)
        facts = (path, 'A A', 400.0, 400.0, 0.7, {})
        self.assertEqual(media.missing_characters({'text': {'words': ['AB', 'A']}}, facts), ['B'])
        self.assertEqual(media.missing_characters({'text': {'words': ['A A']}}, facts), [])


if __name__ == '__main__':
    unittest.main()
