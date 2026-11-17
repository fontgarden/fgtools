"""Weight axis: one text from the lightest weight to the heaviest and back. A loop of 256 frames.

One value moves. A line shows the axis and a square shows the value. The square moves a whole
number of units in each frame."""

SIZE, FRAMES = 256, 256


def draw(sheet, job):
    font, unit = job.type, sheet.grid['unit']
    if font.high == font.low:
        return 'the font has one weight'
    text = font.fit(job.words['Latin'], sheet.measure, SIZE, font.high) or \
        font.fit(job.words['Latin'], sheet.measure, SIZE, font.high, least=0)
    if not text:
        return 'the font can set no word yet'
    step = unit * -(-sheet.measure // (unit * 112))       # pixels in one frame
    up = sheet.measure // step
    hold = (FRAMES - 2 * up) // 2
    positions = [k * step for k in range(up)] + [sheet.measure] * hold + \
        [sheet.measure - k * step for k in range(up)] + [0] * hold
    sheet.axis = True
    line = 6                                               # the row of the axis line
    for position in positions:
        weight = font.low + (font.high - font.low) * position / sheet.measure
        sheet.page(1 / 30)
        sheet.header(job.family, f'Wght {weight:.0f}', sheet.size(SIZE))
        sheet.text(text, 0, 1, SIZE, weight, optical=True)
        sheet.rule(line, color='secondary')
        for value in job.facts['instances']:
            x = sheet.x(0) + sheet.measure * (value - font.low) / (font.high - font.low)
            sheet.line(x, sheet.y(line), x, sheet.y(line) + 16, 'secondary')
            flush = 'right' if value == font.high else 'left'
            col = (x - sheet.x(0)) / sheet.grid['module']
            sheet.label(f'{value:g}', col, line, flush=flush, drop=24, free=True)
        sheet.rect(sheet.x(0) + position - 8, sheet.y(line) - 8, 16, 16, 'accent')
