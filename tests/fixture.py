"""A small font project for the tests: two masters and four glyphs.

The first designspace source has a `stylename`; the second has none, so its
master name comes from the UFO file name.
"""
import contextlib
import os
import plistlib
from pathlib import Path

GREEN, PURPLE, YELLOW, ORANGE = '0,1,0,1', '0.54,0.44,0.88,1', '1,1,0,1', '1,0.5,0,1'

DESIGN = '''[targets.Regular.Latin]
vertical_stem = [92, 108]
horizontal_stroke = [78, 100]
stroke_limit = 180

[colors.green]
rgba = [[0, 1, 0, 1]]
policy = "Approved."

[colors.yellow]
rgba = [[1, 1, 0, 1]]
policy = "Close."

[colors.orange]
rgba = [[1, 0.5, 0, 1]]
policy = "Better."

[colors.red]
rgba = [[1, 0, 0, 1]]
policy = "Broken."

[colors.purple]
rgba = [[0.54, 0.44, 0.88, 1]]
policy = "Draft."
'''

HELD_OUT = '''[redraw]
glyphs = ["square"]

[bold]
glyphs = ["square"]

[repair]
glyphs = ["square"]

[relatives]
cases = [{ glyph = "n", from = ["square"] }]
'''

DESIGNSPACE = '''<?xml version='1.0' encoding='UTF-8'?>
<designspace format="5">
  <axes>
    <axis name="Weight" tag="wght" default="400" minimum="400" maximum="700"/>
  </axes>
  <sources>
    <source stylename="Regular" filename="Test-Regular.ufo">
      <location><dimension name="Weight" xvalue="400"/></location>
    </source>
    <source filename="Test-Bold.ufo">
      <location><dimension name="Weight" xvalue="700"/></location>
    </source>
  </sources>
</designspace>
'''


def glif(name, mark=None, right=100, advance=200, unicode=None, components=(), contour=True):
    """GLIF text of a square glyph, a composite or an empty glyph."""
    lines = [f'<?xml version="1.0" encoding="UTF-8"?>',
             f'<glyph name="{name}" format="2">',
             f'\t<advance width="{advance}"/>']
    if unicode:
        lines.append(f'\t<unicode hex="{unicode}"/>')
    lines.append('\t<outline>')
    if contour:
        lines += ['\t\t<contour>',
                  '\t\t\t<point x="0" y="0" type="line"/>',
                  f'\t\t\t<point x="{right}" y="0" type="line"/>',
                  f'\t\t\t<point x="{right}" y="100" type="line"/>',
                  '\t\t\t<point x="0" y="100" type="line"/>',
                  '\t\t</contour>']
    lines += [f'\t\t<component base="{base}"/>' for base in components]
    lines.append('\t</outline>')
    if mark:
        lines += ['\t<lib>', '\t\t<dict>', '\t\t\t<key>public.markColor</key>',
                  f'\t\t\t<string>{mark}</string>', '\t\t</dict>', '\t</lib>']
    lines.append('</glyph>')
    return '\n'.join(lines) + '\n'


def glyphs(master):
    """Glyph name to GLIF text in one master."""
    wide = 100 if master == 'Regular' else 140
    return {
        'square': glif('square', GREEN, right=wide, unicode='25A1'),
        'n': glif('n', GREEN, right=wide, unicode='006E'),
        'squarecomposite': glif('squarecomposite', ORANGE, contour=False, components=['square']),
        'space': glif('space', GREEN, contour=False, unicode='0020'),
    }


def write_project(root):
    """Write the project into `root` and return `root`."""
    root = Path(root)
    sources = root / 'sources'
    sources.mkdir(parents=True)
    (sources / 'config.yaml').write_text('sources:\n  - Test.designspace\noutputDir: ../fonts\n')
    (sources / 'Test.designspace').write_text(DESIGNSPACE)
    (root / 'CONTEXT.md').write_text(f'# Test rules\n\nR1. A rule.\n\n```toml\n{DESIGN}```\n')
    (sources / 'held-out-glyphs.toml').write_text(HELD_OUT)
    for master in ('Regular', 'Bold'):
        ufo = sources / f'Test-{master}.ufo'
        (ufo / 'glyphs').mkdir(parents=True)
        texts = glyphs(master)
        (ufo / 'lib.plist').write_bytes(plistlib.dumps({'public.glyphOrder': list(texts)}))
        (ufo / 'glyphs/contents.plist').write_bytes(
            plistlib.dumps({name: f'{name}.glif' for name in texts}))
        for name, text in texts.items():
            (ufo / f'glyphs/{name}.glif').write_text(text)
    return root


@contextlib.contextmanager
def working_directory(path):
    before = os.getcwd()
    os.chdir(path)
    try:
        yield Path(path)
    finally:
        os.chdir(before)
