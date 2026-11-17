"""Render the marketing media of a font project with DesignBot.

Every project gets the default formats, which are in fgtools
(`fgtools/media_formats/`): a specimen poster, a release picture, a link card,
a glyph on the grid, the character set, the scripts of the font and an
animation of the weight axis. A project changes them in `documentation/media/`:

    brand.toml       the colors and the texts of the font
    formats.toml     optional: other canvases or words, the caption and the alternative text of a
                     format, and the tables of formats that only this font has
    images/          optional: a DesignBot script (`.rs`) with the name of a default format
    carousels/       replaces it; a script with a new name is a new format. The folder says
    videos/          what a format makes.

A format is one kind of picture. The canvases (the sizes and the safe areas of
the platforms) are the same for every font and are in
`fgtools/media_canvases.toml`.

    fgtools media                       every format on each of its canvases
    fgtools media weight-axis           one format
    fgtools media --canvas vertical     one canvas
    fgtools media --safe-areas          draw the safe area on each picture
    fgtools media --list                list the formats and the canvases
    fgtools media --copy weight-axis    copy a default script into the project, to change it

The command gives each script a module `brief` with the canvas, the safe area,
the family name, the font file, the weight range, the metrics, the colors and
the texts, so that a script holds only the layout. One output is one format on
one canvas: `output/media/<folder>/<format>/<family>_<format>_<canvas>.<extension>`.
An image is a PNG, a carousel is numbered PNG pages and one PDF (the document
post of LinkedIn), and a video is an MP4. Beside each output is a JSON record
with the caption, the alternative text, the size and the commit of the sources.
`output/media/index.html` is a review page that shows every output.

A font at the start of its design has few glyphs. The media use what it has:
a text with a character that the font does not have is left out, and when no
word of brand.toml can be set, the pictures show the letters that exist.
DesignBot would draw a missing glyph with a system font, and a picture must
never show another font.

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
FOLDERS = {'images': 'image', 'carousels': 'carousel', 'videos': 'video'}     # folder: kind
MEDIA = 'documentation/media'
DEFAULTS = Path(__file__).with_name('media_formats')
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


def commit(root):
    result = subprocess.run(['git', 'rev-parse', '--short', 'HEAD'], cwd=root, capture_output=True, text=True)
    return result.stdout.strip() or None


def find_script(folder, name):
    """(kind folder, path) of the script of a format in a media folder, or None."""
    found = [(kind_folder, folder / kind_folder / f'{name}.rs') for kind_folder in FOLDERS
             if (folder / kind_folder / f'{name}.rs').is_file()]
    if len(found) > 1:
        raise SystemExit(f'{name}.rs is in two folders of {folder}. Keep one.')
    return found[0] if found else None


def load_brand(layout):
    """brand.toml with a table `format`: the default formats of fgtools, changed and extended by
    formats.toml and the scripts of the project. Each format has its kind and its script."""
    folder = layout.root / MEDIA
    brand = tomllib.loads((folder / 'brand.toml').read_text()) if (folder / 'brand.toml').is_file() else {}
    formats = tomllib.loads((DEFAULTS / 'formats.toml').read_text())
    own = tomllib.loads((folder / 'formats.toml').read_text()) if (folder / 'formats.toml').is_file() else {}
    for name, table in own.items():
        formats.setdefault(name, {}).update(table)
    for name, table in formats.items():
        found = find_script(folder, name) or find_script(DEFAULTS, name)
        if not found:
            places = ', '.join(f'{MEDIA}/{kind_folder}/' for kind_folder in FOLDERS)
            raise SystemExit(f'formats.toml names the format `{name}`. Its script {name}.rs must be in one of {places}.')
        table['folder'], table['script'] = found
        table['kind'] = FOLDERS[found[0]]
        table['own'] = folder in found[1].parents
    scripts = {path.stem for kind_folder in FOLDERS for path in (folder / kind_folder).glob('*.rs')}
    for name in sorted(scripts - set(formats)):
        print(f'{name}.rs has no table in formats.toml and is not rendered.', file=sys.stderr)
    brand['format'] = formats
    return brand


PREFERRED_GLYPHS = 'aGRg&?nHOoesE25'


def character_map(facts):
    """The code points that the font has a glyph for."""
    from fontTools.ttLib import TTFont
    with TTFont(facts[0], lazy=True) as font:
        return set(font.getBestCmap())


def texts(brand, table, facts):
    """The texts that a format draws, limited to what the font can set. A project names them in
    formats.toml as a list, or the table names a list of brand.toml: words, glyphs or lines."""
    covered = character_map(facts)
    can_set = lambda text: bool(text.strip()) and all(ord(character) in covered for character in text)
    text, source = brand.get('text', {}), table.get('words', 'words')
    letters = [chr(code) for code in sorted(covered) if chr(code).isalnum()]
    if isinstance(source, list):
        chosen = [item for item in source if can_set(item)]
        source = 'words' if all(len(item) > 1 for item in source) else 'glyphs'
    else:
        chosen = [item for item in text.get(source, []) if can_set(item)]
    if chosen:
        return chosen
    if source == 'glyphs':
        return [c for c in PREFERRED_GLYPHS if can_set(c)][:6] or letters[:6]
    if source == 'lines' and can_set(facts[1]):
        return [facts[1]]
    words = [word for word in text.get('words', []) + facts[1].split() if can_set(word)]
    # No word can be set: show the letters that exist, capitals first.
    capitals = ''.join(c for c in letters if c.isupper())[:6]
    small = ''.join(c for c in letters if c.islower())[:6]
    return words[:3] or [group for group in (capitals, small) if group] or [''.join(letters[:6])]


def charset(facts):
    """The characters of the font as ranges of hexadecimal code points, for the brief."""
    codes, ranges = sorted(character_map(facts)), []
    for code in codes:
        if ranges and code == ranges[-1][1] + 1:
            ranges[-1][1] = code
        else:
            ranges.append([code, code])
    return ','.join(f'{low:x}-{high:x}' for low, high in ranges)


def outputs(layout, brand, names=None, only_canvas=None):
    """[(format name, format table, canvas name, canvas table)] to render."""
    known, formats = canvases(), brand.get('format', {})
    for name in names or []:
        if name not in formats:
            raise SystemExit(f'No format `{name}` in formats.toml. Formats: {", ".join(formats) or "none"}.')
    found = []
    for name, table in formats.items():
        if names and name not in names:
            continue
        for canvas in table.get('canvases', []):
            if canvas not in known:
                raise SystemExit(f'Format `{name}`: no canvas `{canvas}`. Canvases: {", ".join(known)}.')
            if only_canvas in (None, canvas):
                found.append((name, table, canvas, known[canvas]))
    return found


def arguments(brand, table, canvas, facts, output, safe_areas, characters=''):
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
        'words': '|'.join(texts(brand, table, facts)), 'charset': characters or charset(facts),
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
        source = brand['format'][name]['script'].read_text()
        if 'fn main()' not in source:
            raise SystemExit(f'{name}.rs has no `fn main()`.')
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
    kind = table['kind']
    folder = layout.root / 'output/media' / table['folder'] / name
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
format on one canvas. The brand, the formats and their scripts are in <code>documentation/media/</code>; the canvases are
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
        records = [json.loads(path.read_text()) for path in sorted((root / table['folder'] / name).glob('*.json'))]
        figures = []
        for record in records:
            label = f'{record["canvas"]}, {record["width"]} x {record["height"]}'
            for file in record['files']:
                source = f'{table["folder"]}/{name}/{file}'
                if file.endswith('.mp4'):
                    media = f'<video src="{escape(source)}" autoplay loop muted playsinline></video>'
                elif file.endswith('.pdf'):
                    figures.append(f'<figure><figcaption><a style="color:#c8c8c8" href="{escape(source)}">'
                                   f'{escape(file)}</a> (the carousel as one PDF)</figcaption></figure>')
                    continue
                else:
                    media = f'<img src="{escape(source)}" alt="{escape(record["alt"])}" loading="lazy">'
                figures.append(f'<figure>{media}<figcaption>{escape(label)}<br>{escape(file)}</figcaption></figure>')
        text = lambda key: escape(table.get(key, '')) or f'<span class="missing">no {key} in formats.toml</span>'
        note = '' if records else '<p class="missing">Not rendered.</p>'
        sections.append(f'<h2>{escape(name)}</h2>\n<p>{escape(table["kind"])} on '
                        f'{escape(", ".join(table.get("canvases", [])))}.<br>Caption: {text("caption")}<br>'
                        f'Alternative text: {text("alt")}</p>{note}\n<div class="row">{"".join(figures)}</div>')
    page = PAGE.format(family=escape(family), commit=escape(commit(layout.root) or 'unknown'),
                       canvas_rows=canvas_rows, sections='\n'.join(sections))
    (root / 'index.html').write_text(page)
    return root / 'index.html'


def main(argv=None):
    parser = argparse.ArgumentParser(prog='fgtools media', description=__doc__.split('\n')[0])
    parser.add_argument('formats', nargs='*', help='format names; the default is every format of formats.toml')
    parser.add_argument('--canvas', help='one canvas; the default is each canvas of the format')
    parser.add_argument('--safe-areas', action='store_true', help='draw the safe area of the canvas on each picture')
    parser.add_argument('--list', action='store_true', help='list the formats and the canvases, and render nothing')
    parser.add_argument('--copy', metavar='FORMAT', help='copy the default script of a format into the project')
    args = parser.parse_args(argv)
    layout = project.load()
    brand = load_brand(layout)
    if args.copy:
        table = brand['format'].get(args.copy)
        if not table:
            raise SystemExit(f'No format `{args.copy}`. Formats: {", ".join(brand["format"])}.')
        target = layout.root / MEDIA / table['folder'] / f'{args.copy}.rs'
        if target.is_file():
            raise SystemExit(f'{target.relative_to(layout.root)} exists already.')
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy(table['script'], target)
        print(f'{target.relative_to(layout.root)}: change it, and `fgtools media {args.copy}` renders your version.')
        return
    todo = outputs(layout, brand, args.formats, args.canvas)
    if args.list:
        for name, table in brand.get('format', {}).items():
            origin = 'script of this project' if table['own'] else 'default script'
            print(f'{name}  {table["kind"]}  {" ".join(table.get("canvases", []))}  ({origin})')
        for name, canvas in canvases().items():
            print(f'canvas {name}  {canvas["width"]} x {canvas["height"]}  {canvas["use"]}')
        return
    if shutil.which('designbot') is None:
        raise SystemExit(f'`fgtools media` needs the `designbot` command, which is not on PATH. Install it:\n  {INSTALL}')
    if any(table['kind'] == 'video' for _, table, _, _ in todo) and shutil.which('ffmpeg') is None:
        raise SystemExit('A video format needs the `ffmpeg` command, which is not on PATH.')
    facts = font_facts(layout)
    covered = character_map(facts)
    if not any(chr(code).isalnum() for code in covered):
        print('Nothing rendered: the font has no letter and no figure yet.')
        return
    text = brand.get('text', {})
    for key in ('tagline', 'designer', 'url'):
        missing = sorted({c for c in text.get(key, '') if ord(c) not in covered})
        if missing:
            print(f'The {key} of brand.toml is left out: the font has no glyph for {" ".join(missing[:30])}')
    script = program(layout, brand)
    count = 0
    for name, table, canvas_name, canvas in todo:
        if table.get('needs_weight_axis') and facts[2] == facts[3]:
            print(f'{name}  {canvas_name}  not rendered: the font has one weight')
            continue
        if table.get('needs_family_name') and any(ord(c) not in covered for c in facts[1]):
            print(f'{name}  {canvas_name}  not rendered: the font cannot set its name, {facts[1]}, yet')
            continue
        count += 1
        files = render(layout, brand, script, name, table, canvas_name, canvas, facts, args.safe_areas)
        print(f'{name}  {canvas_name}  {files[0].relative_to(layout.root)}' + (f'  (+{len(files) - 1})' if len(files) > 1 else ''))
    index = write_index(layout, brand, facts[1])
    print(f'{count} outputs in output/media/. The review page is {index.relative_to(layout.root)}')


if __name__ == '__main__':
    main()
