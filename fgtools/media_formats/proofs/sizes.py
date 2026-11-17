"""Sizes: the first line of a text at each size of the scale, for each script and each master."""

SIZES = [(256, 5), (128, 3), (64, 2), (32, 1), (16, 1)]     # the size, and the modules that its line takes
LABELS = 2
SCRIPTS = ['Latin', 'Arabic', 'Hebrew']


def draw(sheet, job):
    font = job.type
    sheet.waterfall = True
    measure = (sheet.cols - LABELS) * sheet.grid['module']
    for script in SCRIPTS:
        text = job.texts.get(script)
        if not text:
            continue
        right = font.right_to_left(text)
        for weight in sorted({font.low, font.high}):
            sheet.page()
            sheet.header(job.family, f'Sizes, {script}', f'Wght {weight:g}', job.stamp)
            row = 1
            for size, rows in SIZES:
                if size not in sheet.grid['sizes'] or row + rows > sheet.rows:
                    continue
                line = font.lines(text, measure, size, weight)[0]
                if font.measure(line, weight)[0] * size < measure * 0.6:
                    # A large size has room for one word: the word of the text that fills the measure best.
                    line = font.fit(sorted(set(text.replace(',', ' ').replace('.', ' ').split())), measure * 0.95, size,
                                    weight, least=0) or line
                if font.measure(line, weight)[0] * size > measure:
                    continue
                sheet.label(sheet.size(size), 0, row, drop=0)
                sheet.text(line, sheet.cols if right else LABELS, row, size, weight,
                           flush='right' if right else 'left')
                row += rows
    if not sheet.pages:
        return 'the font can set no text yet'
