"""Reading: a text at the two reading sizes, 8 and 16 points on paper, for each script and each master."""

SMALL, LARGE = (16, 24), (32, 48)       # the size and the leading
NARROW = 7                              # modules of the small column
SCRIPTS = ['Latin', 'Arabic', 'Hebrew']


def draw(sheet, job):
    font = job.type
    if SMALL[0] not in sheet.grid['sizes']:
        return 'the canvas has no reading size'
    rows = sheet.rows - 1
    for script in SCRIPTS:
        text = job.texts.get(script)
        if not text:
            continue
        text = ' '.join([text] * 4)
        for weight in sorted({font.low, font.high}):
            sheet.page()
            sheet.header(job.family, f'Reading, {script}', f'Wght {weight:g}',
                         f'{sheet.size(*SMALL)} and {sheet.size(*LARGE)} pt', job.stamp)
            wide = sheet.cols - NARROW - 1
            columns = [(0, NARROW, SMALL), (NARROW + 1, wide, LARGE)]
            if font.right_to_left(text):
                columns = [(sheet.cols - NARROW, NARROW, SMALL), (0, wide, LARGE)]
            for col, cols, (size, leading) in columns:
                sheet.paragraph(text, col, 1, cols, size, leading, weight, sheet.room(rows, size, leading))
    if not sheet.pages:
        return 'the font can set no text yet'
