"""Compare a shaped word in static font instances with one Runebender thickness scale."""
import hashlib
import json
from math import dist
import subprocess
import tempfile
from pathlib import Path

from fontTools.pens.svgPathPen import SVGPathPen
from fontTools.pens.transformPen import TransformPen
from fontTools.ttLib import TTFont
from PIL import Image, ImageDraw, ImageFont, ImageOps
import uharfbuzz as hb

from fgtools import measure_picture, project
from fgtools.check_design import runebender
from fgtools.render_glyphs import BACKGROUND, INK, TEXT


def shaped_glyphs(path, word, units):
    """Yield the local outline and shaped origin of each ink-bearing glyph, in common units."""
    with TTFont(path) as font:
        if 'fvar' in font:
            raise ValueError(f'{path}: supply a static instance so the axes are explicit')
        face = hb.Face(path.read_bytes())
        scale = units / face.upem
        glyphs = font.getGlyphSet()
        buf = hb.Buffer()
        buf.add_str(word)
        buf.guess_segment_properties()
        hb.shape(hb.Font(face), buf)
        outlines = {}
        x = y = 0
        for info, pos in zip(buf.glyph_infos, buf.glyph_positions):
            gid = info.codepoint
            if gid == 0:
                raise ValueError(f'{path}: missing glyph in {word!r}')
            if gid not in outlines:
                pen = SVGPathPen(glyphs)
                glyphs[font.getGlyphName(gid)].draw(TransformPen(pen, (scale, 0, 0, scale, 0, 0)))
                outlines[gid] = pen.getCommands()
            if outlines[gid]:
                yield font.getGlyphName(gid), outlines[gid], (x + pos.x_offset) * scale, (y + pos.y_offset) * scale
            x += pos.x_advance
            y += pos.y_advance


def shaped_outlines(path, word, units):
    for _, commands, x, y in shaped_glyphs(path, word, units):
        yield commands, x, y


def draw_edge_profiles(path, word, units, pixels, image, left, top, tracks):
    from fgtools.edge_profiles import edge_profile

    reports = {}
    draw = ImageDraw.Draw(image)
    for glyph, commands, x, y in shaped_glyphs(path, word, units):
        for name, *coords in tracks:
            if name != glyph:
                continue
            key = (name, *coords)
            if key not in reports:
                coords = list(map(float, coords))
                reports[key] = dict(edge_profile(commands, coords[:2], coords[2:], units), glyph=name)
            valid = [s for s in reports[key]['samples'] if s['status'] == 'paired']
            if not valid:
                continue
            # Avoid stacking several marks on a short crossbar at proof size.
            span = dist(valid[0]['point'], valid[-1]['point']) * pixels
            markers = [len(valid) // 2] if span < 16 else [0, len(valid) // 2, len(valid) - 1]
            for n in sorted(set(markers)):
                ends = [((x + a) * pixels - left, top - (y + b) * pixels)
                        for a, b in valid[n]['contacts']]
                draw.line(ends, fill=(42, 64, 68, 255), width=3)
                draw.line(ends, fill=(200, 255, 250, 255), width=1)
    missing = {tuple(track) for track in tracks} - reports.keys()
    if missing:
        raise ValueError(f'Edge track glyphs missing from shaped word: {sorted({t[0] for t in missing})}')
    return list(reports.values())


def word_field(path, word, units, reference, pixels, binary, temp):
    """Measure each distinct glyph at its own origin, just as the editor does."""
    outline, png = (Path(temp) / name for name in ('outline.path', 'field.png'))
    measured = {}
    placements = []
    for commands, x, y in shaped_outlines(path, word, units):
        if commands not in measured:
            outline.write_text(commands)
            call = subprocess.run([binary, '--json', 'thickness', str(outline), '--reference',
                                   str(reference), '--units-per-em', str(units), '--out', str(png)],
                                  capture_output=True, text=True)
            if call.returncode:
                raise ValueError(f'Runebender thickness failed: {call.stdout or call.stderr}')
            data = json.loads(call.stdout)
            with Image.open(png) as raw:
                scale = pixels * data['cell']
                size = tuple(max(1, round(n * scale)) for n in raw.size)
                measured[commands] = raw.resize(size, Image.Resampling.LANCZOS), data['origin']
        field, (ox, oy) = measured[commands]
        placements.append((field, round((x + ox) * pixels), round(-(y + oy) * pixels)))
    if not placements:
        raise ValueError('Word contains no ink')
    left = min(x for _, x, _ in placements)
    upper = min(y for _, _, y in placements)
    right = max(x + im.width for im, x, _ in placements)
    lower = max(y + im.height for im, _, y in placements)
    image = Image.new('RGBA', (right - left, lower - upper))
    for field, x, y in placements:
        image.alpha_composite(field, (x - left, y - upper))
    return image, left, -upper


def word_proof(paths, word, reference, picture, out, edge_tracks=()):
    """Stack identical word settings. A screenshot uses the leading flat capital for registration."""
    binary = runebender()
    with TTFont(paths[0]) as first:
        units = first['head'].unitsPerEm
        cap = getattr(first['OS/2'], 'sCapHeight', None)
    pixels = 144 / units
    rows = []
    measurements = []
    with tempfile.TemporaryDirectory(prefix='fgtools-thickness-') as temp:
        for path in paths:
            field, x, top = word_field(path, word, units, reference, pixels, binary, temp)
            if edge_tracks:
                profiles = draw_edge_profiles(path, word, units, pixels, field, x, top, edge_tracks)
                measurements.append({'font': path.name, 'sha256': hashlib.sha256(path.read_bytes()).hexdigest(),
                                     'profiles': profiles})
            # Set the comparison in the font's normal rasterizer. Register the
            # heatmap separately using its design-space origin and baseline.
            size = 144
            face = ImageFont.truetype(path, size)
            bounds = face.getbbox(word, anchor='ls')
            l = min(x, bounds[0])
            t = min(-top, bounds[1])
            right = max(x + field.width, bounds[2])
            bottom = max(field.height - top, bounds[3])
            mono = Image.new('RGBA', (right - l, bottom - t))
            ImageDraw.Draw(mono).text((-l, -t), word, font=face, anchor='ls', fill=INK)
            registered = Image.new('RGBA', mono.size)
            registered.paste(field, (x - l, -top - t))
            field, x, top = registered, l, -t
            rows.append((path.stem, mono, field, x, top))
    if picture:
        if not cap or not word or word[0] not in 'EFHIKLMNTVWXYZ':
            raise ValueError('Screenshot alignment requires a known cap height and an initial flat baseline capital')
        shapes = measure_picture.glyphs(measure_picture.ink(picture))
        if len(shapes) != len(word.replace(' ', '')):
            raise ValueError('Reference picture must show the same line, with separated glyphs')
        lead = shapes[0]
        scale = cap * pixels / (lead['bottom'] - lead['top'])
        with Image.open(picture) as src:
            gray = src.convert('L')
        mask = ImageOps.invert(gray) if gray.getpixel((0, 0)) > 127 else gray
        box = mask.getbbox()
        mask = mask.crop(box)
        mask = mask.resize(tuple(max(1, round(size * scale)) for size in mask.size), Image.Resampling.LANCZOS)
        sample = Image.new('RGBA', mask.size, INK)
        sample.putalpha(mask)
        # Register the first visible edge and its baseline with the first font.
        first_ink = rows[0][1].getbbox()[0] + rows[0][3]
        rows.append(('Supplied reference · matched cap height', sample, None, first_ink,
                     round((lead['bottom'] - box[1]) * scale)))
    margin = 24
    left = min(0, min(x for _, _, _, x, _ in rows))
    right = max(x + mono.width for _, mono, _, x, _ in rows)
    top = max(row[4] for row in rows)
    bottom = max(mono.height - above for _, mono, _, _, above in rows)
    band = top + bottom + 12
    height = 2 * margin + sum(36 + band * (2 if heat else 1) for _, _, heat, _, _ in rows)
    image = Image.new('RGB', (right - left + 2 * margin, height), BACKGROUND)
    draw = ImageDraw.Draw(image)
    label = ImageFont.load_default(18)
    y = margin
    for name, mono, heat, x, above in rows:
        caption = f'{name}   ·   Thickness scale {reference:g} units ±20%' if heat else name
        draw.text((margin, y), caption, font=label, fill=TEXT)
        y += 32
        for sample in (mono, heat) if heat else (mono,):
            image.paste(sample, (margin + x - left, y + top - above), sample)
            y += band
        y += 4
    out.parent.mkdir(parents=True, exist_ok=True)
    image.save(out)
    if measurements:
        out.with_suffix('.json').write_text(json.dumps({'word': word, 'units_per_em': units,
            'thickness_reference': reference, 'fonts': measurements}, indent=2) + '\n')
    project.show(out)
