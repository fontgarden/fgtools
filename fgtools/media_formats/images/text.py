"""Text: the line of the brand at 64 pixels, and the description of the font at 32 pixels."""


def block(sheet, job, lines, row, size, leading, weight, limit):
    """Set lines from a row line down, and return the number of modules that they take."""
    lines = lines[:limit]
    for index, line in enumerate(lines):
        sheet.text(line, 0, row, size, weight, drop=index * leading)
    return -(-((len(lines) - 1) * leading + size) // sheet.grid['module'])


def draw(sheet, job):
    font = job.type
    head, body = job.brand.get('text', {}).get('tagline', ''), job.description
    if not font.covers((head + body).replace(' ', '') or '.'):
        return 'the font cannot set the text yet'
    sheet.page()
    row = 0
    if head:
        sheet.header(job.family, f'Wght {font.high:g}', sheet.size(64, 80), row=row)
        row += 1 + block(sheet, job, font.lines(head, sheet.measure, 64, font.high), row + 1, 64, 80, font.high, 4) + 1
    if body:
        sheet.header(job.family, f'Wght {font.low:g}', sheet.size(32, 48), row=row)
        room = (sheet.rows - 1 - (row + 1)) * sheet.grid['module'] // 48
        block(sheet, job, font.lines(body, sheet.measure, 32, font.low), row + 1, 32, 48, font.low, room)
    sheet.header(job.url, row=sheet.rows - 1)
