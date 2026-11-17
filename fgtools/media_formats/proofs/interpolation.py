"""Interpolation: the glyphs of the brand at even steps of the weight axis."""

SIZE, CELL = 128, 2


def draw(sheet, job):
    font, module = job.type, sheet.grid['module']
    if font.high == font.low:
        return 'the font has one weight'
    steps = min(11, sheet.cols // CELL)
    glyphs = job.glyphs[:(sheet.rows - 2) // CELL]
    sheet.axis = True
    sheet.page()
    sheet.header(job.family, 'Interpolation', sheet.size(SIZE), job.stamp)
    for step in range(steps):
        weight = round(font.low + (font.high - font.low) * step / (steps - 1))
        sheet.label(str(weight), step * CELL, 1, drop=0)
        for index, glyph in enumerate(glyphs):
            sheet.text(glyph, step * CELL, 2 + index * CELL, SIZE, weight, optical=True)
