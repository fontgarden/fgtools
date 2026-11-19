"""Characters: the characters of the font in cells of two modules, one group for each page."""

GROUPS = [
    ('Capital letters', 'ABCDEFGHIJKLMNOPQRSTUVWXYZ', False),
    ('Small letters', 'abcdefghijklmnopqrstuvwxyz', False),
    ('Figures and punctuation', '0123456789.,:;!?&@#$%()[]{}/*+-=<>', False),
    ('Arabic', 'ابتثجحخدذرزسشصضطظعغفقكلمنهوي', True),
    ('Hebrew', 'אבגדהוזחטיכלמנסעפצקרשתךםןףץ', True),
]
SIZE, CELL = 64, 2


def draw(sheet, job):
    font, module = job.type, sheet.grid['module']
    across, down = sheet.cols // CELL, (sheet.rows - 2) // CELL
    drawn = False
    for title, characters, right_to_left in GROUPS:
        characters = [character for character in characters if font.covers(character)]
        for start in range(0, len(characters), across * down):
            part = characters[start:start + across * down]
            sheet.page()
            drawn = True
            sheet.header(job.family, title, sheet.size(SIZE), f'{len(characters)} characters')
            for index, character in enumerate(part):
                line, place = divmod(index, across)
                place = across - 1 - place if right_to_left else place
                row = 1 + line * CELL
                if index % across == 0:
                    sheet.rule(row)
                advance = font.measure(character, size=SIZE)[0] * SIZE
                # A character stands in the middle of its cell: an optical position, not a lattice one.
                sheet.text(character, place * CELL + (CELL * module - advance) / 2 / module, row + 0.5, SIZE, free=True)
            sheet.rule(1 + (-(-len(part) // across)) * CELL)
            sheet.header(job.url, row=sheet.rows - 1)
    if not drawn:
        return 'the font has no character of these groups yet'
