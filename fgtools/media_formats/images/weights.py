"""The weight axis as a ladder: one text at each weight, from the lightest to the heaviest."""

SIZE = 128
LABELS = 2      # modules for the weight values at the left


def draw(sheet, job):
    font = job.type
    if font.high == font.low:
        return 'the font has one weight'
    count = min(7, (sheet.rows - 2) // 2)
    measure = (sheet.cols - LABELS) * sheet.grid['module']
    text = font.fit(job.words['Latin'], measure, SIZE, font.high) or font.fit(job.words['Latin'], measure, SIZE, font.high, least=0)
    if not text:
        return 'the font can set no word yet'
    sheet.axis = True
    sheet.page()
    sheet.header(job.family, sheet.size(SIZE, SIZE), f'Wght {font.low:g} to {font.high:g}')
    for index in range(count):
        weight = round(font.low + (font.high - font.low) * index / (count - 1))
        row = 1 + index * 2
        sheet.label(str(weight), 0, row, drop=0)
        sheet.text(text, LABELS, row, SIZE, weight, optical=True)
    sheet.header(job.url, row=sheet.rows - 1)
