"""Release: the name of the font and its facts, read from the font file."""


def draw(sheet, job):
    font, facts = job.type, job.facts
    if not font.covers(job.family.replace(' ', '')):
        return 'the font cannot set its name yet'
    fits = lambda text, size: font.measure(text, font.high, size=size)[0] * size <= sheet.measure
    size = next((size for size in (256, 128) if all(fits(word, size) for word in job.family.split())), 64)
    lines = [job.family] if fits(job.family, size) else job.family.split()
    step = size // sheet.grid['module']
    sheet.page()
    sheet.header(job.designer, f'Version {facts["version"]}', job.url)
    for index, line in enumerate(lines):
        sheet.text(line, 0, 1 + index * step, size, font.high, optical=True)
    weights = f'{font.low:g} to {font.high:g}' if font.high > font.low else f'{font.low:g}'
    table = [('Weights', weights), ('Glyphs', str(facts['glyphs'])), ('Characters', str(facts['characters'])),
             ('Scripts', ', '.join(facts['scripts'])), ('License', 'SIL Open Font License 1.1')]
    row = 1 + len(lines) * step + 1
    for key, value in table[:max(0, sheet.rows - 1 - row)]:
        sheet.rule(row)
        sheet.label(key, 0, row)
        sheet.text(value, 4, row, 32, font.low, drop=16)
        row += 1
    sheet.rule(row)
