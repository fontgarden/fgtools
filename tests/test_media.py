"""Tests of fgtools/media.py: the formats, the outputs, the texts and the arguments, without DesignBot."""
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace

from fgtools import media

METRICS = {'upm': 1024, 'x_height': 0.5625, 'ascender': 1.0, 'descender': -0.25, 'version': '1.000',
           'glyphs': 900, 'characters': 690}


def project_with(formats='', scripts=None, brand='[text]\nwords = ["A"]\n'):
    """A project with brand.toml, formats.toml and the scripts {name: folder}."""
    root = Path(tempfile.mkdtemp())
    folder = root / 'documentation/media'
    folder.mkdir(parents=True)
    (folder / 'brand.toml').write_text(brand)
    if formats:
        (folder / 'formats.toml').write_text(formats)
    for name, kind_folder in (scripts or {}).items():
        (folder / kind_folder).mkdir(exist_ok=True)
        (folder / kind_folder / f'{name}.rs').write_text('fn main() {}\n')
    return SimpleNamespace(root=root)


def font_with(characters, family='A A'):
    """The facts of a font that has these characters."""
    from fontTools.fontBuilder import FontBuilder
    from fontTools.pens.ttGlyphPen import TTGlyphPen
    path = Path(tempfile.mkdtemp()) / 'Font-Regular.ttf'
    names = ['.notdef'] + [f'u{ord(c):04X}' for c in characters]
    builder = FontBuilder(1000, isTTF=True)
    builder.setupGlyphOrder(names)
    builder.setupCharacterMap({ord(c): f'u{ord(c):04X}' for c in characters})
    builder.setupGlyf({name: TTGlyphPen(None).glyph() for name in names})
    builder.setupHorizontalMetrics({name: (500, 0) for name in names})
    builder.setupHorizontalHeader()
    builder.setupNameTable({'familyName': family, 'styleName': 'Regular'})
    builder.setupOS2()
    builder.setupPost()
    builder.save(path)
    return (path, family, 400.0, 400.0, 0.7, METRICS)


class Media(unittest.TestCase):
    def test_every_canvas_has_a_size_and_a_safe_area_inside_it(self):
        for name, canvas in media.canvases().items():
            safe = canvas['safe']
            self.assertGreater(canvas['width'] - safe['left'] - safe['right'], canvas['width'] / 2, name)
            self.assertGreater(canvas['height'] - safe['top'] - safe['bottom'], canvas['height'] / 3, name)

    def test_a_project_without_files_has_the_default_formats(self):
        layout = SimpleNamespace(root=Path(tempfile.mkdtemp()))
        formats = media.load_brand(layout)['format']
        self.assertIn('specimen-poster', formats)
        self.assertEqual((formats['weight-axis']['kind'], formats['weight-axis']['own']), ('video', False))
        self.assertTrue(formats['glyph-detail']['script'].is_file())
        for name, table in formats.items():
            for canvas in table['canvases']:
                self.assertIn(canvas, media.canvases(), name)

    def test_a_project_changes_a_default_format_and_adds_its_own(self):
        layout = project_with('[specimen-poster]\ncanvases = ["square"]\ncaption = "A poster"\n\n'
                              '[loop]\ncanvases = ["vertical"]\n',
                              {'loop': 'videos', 'release': 'images'})
        formats = media.load_brand(layout)['format']
        self.assertEqual((formats['specimen-poster']['canvases'], formats['specimen-poster']['caption']),
                         (['square'], 'A poster'))
        self.assertEqual((formats['loop']['kind'], formats['loop']['own']), ('video', True))
        self.assertTrue(formats['release']['own'])
        self.assertFalse(formats['link-card']['own'])
        found = media.outputs(layout, {'format': formats}, ['specimen-poster', 'loop'])
        self.assertEqual([(name, canvas) for name, _, canvas, _ in found],
                         [('specimen-poster', 'square'), ('loop', 'vertical')])

    def test_a_format_without_a_script_or_with_an_unknown_canvas_stops_the_command(self):
        with self.assertRaises(SystemExit):
            media.load_brand(project_with('[poster]\ncanvases = ["portrait"]\n'))
        layout = project_with('[poster]\ncanvases = ["poster-size"]\n', {'poster': 'images'})
        with self.assertRaises(SystemExit):
            media.outputs(layout, media.load_brand(layout))

    def test_the_texts_are_limited_to_what_the_font_can_set(self):
        facts = font_with('ABab G')
        brand = {'text': {'words': ['AB', 'Grid', 'ab'], 'glyphs': ['a', 'Q']}}
        self.assertEqual(media.texts(brand, {'words': 'words'}, facts), ['AB', 'ab'])
        self.assertEqual(media.texts(brand, {'words': 'glyphs'}, facts), ['a'])
        self.assertEqual(media.texts(brand, {'words': ['BA', 'no']}, facts), ['BA'])
        self.assertEqual(media.texts(brand, {'words': 'lines'}, facts), ['A A'])

    def test_a_font_with_few_glyphs_shows_the_letters_that_exist(self):
        facts = font_with('HOno', family='New Font')
        self.assertEqual(media.texts({'text': {'words': ['Font']}}, {'words': 'words'}, facts), ['HO', 'no'])
        self.assertEqual(media.texts({}, {'words': 'glyphs'}, facts), ['n', 'H', 'O', 'o'])

    def test_the_arguments_carry_the_canvas_the_font_and_the_brand(self):
        canvas = media.canvases()['vertical']
        brand = {'colors': {'ground': '#000000'}, 'text': {'words': ['AB', 'A']}}
        facts = font_with('AB ')
        values = dict(item.split('=', 1) for item in media.arguments(brand, {}, canvas, facts, 'out.mp4', True))
        self.assertEqual((values['width'], values['height'], values['safe']), ('1080', '1920', '270,195,672,120'))
        self.assertEqual((values['family'], values['weight'], values['words']), ('A A', '400,400', 'AB|A'))
        self.assertEqual((values['ground'], values['overlay']), ('#000000', '1'))
        self.assertEqual((values['upm'], values['grid'], values['glyphs']), ('1024', '64', '900'))
        self.assertEqual(values['charset'], '20-20,41-42')

    def test_the_commit_of_a_folder_outside_git_is_none(self):
        self.assertIsNone(media.commit(tempfile.mkdtemp()))


if __name__ == '__main__':
    unittest.main()
