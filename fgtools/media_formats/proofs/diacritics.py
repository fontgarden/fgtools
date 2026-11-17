"""Diacritics: each letter with a mark that the font encodes, beside its base letter, for each master."""
import unicodedata

SIZE, LEADING = 32, 48


def draw(sheet, job):
    font = job.type
    groups = {}
    for code in sorted(font.characters):
        character = chr(code)
        parts = unicodedata.normalize('NFD', character)
        if len(parts) > 1 and parts[0].isalpha() and unicodedata.category(parts[1])[0] == 'M' \
                and unicodedata.name(parts[0], '').startswith('LATIN') and font.covers(parts[0]):
            groups.setdefault(parts[0], []).append(character)
    if not groups or not font.covers(' '):
        return 'the font has no letter with a mark yet'
    cases = [('Small letters', str.islower), ('Capital letters', str.isupper)]
    weights = sorted({font.low, font.high})
    for weight in weights:
        sheet.page()
        sheet.header(job.family, 'Diacritics', f'Wght {weight:g}', sheet.size(SIZE, LEADING), job.stamp)
        row = 1
        for title, test in cases:
            text = ' '.join(base + ''.join(marked) for base, marked in sorted(groups.items()) if test(base))
            left = sheet.rows - row - 1
            if not text or left < 1:
                continue
            sheet.label(title, 0, row, drop=0)
            row += sheet.paragraph(text, 4, row, sheet.cols - 4, SIZE, LEADING, weight, sheet.room(left, SIZE, LEADING)) + 1
