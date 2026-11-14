"""Tests of fontgarden/accent_placement.py on a small UFO and a small compiled font."""
import contextlib
import io
import plistlib
import tempfile
import unittest
from pathlib import Path

from fontTools.fontBuilder import FontBuilder
from fontTools.pens.ttGlyphPen import TTGlyphPen

from fontgarden import accent_placement

# Base letter: (code point, left, right, top). Each is a box on the baseline.
BASES = {'x': (0x78, 0, 100, 500), 'H': (0x48, 0, 140, 700), 'l': (0x6C, 0, 40, 750),
         'a': (0x61, 20, 120, 500), 'e': (0x65, 10, 90, 500), 'o': (0x6F, 0, 160, 500),
         'A': (0x41, 0, 200, 700)}
# Mark: (code point, combining code point, left, right). Each is a box from 560 to 620.
MARKS = {'acute': (0xB4, 0x301, 0, 40), 'dieresis': (0xA8, 0x308, 0, 80), 'grave': (0x60, 0x300, 10, 50)}


def accents():
    """Glyph name: (code point, base, mark, dx, dy), each mark centered over its base."""
    import unicodedata
    found = {}
    for base, (code_point, left, right, top) in BASES.items():
        for mark, (_, combining, mark_left, mark_right) in MARKS.items():
            character = unicodedata.normalize('NFC', chr(code_point) + chr(combining))
            if len(character) == 1:
                dx = (left + right) / 2 - (mark_left + mark_right) / 2
                found[f'{base}{mark}'] = (ord(character), base, mark, dx, top - 500)
    return found


def box(left, bottom, right, top):
    return [(left, bottom), (right, bottom), (right, top), (left, top)]


def write_ufo(root, moved=None):
    """A project with one master. `moved` names an accented letter to displace by 40 units."""
    ufo = root / 'sources/Test-Regular.ufo'
    (ufo / 'glyphs').mkdir(parents=True)
    (root / 'sources/config.yaml').write_text('sources:\n  - Test-Regular.ufo\n')
    texts = {}

    def glif(name, code_point, body):
        return (f'<?xml version="1.0" encoding="UTF-8"?>\n<glyph name="{name}" format="2">\n'
                f'\t<advance width="200"/>\n\t<unicode hex="{code_point:04X}"/>\n'
                f'\t<outline>\n{body}\t</outline>\n</glyph>\n')

    def contour(points):
        lines = ''.join(f'\t\t\t<point x="{x}" y="{y}" type="line"/>\n' for x, y in points)
        return f'\t\t<contour>\n{lines}\t\t</contour>\n'

    for name, (code_point, left, right, top) in BASES.items():
        texts[name] = glif(name, code_point, contour(box(left, 0, right, top)))
    for name, (code_point, _, left, right) in MARKS.items():
        texts[name] = glif(name, code_point, contour(box(left, 560, right, 620)))
    for name, (code_point, base, mark, dx, dy) in accents().items():
        dx += 40 if name == moved else 0
        texts[name] = glif(name, code_point, f'\t\t<component base="{base}"/>\n'
                           f'\t\t<component base="{mark}" xOffset="{dx:g}" yOffset="{dy:g}"/>\n')
    # A capital letter gets an underscore, so that a and A are two files on every file system.
    files = {name: ''.join(c + '_' if c.isupper() else c for c in name) + '.glif' for name in texts}
    (ufo / 'glyphs/contents.plist').write_bytes(plistlib.dumps(files))
    for name, text in texts.items():
        (ufo / 'glyphs' / files[name]).write_text(text)
    return root


def write_font(path):
    """The same glyphs as a compiled font."""
    glyphs, code_points = {}, {}

    def outline(points):
        pen = TTGlyphPen(None)
        pen.moveTo(points[0])
        for point in points[1:]:
            pen.lineTo(point)
        pen.closePath()
        return pen.glyph()

    for name, (code_point, left, right, top) in BASES.items():
        glyphs[name], code_points[code_point] = outline(box(left, 0, right, top)), name
    for name, (code_point, _, left, right) in MARKS.items():
        glyphs[name], code_points[code_point] = outline(box(left, 560, right, 620)), name
    for name, (code_point, base, mark, dx, dy) in accents().items():
        pen = TTGlyphPen(glyphs)
        pen.addComponent(base, (1, 0, 0, 1, 0, 0))
        pen.addComponent(mark, (1, 0, 0, 1, int(dx), int(dy)))
        glyphs[name], code_points[code_point] = pen.glyph(), name
    pen = TTGlyphPen(None)
    glyphs['.notdef'] = pen.glyph()
    builder = FontBuilder(1000, isTTF=True)
    builder.setupGlyphOrder(['.notdef', *[name for name in glyphs if name != '.notdef']])
    builder.setupCharacterMap(code_points)
    builder.setupGlyf(glyphs)
    # The left side bearing must be the left edge of the outline, or fontTools moves the glyph.
    table = builder.font['glyf']
    bearings = {}
    for name in builder.font.getGlyphOrder():
        table[name].recalcBounds(table)
        bearings[name] = (200, getattr(table[name], 'xMin', 0))
    builder.setupHorizontalMetrics(bearings)
    builder.setupHorizontalHeader()
    builder.setupOS2()
    builder.setupPost()
    builder.setupNameTable({'familyName': 'Test', 'styleName': 'Regular'})
    builder.save(path)


class AccentPlacement(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)

    def tearDown(self):
        self.temp.cleanup()

    def run_check(self, root):
        output = io.StringIO()
        with contextlib.redirect_stdout(output):
            status = accent_placement.check(root=root)
        return status, output.getvalue()

    def test_centered_marks_are_as_predicted(self):
        status, text = self.run_check(write_ufo(self.root / 'font'))
        self.assertEqual(status, 0, text)
        self.assertIn('0 listed', text)
        self.assertIn('anchors are missing: A `top`', text)

    def test_a_displaced_mark_is_listed(self):
        status, text = self.run_check(write_ufo(self.root / 'font', moved='eacute'))
        self.assertEqual(status, 1)
        self.assertIn('eacute (acute): +40, +0 from the position', text)
        self.assertEqual(text.count('from the position'), 1, text)

    def test_every_method_predicts_centered_marks_of_a_compiled_font(self):
        path = self.root / 'Test.ttf'
        write_font(path)
        font = accent_placement.Font.from_compiled(path)
        self.assertEqual(len(list(accent_placement.observations(font))), len(accents()))
        for method in accent_placement.METHODS:
            found = accent_placement.errors(font, method)
            self.assertTrue(found, method)
            self.assertEqual(max(error for _, error in found), 0, method)

    def test_a_cap_mark_is_predicted_from_the_cap_height(self):
        font = accent_placement.Font.from_ufo(write_ufo(self.root / 'font') / 'sources/Test-Regular.ufo')
        row = next(row for row in accent_placement.observations(font) if row['glyph'] == 'Aacute')
        self.assertEqual(accent_placement.outline_position(font, row), (80, 200))


class ReferenceFonts(unittest.TestCase):
    def test_one_upright_font_is_chosen_for_each_family(self):
        from fontgarden import reference_fonts
        with tempfile.TemporaryDirectory() as temp:
            for name in ('inter/Inter[wght].ttf', 'inter/Inter-Italic[wght].ttf',
                         'poppins/Poppins-Bold.ttf', 'poppins/Poppins-Regular.ttf',
                         'poppins/Poppins-Italic.ttf'):
                path = Path(temp) / name
                path.parent.mkdir(exist_ok=True)
                path.write_bytes(b'')
            chosen = [path.name for path in reference_fonts.one_for_each_family(temp)]
            self.assertEqual(chosen, ['Inter[wght].ttf', 'Poppins-Regular.ttf'])
            self.assertEqual(len(reference_fonts.fonts(temp, italic=True)), 5)

    def test_each_trusted_family_has_a_reason(self):
        from fontgarden import reference_fonts
        families = reference_fonts.families()
        self.assertTrue(families)
        for family, reason in families.items():
            self.assertRegex(family, r'^[a-z0-9]+$')
            self.assertGreater(len(reason), 20, family)


if __name__ == '__main__':
    unittest.main()
