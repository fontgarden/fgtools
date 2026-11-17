"""Scripts: one word in each script of the font, each chosen so that it fills the measure."""

DIRECTION = {'Latin': 'Left to right', 'Arabic': 'Right to left', 'Hebrew': 'Right to left'}


def draw(sheet, job):
    font = job.type
    scripts = [name for name in DIRECTION if any(font.covers(word) for word in job.words.get(name, []))]
    if len(scripts) < 2:
        return 'the font has one script'
    size, block = (256, 5) if len(scripts) * 5 <= sheet.rows - 1 else (128, 3)
    sheet.page()
    for index, script in enumerate(scripts):
        row = index * block
        word = font.fit(job.words[script], sheet.measure, size, font.low) or \
            font.fit(job.words[script], sheet.measure, size, font.low, least=0)
        sheet.header(script, DIRECTION[script], sheet.size(size), job.family, row=row)
        if script == 'Latin':
            sheet.text(word, 0, row + 1, size, font.low, optical=True)
        else:
            sheet.text(word, sheet.cols, row + 1, size, font.low, optical=True, flush='right')
    sheet.header(job.url, row=sheet.rows - 1)
