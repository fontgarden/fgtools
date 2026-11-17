"""Link card: the picture that a link to the font shows. The name, and the line of the brand."""


def draw(sheet, job):
    font = job.type
    if not font.covers(job.family.replace(' ', '')):
        return 'the font cannot set its name yet'
    size = next((size for size in (256, 128, 64) if font.measure(job.family, font.high)[0] * size <= sheet.measure
                 and size * 1.25 <= (sheet.rows - 3) * sheet.grid['module']), 64)
    sheet.page()
    sheet.header(job.designer, f'Version {job.facts["version"]}', job.url)
    sheet.text(job.family, 0, 1, size, font.high, optical=True)
    sheet.rule(sheet.rows - 2)
    sheet.text(job.brand.get('text', {}).get('tagline', ''), 0, sheet.rows - 2, 32, font.low, drop=16)
