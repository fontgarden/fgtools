"""Spacing: each letter between two straight and two round control letters, for each master."""

SIZE, LEADING = 32, 48
LABELS = 4
GROUPS = [
    ('Capital letters', 'ABCDEFGHIJKLMNOPQRSTUVWXYZ', 'H', 'O'),
    ('Small letters', 'abcdefghijklmnopqrstuvwxyz', 'n', 'o'),
    ('Figures', '0123456789', '1', '0'),
]


def draw(sheet, job):
    font = job.type
    groups = []
    for title, letters, straight, round_ in GROUPS:
        if not font.covers(straight + round_ + ' '):
            continue
        words = [f'{straight}{straight}{letter}{straight}{round_}{letter}{round_}{round_}'
                 for letter in letters if font.covers(letter)]
        if words:
            groups.append((title, ' '.join(words)))
    if not groups:
        return 'the font has no control letters yet'
    for weight in sorted({font.low, font.high}):
        sheet.page()
        sheet.header(job.family, 'Spacing', f'Wght {weight:g}', sheet.size(SIZE, LEADING), job.stamp)
        row = 1
        for title, text in groups:
            left = sheet.rows - row - 1
            if left < 1:
                break
            sheet.label(title, 0, row, drop=0)
            row += sheet.paragraph(text, LABELS, row, sheet.cols - LABELS, SIZE, LEADING, weight,
                                   sheet.room(left, SIZE, LEADING)) + 1
