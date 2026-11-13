"""The fonts in the reference-fonts/ folder of a project.

The module reads font files only. It does not download fonts or change
sources. Each face is copied, under the name of its SHA-256 hash, into the
fonts/ folder of the proof that serves it.
"""
from __future__ import annotations

import hashlib
import io
import json
import math
import re
import time
from pathlib import Path

from fontTools.ttLib import TTFont

FOLDER = 'reference-fonts'
MAX_BYTES = 32 * 1024 * 1024
CACHE_GRACE_SECONDS = 300


def font_paths(folder):
    """The TTF and OTF files in `folder` and its subfolders, without hidden
    files and symbolic links."""
    paths = []

    def visit(directory):
        for path in sorted(directory.iterdir()):
            if path.name.startswith('.') or path.is_symlink():
                continue
            if path.is_dir():
                visit(path)
            elif path.suffix.lower() in ('.ttf', '.otf'):
                paths.append(path)

    if Path(folder).exists():
        visit(Path(folder))
    return sorted(paths)


def collect(folder, target):
    """The reference families, with the coverage of each face, and the errors.
    One family is one family name, width and slope. The faces are copied into
    `target`."""
    families, errors, seen = {}, [], set()
    try:
        paths = font_paths(folder)
    except OSError as error:
        return {'fonts': {}, 'errors': [str(error)]}
    for path in paths:
        try:
            if path.stat().st_size > MAX_BYTES:
                raise ValueError('font exceeds 32 MiB')
            raw = path.read_bytes()
            digest = hashlib.sha256(raw).hexdigest()
            if digest in seen:
                continue
            with TTFont(io.BytesIO(raw)) as font:
                names = font['name']
                family = names.getDebugName(16) or names.getDebugName(1)
                if not family:
                    raise ValueError('missing family name')
                os2 = font['OS/2']
                italic = bool(os2.fsSelection & (1 | 512))
                width = os2.usWidthClass
                label = family + (f' · Width {width}' if width != 5 else '') + (' Italic' if italic else '')
                key = (family.lower(), width, italic)
                axes = {a.axisTag: [a.minValue, a.defaultValue, a.maxValue] for a in font['fvar'].axes} if 'fvar' in font else {}
                weights = axes.get('wght', [os2.usWeightClass] * 3)
                if not all(math.isfinite(value) for value in weights) or weights[0] > weights[2]:
                    raise ValueError('invalid weight range')
                cmap = font.getBestCmap() or {}
                face = dict(sha256=digest, url=f'fonts/reference-{digest}{path.suffix.lower()}',
                            path=path.relative_to(folder).as_posix(), axes=axes,
                            minWeight=weights[0], maxWeight=weights[2], weight=str(os2.usWeightClass),
                            codepoints=sorted(cp for cp, glyph in cmap.items() if font.getGlyphID(glyph) != 0))
            destination = Path(target) / face['url']
            destination.parent.mkdir(parents=True, exist_ok=True)
            if not destination.exists() or hashlib.sha256(destination.read_bytes()).hexdigest() != digest:
                # Write the bytes that were hashed, not a second read of the file.
                destination.write_bytes(raw)
            record = families.setdefault(key, dict(family=label, sourceFamily=family, label=label,
                                                   reference=True, faces=[]))
            record['faces'].append(face)
            seen.add(digest)
        except Exception as error:
            errors.append(f'{path.relative_to(folder)}: {error}')
    fonts = {f'reference-{index}': families[key] for index, key in enumerate(sorted(families))}
    return dict(fonts=fonts, errors=errors)


def prune_reference_cache(target, stale_since, now):
    """Remove the reference copies in target/fonts that neither manifest uses,
    after a grace time of CACHE_GRACE_SECONDS.

    Both manifests keep their files: a new browser tab can load the startup
    data before its first reference poll. The function does not follow
    symbolic links and does not remove a file whose hash differs from its name.
    """
    target = Path(target)
    try:
        live = json.loads((target / 'live-fonts.json').read_text())
        startup = read_review_data(target)['fonts']
        keep = {face['url'] for manifest in (live, startup)
                for record in manifest.values() for face in record.get('faces', [record])}
        folder = target / 'fonts'
        if target.is_symlink() or folder.is_symlink():
            return []
        candidates = list(folder.iterdir())
    except (OSError, ValueError, KeyError, TypeError, AttributeError):
        # An incomplete manifest is not permission to delete.
        return []
    removed, obsolete = [], set()
    for path in candidates:
        match = re.fullmatch(r'reference-([0-9a-f]{64})\.(ttf|otf)', path.name)
        if not match or path.is_symlink() or not path.is_file():
            continue
        if f'fonts/{path.name}' in keep:
            stale_since.pop(path.name, None)
            continue
        obsolete.add(path.name)
        since = stale_since.setdefault(path.name, now)
        if now - since < CACHE_GRACE_SECONDS:
            continue
        try:
            if hashlib.sha256(path.read_bytes()).hexdigest() != match[1]:
                continue
            path.unlink()
            removed.append(path.name)
        except OSError:
            continue
    for name in list(stale_since):
        if name not in obsolete or name in removed:
            stale_since.pop(name, None)
    return removed


def read_review_data(folder):
    """The data of review-data.js in a prepared proof folder."""
    raw = (Path(folder) / 'review-data.js').read_text()
    return json.loads(raw[raw.index('=') + 1:].strip().removesuffix(';'))


class ReferenceCache:
    """The reference fonts, read again only when the files in the folder change.

    With `base_fonts` (the Before and Candidate records), each change also
    rewrites target/live-fonts.json with the base fonts and the references.
    """

    def __init__(self, folder, target, base_fonts=None, *, prune=False):
        self.folder, self.target = Path(folder), Path(target)
        self.base_fonts = base_fonts
        self.signature, self.value = None, None
        self.prune, self.stale_since = prune, {}

    def get(self):
        try:
            signature = [(str(p), p.stat().st_size, p.stat().st_mtime_ns, p.stat().st_ctime_ns)
                         for p in font_paths(self.folder)]
        except OSError as error:
            signature = str(error)
        if signature != self.signature:
            self.value = collect(self.folder, self.target)
            self.value['revision'] = hashlib.sha256(json.dumps(self.value, sort_keys=True).encode()).hexdigest()
            if self.base_fonts is not None:
                base_fonts = self.base_fonts
                if self.signature is not None:
                    # A prepare run can have replaced the Before and Candidate
                    # fonts since the start. Keep its records, not the first ones.
                    current = json.loads((self.target / 'live-fonts.json').read_text())
                    base_fonts = {key: value for key, value in current.items() if key in ('before', 'after')}
                temporary = self.target / '.live-fonts.json.partial'
                temporary.write_text(json.dumps({**base_fonts, **self.value['fonts']}, indent=2) + '\n')
                temporary.replace(self.target / 'live-fonts.json')
            self.signature = signature
        if self.prune:
            prune_reference_cache(self.target, self.stale_since, time.monotonic())
        return self.value
