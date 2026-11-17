"""Arabic joining: each letter in its isolated, final, medial and initial form."""

SIZE = 32
JOINER = '‍'
LETTERS = 'ابتثجحخدذرزسشصضطظعغفقكلمنهويءةىپچژگک'
RIGHT_JOINING = 'ادذرزوءةىژ'       # these join to the right only: no medial and no initial form
BLOCK = 7                           # modules of one block: four forms


def draw(sheet, job):
    font = job.type
    letters = [letter for letter in LETTERS if font.covers(letter)]
    if len(letters) < 20:
        return 'the font has no Arabic alphabet yet'
    down = sheet.rows - 2
    blocks = sheet.cols // BLOCK
    for start in range(0, len(letters), down * blocks):
        sheet.page()
        sheet.header(job.family, 'Arabic joining', sheet.size(SIZE), job.stamp)
        for block in range(blocks):
            left = block * BLOCK
            for index, name in enumerate(('Initial', 'Medial', 'Final', 'Isolated')):
                sheet.label(name, left + 0.5 + index * 1.5, 1, drop=0)
        for index, letter in enumerate(letters[start:start + down * blocks]):
            block, line = divmod(index, down)
            left, row = block * BLOCK, 2 + line
            both = letter not in RIGHT_JOINING
            forms = [letter + JOINER if both else '', JOINER + letter + JOINER if both else '',
                     JOINER + letter if letter != 'ء' else '', letter]
            sheet.rule(row, left, left + BLOCK - 1)
            for place, form in enumerate(forms):
                if form:
                    sheet.text(form, left + 0.5 + place * 1.5, row, SIZE, drop=16)
