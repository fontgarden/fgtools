"""Arabic marks: each vowel mark on letters of each shape, for each master."""

SIZE, CELL = 64, 2
MARKS = [('Fatha', 'َ'), ('Damma', 'ُ'), ('Kasra', 'ِ'), ('Sukun', 'ْ'), ('Shadda', 'ّ'),
         ('Fathatan', 'ً'), ('Dammatan', 'ٌ'), ('Kasratan', 'ٍ'), ('Shadda a', 'َّ'),
         ('Shadda i', 'ِّ')]
BASES = 'ابحسصطعفكلمه'      # a stroke, a tooth, bowls, loops, an ascender and descenders


def draw(sheet, job):
    font = job.type
    marks = [(name, mark) for name, mark in MARKS if font.covers(mark)][:sheet.cols // CELL]
    bases = [base for base in BASES if font.covers(base)]
    if not marks or not bases:
        return 'the font has no Arabic marks yet'
    down = (sheet.rows - 2) // CELL
    for weight in sorted({font.low, font.high}):
        for start in range(0, len(bases), down):
            sheet.page()
            sheet.header(job.family, 'Arabic marks', f'Wght {weight:g}', sheet.size(SIZE), job.stamp)
            for place, (name, mark) in enumerate(marks):
                sheet.label(name, place * CELL, 1, drop=0)
                for line, base in enumerate(bases[start:start + down]):
                    sheet.text(base + mark, place * CELL, 2 + line * CELL + 0.5, SIZE, weight)
            for line in range(len(bases[start:start + down]) + 1):
                sheet.rule(2 + line * CELL)
