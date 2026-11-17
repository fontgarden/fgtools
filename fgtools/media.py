"""Render the marketing media of a font project with DesignBot.

A project keeps its formats in `documentation/media/`: one DesignBot script
(`.rs`) for each format, for example a specimen poster or an animation of the
weight axis, and `brand.toml` with the colors, the words and the list of
canvases for each format. The designer changes these files for the style of
the font. The canvases (the sizes and the safe areas of the platforms) are the
same for every font and are in `fgtools/media_canvases.toml`.

    fgtools media                       every format on each of its canvases
    fgtools media weight-axis           one format
    fgtools media --canvas vertical     one canvas
    fgtools media --safe-areas          draw the safe area on each picture
    fgtools media --list                list the formats and the canvases

The command gives each script a module `brief` with the canvas, the safe area,
the family name, the font file, the weight range, the colors and the texts,
so that a script holds only the layout. One output is one format on one
canvas: `output/media/<format>/<family>_<format>_<canvas>.<extension>`. An
image is a PNG, a carousel is numbered PNG pages and one PDF (the document
post of LinkedIn), and a video is an MP4. Beside each output is a JSON record
with the caption, the alternative text, the size and the commit of the sources.
`output/media/index.html` is a review page that shows every output.

The command renders nothing when the font has no glyph for a character of
the texts in brand.toml, because DesignBot would draw it with a system font.
It does not yet check the text that a script writes itself.

It needs the `designbot` command, and `ffmpeg` for video:

    cargo install --git https://github.com/eliheuer/designbot designbot-cli
"""
from __future__ import annotations

import argparse
import json
import shutil
import subprocess
import sys
import tomllib
from pathlib import Path

from fgtools import project

CANVASES = Path(__file__).with_name('media_canvases.toml')
BRIEF = Path(__file__).with_name('media_brief.rs')
EXTENSION = {'image': 'png', 'carousel': 'png', 'video': 'mp4'}
INSTALL = 'cargo install --git https://github.com/eliheuer/designbot designbot-cli'


def slug(text):
    return ''.join(c.lower() if c.isalnum() else '-' for c in text).strip('-')


def canvases():
    return tomllib.loads(CANVASES.read_text())['canvas']


def font_facts(layout):
    """The font file to draw with, and the range of its weight axis."""
    from fontTools.ttLib import TTFont
    variable = sorted((layout.fonts / 'variable').glob('*.ttf'))
    static = sorted((layout.fonts / 'ttf').glob('*.ttf'))
    if not variable and not static:
        raise SystemExit('No built fonts. Run `make build` first.')
    path = (variable or static)[0]
    font = TTFont(path, lazy=True)
    family = font['name'].getBestFamilyName()
    low = high = float(font['OS/2'].usWeightClass)
    if 'fvar' in font:
        for axis in font['fvar'].axes:
            if axis.axisTag == 'wght':
                low, high = axis.minValue, axis.maxValue
    upm, os2 = font['head'].unitsPerEm, font['OS/2']
    cap = getattr(os2, 'sCapHeight', 0) / upm or 0.7
    metrics = {'upm': upm, 'x_height': getattr(os2, 'sxHeight', 0) / upm or 0.5,
               'ascender': font['hhea'].ascent / upm, 'descender': font['hhea'].descent / upm,
               'version': f'{font["head"].fontRevision:.3f}', 'glyphs': font['maxp'].numGlyphs,
               'characters': len(font.getBestCmap())}
    return path, family, low, high, cap, metrics


def missing_characters(brand, facts):
    """The characters of the texts of brand.toml that the font has no glyph for. DesignBot draws
    such a character with a system font, and a picture of another font is worse than no picture."""
    from fontTools.ttLib import TTFont
    covered = TTFont(facts[0], lazy=True).getBestCmap()
    text = brand.get('text', {})
    words = [word for table in brand.get('format', {}).values() for word in table.get('words', [])]
    used = ''.join([facts[1], text.get('tagline', ''), text.get('designer', ''), text.get('url', ''),
                    *text.get('words', []), *words])
    return sorted({character for character in used if ord(character) not in covered})


def commit(root):
    result = subprocess.run(['git', 'rev-parse', '--short', 'HEAD'], cwd=root, capture_output=True, text=True)
    return result.stdout.strip() or None


def outputs(layout, brand, names=None, only_canvas=None):
    """[(format name, format table, canvas name, canvas table)] to render."""
    known, formats = canvases(), brand.get('format', {})
    for name in names or []:
        if name not in formats:
            raise SystemExit(f'No format `{name}` in brand.toml. Formats: {", ".join(formats) or "none"}.')
    found = []
    for name, table in formats.items():
        if names and name not in names:
            continue
        if not (layout.root / 'documentation/media' / f'{name}.rs').is_file():
            raise SystemExit(f'brand.toml names the format `{name}`, and documentation/media/{name}.rs does not exist.')
        if table.get('kind', 'image') not in EXTENSION:
            raise SystemExit(f'Format `{name}`: kind is image, carousel or video.')
        for canvas in table.get('canvases', []):
            if canvas not in known:
                raise SystemExit(f'Format `{name}`: no canvas `{canvas}`. Canvases: {", ".join(known)}.')
            if only_canvas in (None, canvas):
                found.append((name, table, canvas, known[canvas]))
    return found


def arguments(brand, table, canvas, facts, output, safe_areas):
    """The key=value arguments that the module `brief` of a script reads."""
    path, family, low, high, cap, metrics = facts
    colors, text, safe = brand.get('colors', {}), brand.get('text', {}), canvas['safe']
    values = {
        'width': canvas['width'], 'height': canvas['height'],
        'safe': f'{safe["top"]},{safe["right"]},{safe["bottom"]},{safe["left"]}',
        'family': family, 'font': path, 'weight': f'{low:g},{high:g}', 'cap': f'{cap:.4f}',
        'ground': colors.get('ground', '#282828'), 'ink': colors.get('ink', '#bebebe'),
        'accent': colors.get('accent', '#e8c547'),
        'tagline': text.get('tagline', ''), 'designer': text.get('designer', ''), 'url': text.get('url', ''),
        'words': '|'.join(table.get('words') or text.get('words') or [family]),
        'overlay': int(bool(safe_areas)), 'output': output,
        'upm': metrics['upm'], 'x_height': f'{metrics["x_height"]:.4f}',
        'ascender': f'{metrics["ascender"]:.4f}', 'descender': f'{metrics["descender"]:.4f}',
        'version': metrics['version'], 'glyphs': metrics['glyphs'], 'characters': metrics['characters'],
        'grid': brand.get('design', {}).get('grid', metrics['upm'] // 16),
    }
    return [f'{key}={value}' for key, value in values.items()]


def program(layout, brand):
    """Write one DesignBot script that holds every format of the project, and return its path.
    DesignBot compiles a script once for each path, so one script for all formats is compiled
    once, and a change to one format compiles in a few seconds."""
    build = layout.root / 'output/media/.build'
    build.mkdir(parents=True, exist_ok=True)
    names = list(brand.get('format', {}))
    parts = []
    for index, name in enumerate(names):
        source = (layout.root / 'documentation/media' / f'{name}.rs').read_text()
        if 'fn main()' not in source:
            raise SystemExit(f'documentation/media/{name}.rs has no `fn main()`.')
        source = source.replace('//!', '//').replace('fn main()', 'pub fn main()', 1)
        parts.append(f'#[allow(dead_code)]\nmod format_{index} {{\nuse crate::brief;\n{source}\n}}\n')
    arms = ''.join(f'        "{name}" => format_{index}::main(),\n' for index, name in enumerate(names))
    parts.append('fn main() {\n    let name = std::env::args().find_map(|a| a.strip_prefix("format=").map(String::from))'
                 '.expect("run the script with `fgtools media`");\n    match name.as_str() {\n' + arms +
                 '        other => panic!("no format {other}"),\n    }\n}\n')
    text = '\n'.join(parts) + BRIEF.read_text()
    script = build / 'media.rs'
    if not script.is_file() or script.read_text() != text:      # an unchanged script is not compiled again
        script.write_text(text)
    return script


def add_silence(path):
    """Give a video a silent audio track: Instagram and X specify audio settings for every video."""
    silent = path.with_name(path.stem + '.audio.mp4')
    result = subprocess.run(['ffmpeg', '-y', '-loglevel', 'error', '-i', str(path), '-f', 'lavfi', '-i',
                             'anullsrc=r=48000:cl=stereo', '-shortest', '-c:v', 'copy', '-c:a', 'aac',
                             '-b:a', '128k', '-movflags', '+faststart', str(silent)], capture_output=True, text=True)
    if result.returncode:
        silent.unlink(missing_ok=True)
        raise SystemExit(f'{path.name}: ffmpeg did not add the audio track.\n{result.stderr[-1000:]}')
    silent.replace(path)


def render(layout, brand, script, name, table, canvas_name, canvas, facts, safe_areas=False):
    """Render one format on one canvas. Returns the list of the files written."""
    kind = table.get('kind', 'image')
    folder = layout.root / 'output/media' / name
    folder.mkdir(parents=True, exist_ok=True)
    stem = f'{slug(facts[1])}_{name}_{canvas_name}' + ('_safe-areas' if safe_areas else '')
    written = []
    for extension in [EXTENSION[kind]] + (['pdf'] if kind == 'carousel' else []):
        output = folder / f'{stem}.{extension}'
        output.unlink(missing_ok=True)
        for old in folder.glob(f'{stem}_[0-9][0-9][0-9][0-9].{extension}'):
            old.unlink()
        command = ['designbot', str(script), '--output', str(output), '--', f'format={name}',
                   *arguments(brand, table, canvas, facts, output, safe_areas)]
        result = subprocess.run(command, cwd=layout.root, capture_output=True, text=True)
        files = [output] if output.is_file() else sorted(folder.glob(f'{stem}_[0-9][0-9][0-9][0-9].{extension}'))
        if result.returncode or not files:
            sys.stderr.write(result.stdout[-2000:] + result.stderr[-4000:])
            raise SystemExit(f'{name} on {canvas_name}: DesignBot did not write {output.name}.')
        if extension == 'mp4':
            add_silence(output)
        written += files
    record = {'format': name, 'kind': kind, 'canvas': canvas_name, 'width': canvas['width'],
              'height': canvas['height'], 'family': facts[1], 'commit': commit(layout.root),
              'caption': table.get('caption', ''), 'alt': table.get('alt', ''),
              'files': [path.name for path in written]}
    (folder / f'{stem}.json').write_text(json.dumps(record, indent=2, ensure_ascii=False) + '\n')
    return written


PAGE = """<!doctype html>
<html lang="en">
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>{family}: media</title>
<style>
  body {{ margin: 0; padding: 32px; background: #1c1c1c; color: #c8c8c8; font: 15px/1.5 system-ui, sans-serif; }}
  h1 {{ font-size: 22px; font-weight: 600; margin: 0 0 4px; }}
  h2 {{ font-size: 17px; font-weight: 600; margin: 48px 0 4px; }}
  p {{ margin: 0 0 12px; max-width: 76ch; color: #9a9a9a; }}
  code {{ color: #c8c8c8; }}
  .row {{ display: flex; flex-wrap: wrap; gap: 24px; align-items: flex-start; margin-top: 16px; }}
  figure {{ margin: 0; }}
  figure img, figure video {{ display: block; height: 420px; width: auto; background: #000; outline: 1px solid #3a3a3a; }}
  figcaption {{ font-size: 13px; color: #9a9a9a; margin-top: 6px; max-width: 420px; }}
  table {{ border-collapse: collapse; margin-top: 12px; }}
  td, th {{ text-align: left; padding: 4px 16px 4px 0; border-bottom: 1px solid #333; font-weight: normal; }}
  th {{ color: #9a9a9a; }}
  .missing {{ color: #e8c547; }}
</style>
<h1>{family}: media</h1>
<p>Every output of <code>fgtools media</code>, from the sources at commit <code>{commit}</code>. One output is one
format on one canvas. The brand and the format scripts are in <code>documentation/media/</code>; the canvases are
the same for every font.</p>
<table><tr><th>Canvas</th><th>Size</th><th>Safe area: top, right, bottom, left</th><th>Use</th></tr>
{canvas_rows}</table>
{sections}
</html>
"""


def write_index(layout, brand, family):
    """Write output/media/index.html: a sheet of every rendered output, for review in a browser."""
    from html import escape
    root = layout.root / 'output/media'
    known = canvases()
    canvas_rows = ''.join(
        f'<tr><td>{escape(name)}</td><td>{c["width"]} x {c["height"]}</td>'
        f'<td>{c["safe"]["top"]}, {c["safe"]["right"]}, {c["safe"]["bottom"]}, {c["safe"]["left"]}</td>'
        f'<td>{escape(c["use"])}</td></tr>\n' for name, c in known.items())
    sections = []
    for name, table in brand.get('format', {}).items():
        records = [json.loads(path.read_text()) for path in sorted((root / name).glob('*.json'))]
        figures = []
        for record in records:
            label = f'{record["canvas"]}, {record["width"]} x {record["height"]}'
            for file in record['files']:
                source = f'{name}/{file}'
                if file.endswith('.mp4'):
                    media = f'<video src="{escape(source)}" autoplay loop muted playsinline></video>'
                elif file.endswith('.pdf'):
                    figures.append(f'<figure><figcaption><a style="color:#c8c8c8" href="{escape(source)}">'
                                   f'{escape(file)}</a> (the carousel as one PDF)</figcaption></figure>')
                    continue
                else:
                    media = f'<img src="{escape(source)}" alt="{escape(record["alt"])}" loading="lazy">'
                figures.append(f'<figure>{media}<figcaption>{escape(label)}<br>{escape(file)}</figcaption></figure>')
        text = lambda key: escape(table.get(key, '')) or f'<span class="missing">no {key} in brand.toml</span>'
        note = '' if records else '<p class="missing">Not rendered.</p>'
        sections.append(f'<h2>{escape(name)}</h2>\n<p>{escape(table.get("kind", "image"))} on '
                        f'{escape(", ".join(table.get("canvases", [])))}.<br>Caption: {text("caption")}<br>'
                        f'Alternative text: {text("alt")}</p>{note}\n<div class="row">{"".join(figures)}</div>')
    page = PAGE.format(family=escape(family), commit=escape(commit(layout.root) or 'unknown'),
                       canvas_rows=canvas_rows, sections='\n'.join(sections))
    (root / 'index.html').write_text(page)
    return root / 'index.html'


def main(argv=None):
    parser = argparse.ArgumentParser(prog='fgtools media', description=__doc__.split('\n')[0])
    parser.add_argument('formats', nargs='*', help='format names; the default is every format of brand.toml')
    parser.add_argument('--canvas', help='one canvas; the default is each canvas of the format')
    parser.add_argument('--safe-areas', action='store_true', help='draw the safe area of the canvas on each picture')
    parser.add_argument('--list', action='store_true', help='list the formats and the canvases, and render nothing')
    args = parser.parse_args(argv)
    layout = project.load()
    brand_path = layout.root / 'documentation/media/brand.toml'
    if not brand_path.is_file():
        raise SystemExit('No documentation/media/brand.toml. The project template has a set to start from.')
    brand = tomllib.loads(brand_path.read_text())
    todo = outputs(layout, brand, args.formats, args.canvas)
    if args.list:
        for name, table in brand.get('format', {}).items():
            print(f'{name}  {table.get("kind", "image")}  {" ".join(table.get("canvases", []))}')
        for name, canvas in canvases().items():
            print(f'canvas {name}  {canvas["width"]} x {canvas["height"]}  {canvas["use"]}')
        return
    if shutil.which('designbot') is None:
        raise SystemExit(f'`fgtools media` needs the `designbot` command, which is not on PATH. Install it:\n  {INSTALL}')
    if any(table.get('kind') == 'video' for _, table, _, _ in todo) and shutil.which('ffmpeg') is None:
        raise SystemExit('A video format needs the `ffmpeg` command, which is not on PATH.')
    facts = font_facts(layout)
    missing = missing_characters(brand, facts)
    if missing:
        print(f'Nothing rendered: the font has no glyph for {len(missing)} characters of the texts in brand.toml: '
              f'{" ".join(missing[:40])}\nDraw them, or change the texts.')
        return
    script = program(layout, brand)
    count = 0
    for name, table, canvas_name, canvas in todo:
        if table.get('needs_weight_axis') and facts[2] == facts[3]:
            print(f'{name}  {canvas_name}  not rendered: the font has one weight')
            continue
        count += 1
        files = render(layout, brand, script, name, table, canvas_name, canvas, facts, args.safe_areas)
        print(f'{name}  {canvas_name}  {files[0].relative_to(layout.root)}' + (f'  (+{len(files) - 1})' if len(files) > 1 else ''))
    index = write_index(layout, brand, facts[1])
    print(f'{count} outputs in output/media/. The review page is {index.relative_to(layout.root)}')


if __name__ == '__main__':
    main()
