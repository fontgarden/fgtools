"""Grade: the glyphs of the brand at even steps of the grade axis, at the lightest and the heaviest weight."""
from fontTools.ttLib import TTFont

SIZE, CELL = 128, 2


def draw(sheet, job):
    font = job.type
    with TTFont(font.path, lazy=True) as built:
        axes = built['fvar'].axes if 'fvar' in built else []
        grade = next(((axis.minValue, axis.maxValue) for axis in axes if axis.axisTag == 'GRAD'), None)
    if grade is None:
        return 'the font has no grade axis'
    steps = min(9, sheet.cols // CELL)
    glyphs = job.glyphs[:(sheet.rows - 2) // CELL]
    for weight in sorted({font.low, font.high}):
        sheet.page()
        sheet.header(job.family, 'Grade', f'Wght {weight:g}', sheet.size(SIZE), job.stamp)
        for step in range(steps):
            value = round(grade[0] + (grade[1] - grade[0]) * step / (steps - 1))
            sheet.label(str(value), step * CELL, 1, drop=0)
            for index, glyph in enumerate(glyphs):
                sheet.text(glyph, step * CELL, 2 + index * CELL, SIZE, weight, optical=True, grade=value)
