"""Big words: one word for each weight, at one size. Each word is chosen so that it fills the measure."""

SIZE = 256
BLOCK = 5       # modules: one for the label, three for the cap height, one for the descenders


def draw(sheet, job):
    font = job.type
    count = max(1, (sheet.rows - 1) // BLOCK)
    sheet.axis = True
    sheet.page()
    used = []
    for index in range(count):
        weight = round(font.low + (font.high - font.low) * index / max(count - 1, 1))
        word = font.fit(job.words['Latin'], sheet.measure, SIZE, weight, used) or \
            font.fit(job.words['Latin'], sheet.measure, SIZE, weight, used, least=0)
        if not word:
            return 'the font can set no word yet'
        used.append(word)
        row = index * BLOCK
        sheet.header(job.family, f'Wght {weight}', sheet.size(SIZE), word, row=row)
        sheet.text(word, 0, row + 1, SIZE, weight, optical=True)
    sheet.header(job.url, row=sheet.rows - 1)
