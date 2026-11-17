"""Tests of fgtools/media_layout.py: the lattice, the typesetter and the checks of a sheet."""
import tempfile
import tomllib
import unittest
from pathlib import Path

from fgtools import media, media_layout


def font_file(characters, family='A A', advance=500):
    """A font in which each character is a box of the cap height: 700 of 1000 units."""
    from fontTools.fontBuilder import FontBuilder
    from fontTools.pens.ttGlyphPen import TTGlyphPen
    path = Path(tempfile.mkdtemp()) / 'Font-Regular.ttf'
    names = ['.notdef'] + [f'u{ord(c):04X}' for c in characters]

    def box(name):
        pen = TTGlyphPen(None)
        if name not in ('.notdef', 'u0020'):
            pen.moveTo((50, 0)); pen.lineTo((50, 700)); pen.lineTo((450, 700)); pen.lineTo((450, 0)); pen.closePath()
        return pen.glyph()
    builder = FontBuilder(1000, isTTF=True)
    builder.setupGlyphOrder(names)
    builder.setupCharacterMap({ord(c): f'u{ord(c):04X}' for c in characters})
    builder.setupGlyf({name: box(name) for name in names})
    builder.setupHorizontalMetrics({name: (advance, 50) for name in names})
    builder.setupHorizontalHeader(ascent=800, descent=-200)
    builder.setupNameTable({'familyName': family, 'styleName': 'Regular'})
    builder.setupOS2(sCapHeight=700, sxHeight=500)
    builder.setupPost()
    builder.save(path)
    return path


def type_with(characters, family='A A'):
    return media_layout.Type(font_file(characters, family), family, 400.0, 400.0, 1000, 0.75, 0.5, -0.25)


def sheet_on(name='portrait', characters='ABab '):
    grid = media_layout.lattice(media.canvases()[name])
    return media_layout.Sheet(grid, type_with(characters), name='test')


class Lattice(unittest.TestCase):
    def test_the_live_area_is_a_whole_number_of_modules_and_the_margin_is_the_rest(self):
        grid = media_layout.lattice({'width': 1080, 'height': 1350, 'safe': {'left': 40, 'right': 40}})
        self.assertEqual((grid['live'], grid['origin']), ((16, 20), (28, 35)))
        self.assertEqual(grid['text'], (1, 1, 14, 18))

    def test_the_text_area_is_inside_the_safe_area_of_the_platform(self):
        grid = media_layout.lattice(media.canvases()['vertical'])
        self.assertEqual((grid['live'], grid['text']), ((16, 28), (2, 4, 11, 14)))

    def test_every_canvas_has_a_text_area(self):
        for name, canvas in media.canvases().items():
            grid = media_layout.lattice(canvas)
            self.assertGreaterEqual(grid['text'][2], 8, name)
            self.assertGreaterEqual(grid['text'][3], 6, name)

    def test_the_module_of_a_project_changes_the_lattice(self):
        grid = media_layout.lattice({'width': 1000, 'height': 1000}, {'module': 100})
        self.assertEqual((grid['live'], grid['origin']), ((8, 8), (100, 100)))


class Typesetting(unittest.TestCase):
    def test_a_line_is_measured_in_parts_of_the_em(self):
        advance, left, right = type_with('AB').measure('AB')
        self.assertEqual((advance, left, right), (1.0, 0.05, 0.95))

    def test_the_word_is_chosen_to_fill_the_measure_and_the_size_stays(self):
        font = type_with('ABCDEF ')
        self.assertEqual(font.fit(['AB', 'ABCD', 'ABCDEF'], 256, 128), 'ABCD')           # ink 1.9 em of 2 em
        self.assertEqual(font.fit(['AB', 'ABCD', 'ABCDEF'], 256, 128, used=['ABCD']), None)
        self.assertEqual(font.fit(['AB', 'ABCD', 'ABCDEF'], 256, 128, used=['ABCD'], least=0), 'AB')
        self.assertIn(font.fit(['AB', 'ABCD', 'Q'], 448, 128), ('AB ABCD', 'ABCD AB'))    # a pair fills 3.4 of 3.5 em

    def test_a_word_with_a_character_that_the_font_lacks_is_never_chosen(self):
        self.assertEqual(type_with('AB').fit(['ABQ', 'AB'], 400, 100, least=0), 'AB')

    def test_a_paragraph_is_broken_at_the_measure(self):
        font = type_with('AB ')
        lines = font.lines('AB AB AB AB AB AB', 200, 64)                 # a character is 32 pixels wide
        self.assertEqual(lines, ['AB AB', 'AB AB', 'AB AB'])
        self.assertTrue(all(font.measure(line)[0] * 64 <= 200 for line in lines))


class Checks(unittest.TestCase):
    def test_a_text_on_the_lattice_has_no_fault(self):
        sheet = sheet_on()
        sheet.page()
        advance = sheet.text('AB', 0, 1, 256, optical=True)
        self.assertEqual((advance, sheet.check()), (256, []))
        kind, x, baseline, size = sheet.pages[0]['items'][0][:4]
        self.assertEqual((x, baseline), (92 - 0.05 * 256, 99 + 64 + 192))    # the ink on the column line, the cap top on the row line

    def test_a_size_that_is_not_on_the_scale_is_a_fault(self):
        sheet = sheet_on()
        sheet.page()
        sheet.text('AB', 0, 1, 200)
        self.assertIn('not on the scale', sheet.check()[0])

    def test_a_position_off_the_unit_is_a_fault(self):
        sheet = sheet_on()
        sheet.page()
        sheet.text('AB', 0.05, 1, 64)
        self.assertIn('not on the unit', sheet.check()[0])

    def test_ink_outside_the_text_area_is_a_fault(self):
        sheet = sheet_on()
        sheet.page()
        sheet.text('ABABABAB', 0, 1, 256)
        self.assertIn('outside the text area', sheet.check()[0])

    def test_a_text_that_the_font_cannot_set_is_left_out(self):
        sheet = sheet_on()
        sheet.page()
        self.assertEqual(sheet.text('Q', 0, 1, 64), 0)
        self.assertEqual(sheet.pages[0]['items'], [])

    def test_more_than_two_weights_is_a_fault_unless_the_subject_is_the_axis(self):
        sheet = sheet_on()
        sheet.page()
        for row, weight in enumerate((400, 500, 600)):
            sheet.text('A', 0, 1 + row, 64, weight)
        self.assertIn('3 weights', sheet.check()[0])
        sheet.faults.clear()
        sheet.axis = True
        self.assertEqual(sheet.check(), [])


class Plot(unittest.TestCase):
    def test_the_plot_file_has_one_element_for_each_line_with_the_origin_at_the_bottom(self):
        sheet = sheet_on('square')
        sheet.page()
        sheet.rule(0)
        sheet.text('AB', 0, 1, 64)
        path = Path(tempfile.mkdtemp()) / 'test.plot'
        media_layout.plot([sheet], path.with_suffix('.png'), path)
        lines = path.read_text().splitlines()
        self.assertEqual(lines[0], 'canvas\t1080\t1080')
        self.assertTrue(lines[3].startswith('page\t0.000000\t32\t32\t32'))
        self.assertEqual(lines[4], 'line\t92\t988\t988\t988\t2\t64\t64\t64\t255')
        self.assertEqual(lines[5], 'text\t92\t876\t64\t400\t224\t224\t224\t255\t\tAB')

    def test_the_print_page_is_written_at_half_size_with_dark_ink_on_a_light_ground(self):
        sheet = sheet_on('page')
        sheet.page()
        sheet.text('AB', 0, 1, 64)
        path = Path(tempfile.mkdtemp()) / 'test.plot'
        media_layout.plot([sheet], path.with_suffix('.pdf'), path)
        lines = path.read_text().splitlines()
        self.assertEqual(lines[0], 'canvas\t842\t595')
        self.assertIn('\t32\t32\t32\t255\t', lines[4])
        self.assertEqual(lines[4].split('\t')[3], '32')                     # 64 pixels are 32 points


class Formats(unittest.TestCase):
    def test_every_default_format_draws_on_each_of_its_canvases_without_a_fault(self):
        font = type_with('ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789 .,-', family='Test Font')
        facts = {'version': '1.000', 'glyphs': 70, 'characters': 66, 'instances': [400.0], 'scripts': ['Latin']}
        from types import SimpleNamespace
        words = tomllib.loads(media.WORDS.read_text())
        job = SimpleNamespace(type=font, brand={'text': {'tagline': 'A test font'}}, facts=facts, family='Test Font',
                              words=words, glyphs=['a', 'G'], description='A font for the tests of the formats.',
                              outline=lambda character: None, url='example.org', designer='A Designer')
        formats = media.load_brand(SimpleNamespace(root=Path(tempfile.mkdtemp())))['format']
        drawn = 0
        for name, table in formats.items():
            for canvas in table['canvases'] + ['page']:
                sheet, reason = media.compose(table, job, media.canvases()[canvas], {}, {}, name)
                if sheet is None:
                    self.assertIn(reason, ('the font has one weight', 'the font has one script'), name)
                    continue
                drawn += 1
                self.assertEqual(sheet.faults, [], f'{name} on {canvas}')
        self.assertGreater(drawn, 12)


if __name__ == '__main__':
    unittest.main()
