"""The text samples of the web proof.

The default samples are in samples.toml next to this module. A project adds
samples, or replaces a default sample with the same key, in
sources/proof-samples.toml. With `defaults = false` in that file, the proof
uses only the samples of the project.

A sample or paragraph with `scripts` is used only when the font covers each
of those scripts: at least half of the letters in ALPHABETS. A sample
without `scripts` is always used.
"""
from __future__ import annotations

import tomllib
import unicodedata
from pathlib import Path

DEFAULTS = Path(__file__).with_name('samples.toml')
PROJECT_FILE = 'proof-samples.toml'

# Script: (letters that show coverage, language tag, direction).
ALPHABETS = {
    'Latin': ('ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz', 'en', 'ltr'),
    'Hebrew': ('אבגדהוזחטיכלמנסעפצקרשתךםןףץ', 'he', 'rtl'),
    'Arabic': ('ءابتثجحخدذرزسشصضطظعغفقكلمنهوي', 'ar', 'rtl'),
}
DIRECTIONS = {language: direction for _, language, direction in ALPHABETS.values()}


def covered_scripts(codepoints):
    """The scripts of ALPHABETS of which the font has at least half the letters."""
    codepoints = set(codepoints)
    return {script for script, (letters, _, _) in ALPHABETS.items()
            if 2 * sum(ord(letter) in codepoints for letter in letters) >= len(letters)}


def read(sources):
    """The samples of the package and of the project, merged by key."""
    merged = tomllib.loads(DEFAULTS.read_text())
    path = Path(sources) / PROJECT_FILE
    if path.is_file():
        try:
            own = tomllib.loads(path.read_text())
        except tomllib.TOMLDecodeError as error:
            raise ValueError(f'{path}: {error}') from error
        if own.get('defaults', True) is False:
            merged = {}
        for kind in ('sample', 'text'):
            merged.setdefault(kind, {}).update(own.get(kind, {}))
    return merged, path


def _scripts(entry, where):
    scripts = entry.get('scripts', [])
    unknown = [name for name in scripts if name not in ALPHABETS]
    if unknown:
        raise ValueError(f'{where}: unknown script {unknown[0]!r}. Known scripts: {", ".join(ALPHABETS)}')
    return scripts


def _language(entry, scripts):
    return entry.get('lang') or (ALPHABETS[scripts[0]][1] if scripts else '')


def select(codepoints, sources):
    """The samples for a font with these codepoints, in the form of the web app:
    `samples` (short lines) and `reading` (text samples by key)."""
    merged, path = read(sources)
    covered = covered_scripts(codepoints)
    lines = []
    for key, entry in merged.get('sample', {}).items():
        where = f'{path.name} sample.{key}'
        scripts = _scripts(entry, where)
        if 'label' not in entry or 'text' not in entry:
            raise ValueError(f'{where}: a sample needs `label` and `text`')
        if set(scripts) <= covered:
            lines.append(dict(key=key, label=entry['label'], text=entry['text'],
                              lang=_language(entry, scripts)))
    reading = {}
    for key, entry in merged.get('text', {}).items():
        where = f'{path.name} text.{key}'
        scripts = _scripts(entry, where)
        if 'label' not in entry or not entry.get('paragraphs'):
            raise ValueError(f'{where}: a text sample needs `label` and `paragraphs`')
        if not set(scripts) <= covered:
            continue
        paragraphs = []
        for index, paragraph in enumerate(entry['paragraphs']):
            own = _scripts(paragraph, f'{where} paragraph {index + 1}')
            if not set(own) <= covered:
                continue
            if 'runs' not in paragraph and 'text' not in paragraph:
                raise ValueError(f'{where} paragraph {index + 1}: needs `text` or `runs`')
            language = _language(paragraph, own or scripts)
            record = dict(lang=language, dir=paragraph.get('dir') or DIRECTIONS.get(language, 'auto'),
                          runs=paragraph.get('runs') or [dict(text=paragraph['text'])])
            if 'label' in paragraph:
                record['label'] = paragraph['label']
            paragraphs.append(record)
        if paragraphs:
            reading[key] = dict(label=entry['label'], overview=bool(entry.get('overview')),
                                paragraphs=paragraphs)
    reading['encoded-repertoire'] = dict(label='Encoded repertoire', overview=True,
                                         paragraphs=repertoire(codepoints))
    return dict(samples=lines, reading=reading)


def repertoire(codepoints):
    """Every printable encoded character of the font, by script, 24 to a line.
    Combining marks follow a dotted circle, so that they do not collide."""
    groups = {}
    for cp in sorted(codepoints):
        char = chr(cp)
        if unicodedata.category(char).startswith('C') or char.isspace():
            continue
        if 0x590 <= cp <= 0x5ff or 0xfb1d <= cp <= 0xfb4f:
            group = ('Hebrew', 'he', 'rtl')
        elif 0x600 <= cp <= 0x8ff or 0xfb50 <= cp <= 0xfdff or 0xfe70 <= cp <= 0xfeff:
            group = ('Arabic', 'ar', 'rtl')
        elif cp < 0x250 or 0x1e00 <= cp <= 0x1eff:
            group = ('Latin', 'en', 'ltr')
        else:
            group = ('Symbols and other encoded glyphs', 'en', 'ltr')
        groups.setdefault(group, []).append(cp)
    paragraphs = []
    for (name, language, direction), points in groups.items():
        for start in range(0, len(points), 24):
            chunk = points[start:start + 24]
            text = ' '.join(('◌' if unicodedata.category(chr(cp)).startswith('M') else '') + chr(cp)
                            for cp in chunk)
            paragraphs.append(dict(label=f'{name} · U+{chunk[0]:04X}–U+{chunk[-1]:04X}', lang=language,
                                   dir=direction, codepoints=chunk, runs=[dict(text=text)]))
    return paragraphs
