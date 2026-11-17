"""Glyph: one glyph for each page on the grid of its design, with its points and its metrics.

The glyph is as large as the lattice allows: at an em of 1024 pixels, 1 pixel is 1 unit of the
font, and the grid of the picture is the grid of the drawing."""


def draw(sheet, job):
    font, module = job.type, sheet.grid['module']
    if not job.glyphs:
        return 'the font has no glyph to show yet'
    for character in job.glyphs:
        advance = font.measure(character)[0]
        em = next((em for em in (1024, 512, 256) if (font.cap - font.descender) * em <= (sheet.rows - 2) * module
                   and advance * em <= sheet.measure), 256)
        unit = em / font.upm                                  # pixels for one unit of the font
        col = round((sheet.cols - advance * em / module) / 2)
        x0, top = sheet.x(col), sheet.y(1)
        baseline, bottom = top + font.cap * em, top + (font.cap - font.descender) * em
        sheet.page()
        outline = job.outline(character)
        name = outline['name'] if outline else character
        sheet.header(job.family, f'{name}  U+{ord(character):04X}', f'1 px = {1 / unit:g} unit' + ('' if unit == 1 else 's'))
        # The design grid: the large step of the grid of the font.
        step = module * unit * font.upm / 1024
        x = sheet.x(0)
        while x <= sheet.x(sheet.cols) + 0.5:
            sheet.line(x, top, x, bottom, 'grid', 1)
            x += step
        y = top
        while y <= bottom + 0.5:
            sheet.line(sheet.x(0), y, sheet.x(sheet.cols), y, 'grid', 1)
            y += step
        # The metrics, with their values in units of the font.
        for label, value in (('Cap height', font.cap), ('x-height', font.x_height), ('Baseline', 0),
                             ('Descender', font.descender)):
            y = baseline - value * em
            sheet.line(sheet.x(0), y, sheet.x(sheet.cols), y, 'secondary')
            row = (y - sheet.y(0)) / module
            drop = -28 if value < 0 else 8          # under its line; the descender has its label above
            sheet.label(label, 0, row, drop=drop, free=True)
            sheet.label(f'{value * font.upm:g}', sheet.cols, row, flush='right', drop=drop, free=True)
        for x in (x0, x0 + advance * em):
            sheet.line(x, top, x, bottom, 'secondary')
        sheet.text(character, col, 1, em, font.low)
        # The points of the drawing: handles, then points on the curve and off it.
        if outline:
            place = lambda point: (x0 + point[0] * unit, baseline - point[1] * unit)
            dot = 12 if em >= 1024 else 8
            for contour in outline['contours']:
                count = len(contour)
                for index, (point, kind) in enumerate(contour):
                    if kind is None:
                        for other in (contour[index - 1], contour[(index + 1) % count]):
                            if other[1] is not None:
                                sheet.line(*place(point), *place(other[0]), 'accent', 1)
                for point, kind in contour:
                    x, y = place(point)
                    if kind is None:
                        sheet.oval(x - dot / 2, y - dot / 2, dot, dot, 'accent')
                    else:
                        sheet.rect(x - dot / 2, y - dot / 2, dot, dot, 'accent')
        sheet.rule(sheet.rows - 1)
        sheet.label(f'Advance {advance * font.upm:g}', 0, sheet.rows - 1)
        sheet.label(job.url, sheet.cols, sheet.rows - 1, flush='right')
