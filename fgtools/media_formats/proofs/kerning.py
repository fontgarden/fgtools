"""Kerning and figures: the pairs that most often need kerning, words with them, and the figures."""

SIZE, LEADING = 64, 80
PAIRS = 'AV AW AY AT VA WA YA LT LY PA To Ta Te Tr Ty Yo Ya Ve Vo We r. y. f) P. F. 7. 74'
WORDS = 'Toronto Voyage Water LAWYER'
FIGURES = '0123456789'
MONEY = '$1,234.56 €789 £60 ¥1,234 50%'


def kept(font, text):
    """The words of a text that the font can set."""
    return ' '.join(word for word in text.split() if font.covers(word)) if font.covers(' ') else ''


def draw(sheet, job):
    font = job.type
    parts = [('Pairs', kept(font, PAIRS), ()), ('Words', kept(font, WORDS), ()),
             ('Figures', kept(font, FIGURES), ()), ('Tabular figures', kept(font, FIGURES), ('tnum',)),
             ('Figures in text', kept(font, MONEY), ())]
    parts = [part for part in parts if part[1]]
    if not parts:
        return 'the font can set no pair yet'
    module = sheet.grid['module']
    for weight in sorted({font.low, font.high}):
        row = sheet.rows
        for title, text, features in parts:
            lines = font.lines(text, sheet.measure - 4 * module, SIZE, weight)
            rows = -(-((len(lines) - 1) * LEADING + SIZE) // module) + 1
            if row + rows > sheet.rows:
                sheet.page()
                sheet.header(job.family, 'Kerning and figures', f'Wght {weight:g}', sheet.size(SIZE, LEADING), job.stamp)
                row = 1
            sheet.label(title, 0, row, drop=0)
            for index, line in enumerate(lines):
                sheet.text(line, 4, row, SIZE, weight, drop=index * LEADING, features=features)
            row += rows
