"""Character set: every character that the font encodes, one in each module."""
import unicodedata

SIZE = 32
CIRCLE = '◌'       # the dotted circle that carries a mark


def shown(font, character):
    """The text that shows a character, or nothing for a character without ink."""
    category = unicodedata.category(character)
    if category[0] in 'CZ':
        return ''
    if category[0] == 'M':
        return CIRCLE + character if font.covers(CIRCLE) else ''
    return character


def draw(sheet, job):
    font, module = job.type, sheet.grid['module']
    texts = [text for text in (shown(font, chr(code)) for code in sorted(font.characters)) if text]
    across, down = sheet.cols, sheet.rows - 1
    for start in range(0, len(texts), across * down):
        part = texts[start:start + across * down]
        sheet.page()
        sheet.header(job.family, 'Character set', f'{len(texts)} characters', job.stamp)
        for index, text in enumerate(part):
            line, place = divmod(index, across)
            advance = font.measure(text)[0] * SIZE
            # A character stands in the middle of its module: an optical position, not a lattice one.
            sheet.text(text, place + (module - advance) / 2 / module, 1 + line + 0.3, SIZE, free=True)
        for line in range(1, -(-len(part) // across) + 2):
            sheet.rule(line)
