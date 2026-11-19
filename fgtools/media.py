"""Render the specimens and the marketing media of a font project.

Every picture is laid out on the lattice of the typeface (see
`fgtools/media_layout.py` and the `[layout]` block of CONTEXT.md): the module
is the large step of the design grid, type sizes double, and a text is chosen
so that it fills its measure. A format is a short Python function that places
type on the lattice. The command checks each drawing against the rules of the
layout, and DesignBot draws it.

Every project gets the default formats, which are in fgtools
(`fgtools/media_formats/`): big words, the weight ladder, text, the scripts,
the release picture, the link card, a glyph on its grid, the characters and
a loop of the weight axis. A project changes them in `documentation/media/`:

    brand.toml       the colors and the texts of the font
    formats.toml     optional: other canvases, the caption and the alternative text of a format,
                     and the tables of formats that only this font has
    images/          optional: a script (`.py`) with the name of a default format replaces it;
    carousels/       a script with a new name is a new format. The folder says what a format
    videos/          makes.

The canvases (the sizes and the safe areas of the platforms) are the same for
every font and are in `fgtools/media_canvases.toml`.

    fgtools media                       every format on each of its canvases
    fgtools media weight-axis           one format
    fgtools media --canvas vertical     one canvas
    fgtools media --lattice             draw the lattice and the text area on each picture
    fgtools media --specimen            the print specimen: the formats on A4 pages, as one PDF
    fgtools media --list                list the formats and the canvases
    fgtools media --copy weight-axis    copy a default script into the project, to change it

One output is one format on one canvas:
`output/media/<folder>/<format>/<family>_<format>_<canvas>.<extension>`. An
image is a PNG, a carousel is numbered PNG pages and one PDF (the document
post of LinkedIn), and a video is an MP4. Beside each output is a JSON record
with the caption, the alternative text, the size and the commit of the sources.
`output/media/index.html` is a review page that shows every output. The print
specimen is `output/specimen/<family>-specimen.pdf`.

A drawing with a fault is not written: a size that is not on the scale, a
position that is not on the unit, or ink outside the text area. A font at the
start of its design has few glyphs, and the formats use what it has: a text
with a character that the font does not have is left out, and a picture never
shows a system font.

It needs DesignBot, which `fgtools install-tools` compiles from a pinned
commit, and `ffmpeg` for video.
"""
from __future__ import annotations

import argparse
import importlib.util
import json
import re
import shutil
import subprocess
import sys
import tomllib
from pathlib import Path
from types import SimpleNamespace

from fgtools import media_layout, project

HERE = Path(__file__).parent
CANVASES, WORDS, PLOTTER = HERE / 'media_canvases.toml', HERE / 'media_words.toml', HERE / 'media_plotter.rs'
DEFAULTS = HERE / 'media_formats'
FOLDERS = {'images': 'image', 'carousels': 'carousel', 'videos': 'video'}     # folder: kind
EXTENSION = {'image': 'png', 'carousel': 'png', 'video': 'mp4'}
MEDIA = 'documentation/media'
# The pages of the print proof, in their order: scripts of media_formats/proofs/, and two formats.
PROOF = ['release', 'character-set', 'sizes', 'reading', 'spacing', 'kerning', 'diacritics', 'weights',
         'interpolation', 'grade', 'lines', 'arabic-joining', 'arabic-marks']
SPECIMEN = ['release', 'text', 'words', 'weights', 'scripts', 'glyph', 'characters']     # the pages, in order
PREFERRED_GLYPHS = 'aGRg&?nHOoesE25'
SCRIPTS = {'Latin': (0x41, 0x7A), 'Arabic': (0x627, 0x64A), 'Hebrew': (0x5D0, 0x5EA), 'Greek': (0x391, 0x3C9),
           'Cyrillic': (0x410, 0x44F)}
INSTALL = 'make setup, which runs `fgtools install-tools`'


def designbot():
    """The DesignBot that `fgtools install-tools` put next to this Python, or else the one on PATH."""
    from fgtools.build_source_snapshot import tool_path
    return shutil.which('designbot', path=tool_path())


def slug(text):
    return ''.join(c.lower() if c.isalnum() else '-' for c in text).strip('-')


def canvases():
    return tomllib.loads(CANVASES.read_text())['canvas']


def commit(root):
    result = subprocess.run(['git', 'rev-parse', '--short', 'HEAD'], cwd=root, capture_output=True, text=True)
    return result.stdout.strip() or None


def find_script(folder, name):
    """(kind folder, path) of the script of a format in a media folder, or None."""
    found = [(kind_folder, folder / kind_folder / f'{name}.py') for kind_folder in FOLDERS
             if (folder / kind_folder / f'{name}.py').is_file()]
    if len(found) > 1:
        raise SystemExit(f'{name}.py is in two folders of {folder}. Keep one.')
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
            raise SystemExit(f'formats.toml names the format `{name}`. Its script {name}.py must be in one of {places}.')
        table['folder'], table['script'] = found
        table['kind'] = FOLDERS[found[0]]
        table['own'] = folder in found[1].parents
    scripts = {path.stem for kind_folder in FOLDERS for path in (folder / kind_folder).glob('*.py')}
    for name in sorted(scripts - set(formats)):
        print(f'{name}.py has no table in formats.toml and is not rendered.', file=sys.stderr)
    brand['format'] = formats
    return brand


def font_type(layout):
    """(Type, facts) of the built font of the project: the font to measure and draw with, and the
    facts that the pictures state."""
    from fontTools.ttLib import TTFont
    variable = sorted((layout.fonts / 'variable').glob('*.ttf'))
    static = sorted((layout.fonts / 'ttf').glob('*.ttf'))
    if not variable and not static:
        raise SystemExit('No built fonts. Run `make build` first.')
    path = (variable or static)[0]
    with TTFont(path, lazy=True) as font:
        upm, os2 = font['head'].unitsPerEm, font['OS/2']
        low = high = float(os2.usWeightClass)
        instances = []
        if 'fvar' in font:
            for axis in font['fvar'].axes:
                if axis.axisTag == 'wght':
                    low, high = axis.minValue, axis.maxValue
            instances = sorted({instance.coordinates.get('wght') for instance in font['fvar'].instances} - {None})
        characters = set(font.getBestCmap())
        facts = {'version': f'{font["head"].fontRevision:.3f}', 'glyphs': font['maxp'].numGlyphs,
                 'characters': len(characters), 'instances': instances or [low, high],
                 'scripts': [name for name, (first, last) in SCRIPTS.items()
                             if first in characters and last in characters]}
        family = font['name'].getBestFamilyName()
        cap = getattr(os2, 'sCapHeight', 0) / upm or 0.7
        x_height = getattr(os2, 'sxHeight', 0) / upm or 0.5
        descender = font['hhea'].descent / upm
    return media_layout.Type(path, family, low, high, upm, cap, x_height, descender), facts


def description(layout):
    """The description of the font: the first paragraph of CONTEXT.md, as plain text."""
    path = layout.root / 'CONTEXT.md'
    if not path.is_file():
        return ''
    paragraphs = [part.strip() for part in path.read_text().split('\n\n')]
    first = next((part for part in paragraphs if part and not part.startswith(('#', '-', '|', '`'))), '')
    return re.sub(r'\s+', ' ', re.sub(r'[`*_]|\[([^\]]*)\]\([^)]*\)', r'\1', first))


def outlines(layout):
    """A function that gives the drawing of a character in the first master: its glyph name and
    its contours as [((x, y), type)], with None for a point off the curve."""
    from fgtools.accent_placement import Font
    try:
        source = Font.from_ufo(layout.ufo(layout.masters[0]))
    except Exception:           # a project without a readable master has no points to show
        return lambda character: None

    class Pen:
        def __init__(self):
            self.contours = []

        def beginPath(self, **_):
            self.contours.append([])

        def addPoint(self, point, segmentType=None, **_):
            self.contours[-1].append(((point[0], point[1]), segmentType))

        def endPath(self):
            pass

        def addComponent(self, *_, **__):
            pass

    def outline(character):
        name = source.names.get(ord(character))
        if not name or name not in source.glyph_set:
            return None
        pen = Pen()
        source.glyph_set[name].drawPoints(pen)
        return {'name': name, 'contours': [contour for contour in pen.contours if contour]}
    return outline


def make_job(layout, brand, type_, facts):
    """What a format gets beside its sheet: the font, the brand and the texts."""
    text = brand.get('text', {})
    words = tomllib.loads(WORDS.read_text())
    words['Latin'] = [word for word in text.get('words', [])] + words['Latin']
    for script, lines in (('Arabic', text.get('arabic', [])), ('Hebrew', text.get('hebrew', []))):
        words[script] = list(lines) + words[script]
    if sum(type_.covers(word) for word in words['Latin']) < 3:
        # A font with few glyphs: the letters that exist are the words.
        letters = [chr(code) for code in sorted(type_.characters) if chr(code).isalpha()]
        capitals, small = [c for c in letters if c.isupper()], [c for c in letters if c.islower()]
        words['Latin'] += [''.join(group[start:start + size]) for group in (capitals, small)
                           for size in (2, 3, 4, 6) for start in range(0, len(group), size)]
    type_.avoid = set(''.join(text.get('avoid', [])))
    glyphs = [g for g in text.get('glyphs', []) if type_.covers(g)] or \
        [g for g in PREFERRED_GLYPHS if type_.covers(g)][:6]
    shown = lambda value: value if type_.covers(value.replace(' ', '') or '.') else ''
    from fgtools.proof_web import samples as proof_samples
    samples, _ = proof_samples.read(layout.sources)
    texts = {}
    for script in proof_samples.ALPHABETS:
        sample = ' '.join(paragraph.get('text', '') for paragraph in
                        samples.get('text', {}).get(script.lower(), {}).get('paragraphs', []))
        if sample and type_.covers(sample.replace(' ', '')):
            texts[script] = sample
    stamp = shown(' '.join(part for part in (f'Version {facts["version"]}', commit(layout.root)) if part))
    return SimpleNamespace(type=type_, brand=brand, facts=facts, family=type_.family, words=words, glyphs=glyphs,
                           samples=samples, texts=texts, stamp=stamp,
                           description=description(layout), outline=outlines(layout),
                           url=shown(text.get('url', '')), designer=shown(text.get('designer', '')))


def project_layout(layout):
    """The `[layout]` block of CONTEXT.md of the project, or nothing: the defaults apply."""
    try:
        return layout.design().get('layout') or {}
    except Exception:
        return {}


def brand_colors(brand):
    colors = {}
    for name, value in brand.get('colors', {}).items():
        value = value.lstrip('#')
        colors[name] = tuple(int(value[i:i + 2], 16) for i in (0, 2, 4))
    return colors


def compose(table, job, canvas, units, colors, name, show_lattice=False):
    """(sheet, reason): the drawing of a format on a canvas, or the reason that it cannot be drawn."""
    grid = media_layout.lattice(canvas, units)
    sheet = media_layout.Sheet(grid, job.type, colors, name)
    spec = importlib.util.spec_from_file_location(f'fgtools_media_{name.replace("-", "_")}', table['script'])
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    reason = module.draw(sheet, job)
    if reason or not sheet.pages:
        return None, reason or 'the format drew nothing'
    sheet.check()
    if show_lattice:
        (ox, oy), (cols, rows), module_size = grid['origin'], grid['live'], grid['module']
        for page in sheet.pages:
            sheet.pages, kept = [page], sheet.pages
            for k in range(cols + 1):
                sheet.line(ox + k * module_size, oy, ox + k * module_size, oy + rows * module_size, 'grid', 1)
            for k in range(rows + 1):
                sheet.line(ox, oy + k * module_size, ox + cols * module_size, oy + k * module_size, 'grid', 1)
            for x in (sheet.x(0), sheet.x(sheet.cols)):
                sheet.line(x, sheet.y(0), x, sheet.y(sheet.rows), 'accent', 1)
            for y in (sheet.y(0), sheet.y(sheet.rows)):
                sheet.line(sheet.x(0), y, sheet.x(sheet.cols), y, 'accent', 1)
            sheet.pages = kept
    return sheet, None


def run_plotter(layout, sheets, output):
    """Write the plot file of the sheets and let DesignBot draw it."""
    build = layout.root / 'output/media/.build'
    build.mkdir(parents=True, exist_ok=True)
    plotter = build / 'plotter.rs'
    if not plotter.is_file() or plotter.read_text() != PLOTTER.read_text():   # compiled once for each project
        plotter.write_text(PLOTTER.read_text())
    plot_file = build / f'{output.stem}.{output.suffix[1:]}.plot'
    media_layout.plot(sheets, output, plot_file)
    result = subprocess.run([designbot(), str(plotter), '--output', str(output), '--', f'plot={plot_file}'],
                            cwd=layout.root, capture_output=True, text=True)
    return result


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


def render(layout, name, table, canvas_name, canvas, sheet, family, suffix=''):
    """Write one drawing. Returns the list of the files written."""
    kind = table['kind']
    folder = layout.root / 'output/media' / table['folder'] / name
    folder.mkdir(parents=True, exist_ok=True)
    stem = f'{slug(family)}_{name}_{canvas_name}{suffix}'
    written = []
    for extension in [EXTENSION[kind]] + (['pdf'] if kind == 'carousel' else []):
        output = folder / f'{stem}.{extension}'
        output.unlink(missing_ok=True)
        for old in folder.glob(f'{stem}_[0-9][0-9][0-9][0-9].{extension}'):
            old.unlink()
        result = run_plotter(layout, [sheet], output)
        files = [output] if output.is_file() else sorted(folder.glob(f'{stem}_[0-9][0-9][0-9][0-9].{extension}'))
        if result.returncode or not files:
            sys.stderr.write(result.stdout[-2000:] + result.stderr[-4000:])
            raise SystemExit(f'{name} on {canvas_name}: DesignBot did not write {output.name}.')
        if extension == 'mp4':
            add_silence(output)
        written += files
    record = {'format': name, 'kind': kind, 'canvas': canvas_name, 'width': canvas['width'],
              'height': canvas['height'], 'family': family, 'commit': commit(layout.root),
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
  body {{ margin: 0; padding: 32px; background: #181818; color: #c8c8c8; font: 15px/1.5 system-ui, sans-serif; }}
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
format on one canvas, laid out on the lattice of the typeface.</p>
<table><tr><th>Canvas</th><th>Size</th><th>Live area, modules</th><th>Text area, modules</th><th>Use</th></tr>
{canvas_rows}</table>
{sections}
</html>
"""


def write_index(layout, brand, family, units):
    """Write output/media/index.html: a sheet of every rendered output, for review in a browser."""
    from html import escape
    root = layout.root / 'output/media'
    rows = []
    for name, canvas in canvases().items():
        grid = media_layout.lattice(canvas, units)
        rows.append(f'<tr><td>{escape(name)}</td><td>{canvas["width"]} x {canvas["height"]}</td>'
                    f'<td>{grid["live"][0]} x {grid["live"][1]}</td><td>{grid["text"][2]} x {grid["text"][3]}</td>'
                    f'<td>{escape(canvas["use"])}</td></tr>\n')
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
                       canvas_rows=''.join(rows), sections='\n'.join(sections))
    (root / 'index.html').write_text(page)
    return root / 'index.html'


def outputs(brand, names=None, only_canvas=None):
    """[(format name, format table, canvas name, canvas table)] to render."""
    known, formats = canvases(), brand.get('format', {})
    # A name is a format, or a folder: `images`, `carousels` or `videos` is every format of that kind.
    names = [name for given in names or []
             for name in ([key for key, table in formats.items() if table['folder'] == given] or [given])]
    for name in names:
        if name not in formats:
            raise SystemExit(f'No format `{name}`. Formats: {", ".join(formats) or "none"}. '
                             f'Kinds: {", ".join(FOLDERS)}.')
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


def pages(all_pages, names):
    """The pages of a book to write: all of them, or the named ones in the order of the book."""
    unknown = [name for name in names if name not in all_pages]
    if unknown:
        raise SystemExit(f'No page `{unknown[0]}`. Pages: {", ".join(all_pages)}.')
    return [name for name in all_pages if name in names] if names else all_pages


def book(layout, brand, job, units, colors, names, title, output):
    """Write formats on the page canvas as one PDF: the print specimen or the print proof."""
    canvas = canvases()['page']
    sheets, faults = [], []
    for name in names:
        script = DEFAULTS / 'proofs' / f'{name}.py'
        table = {'script': script} if script.is_file() else brand['format'].get(name)
        if not table:
            continue
        sheet, reason = compose(table, job, canvas, units, colors, name)
        if sheet is None:
            print(f'{name}  not in the {title}: {reason}')
            continue
        faults += sheet.faults
        sheets.append(sheet)
    if faults:
        raise SystemExit(f'The {title} has faults and is not written:\n  ' + '\n  '.join(faults))
    if not sheets:
        raise SystemExit('No format can be drawn yet.')
    output = layout.root / output
    output.parent.mkdir(parents=True, exist_ok=True)
    result = run_plotter(layout, sheets, output)
    if result.returncode or not output.is_file():
        sys.stderr.write(result.stdout[-2000:] + result.stderr[-4000:])
        raise SystemExit(f'DesignBot did not write the {title}.')
    print(f'{output.relative_to(layout.root)}  {sum(len(sheet.pages) for sheet in sheets)} pages')
    project.show(output)


def main(argv=None):
    parser = argparse.ArgumentParser(prog='fgtools media', description=__doc__.split('\n')[0])
    parser.add_argument('formats', nargs='*', help='names of formats, or `images`, `carousels` or `videos` for each '
                        'format of that kind; with --proof or --specimen, names of pages. The default is all.')
    parser.add_argument('--canvas', help='one canvas; the default is each canvas of the format')
    parser.add_argument('--lattice', action='store_true', help='draw the lattice and the text area on each picture')
    parser.add_argument('--specimen', action='store_true', help='write the print specimen, one PDF of A4 pages')
    parser.add_argument('--proof', action='store_true', help='write the print proof, one PDF of A4 pages')
    parser.add_argument('--list', action='store_true', help='list the formats and the canvases, and render nothing')
    parser.add_argument('--copy', metavar='FORMAT', help='copy the default script of a format into the project')
    args = parser.parse_args(argv)
    layout = project.load()
    brand = load_brand(layout)
    if args.copy:
        table = brand['format'].get(args.copy)
        if not table:
            raise SystemExit(f'No format `{args.copy}`. Formats: {", ".join(brand["format"])}.')
        target = layout.root / MEDIA / table['folder'] / f'{args.copy}.py'
        if target.is_file():
            raise SystemExit(f'{target.relative_to(layout.root)} exists already.')
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy(table['script'], target)
        print(f'{target.relative_to(layout.root)}: change it, and `fgtools media {args.copy}` renders your version.')
        return
    todo = [] if args.proof or args.specimen else outputs(brand, args.formats, args.canvas)
    units = project_layout(layout)
    if args.list:
        for name, table in brand.get('format', {}).items():
            origin = 'script of this project' if table['own'] else 'default script'
            print(f'{name}  {table["kind"]}  {" ".join(table.get("canvases", []))}  ({origin})')
        print(f'pages of the proof  {" ".join(PROOF)}')
        print(f'pages of the specimen  {" ".join(SPECIMEN)}')
        for name, canvas in canvases().items():
            grid = media_layout.lattice(canvas, units)
            print(f'canvas {name}  {canvas["width"]} x {canvas["height"]}  text area {grid["text"][2]} x '
                  f'{grid["text"][3]} modules  {canvas["use"]}')
        return
    if designbot() is None:
        raise SystemExit(f'`fgtools media` needs DesignBot, which is not installed. Install it with {INSTALL}.')
    if any(table['kind'] == 'video' for _, table, _, _ in todo) and shutil.which('ffmpeg') is None:
        raise SystemExit('A video format needs the `ffmpeg` command, which is not on PATH.')
    type_, facts = font_type(layout)
    if not any(chr(code).isalnum() for code in type_.characters):
        print('Nothing rendered: the font has no letter and no figure yet.')
        return
    job = make_job(layout, brand, type_, facts)
    colors = brand_colors(brand)
    if args.specimen:
        book(layout, brand, job, units, colors, pages(SPECIMEN, args.formats), 'specimen',
             f'output/specimen/{slug(job.family)}-specimen.pdf')
        return
    if args.proof:
        book(layout, brand, job, units, colors, pages(PROOF, args.formats), 'proof', 'output/proof/proof.pdf')
        return
    count, faults = 0, []
    for name, table, canvas_name, canvas in todo:
        sheet, reason = compose(table, job, canvas, units, colors, name, args.lattice)
        if sheet is None:
            print(f'{name}  {canvas_name}  not rendered: {reason}')
            continue
        if sheet.faults:
            faults += [f'{canvas_name}: {fault}' for fault in sheet.faults]
            print(f'{name}  {canvas_name}  not written: {len(sheet.faults)} faults')
            continue
        count += 1
        files = render(layout, name, table, canvas_name, canvas, sheet, type_.family, '_lattice' if args.lattice else '')
        print(f'{name}  {canvas_name}  {files[0].relative_to(layout.root)}' + (f'  (+{len(files) - 1})' if len(files) > 1 else ''))
    index = write_index(layout, brand, type_.family, units)
    print(f'{count} outputs in output/media/.')
    project.show(index)
    if faults:
        raise SystemExit('Faults of the layout:\n  ' + '\n  '.join(faults))


if __name__ == '__main__':
    main()
