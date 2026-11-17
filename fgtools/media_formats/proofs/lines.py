"""Lines: the short samples of fgtools and of sources/proof-samples.toml of the project, each with its label.
A sample that mixes a script from the left with a script from the right is left out: DesignBot sets a
line in one direction."""
import unicodedata

SIZE, LEADING = 32, 48
LABELS = 6


def one_direction(text):
    directions = {unicodedata.bidirectional(character) for character in text}
    return not ('L' in directions and directions & {'R', 'AL'})


def draw(sheet, job):
    font = job.type
    samples = [(sample.get('label', key), sample['text']) for key, sample in job.samples.get('sample', {}).items()
               if font.covers(sample.get('text', '').replace(' ', '') or '.') and one_direction(sample['text'])]
    if not samples:
        return 'the font can set no sample yet'
    cols, module = sheet.cols - LABELS, sheet.grid['module']
    for weight in sorted({font.low, font.high}):
        row = sheet.rows
        for label, text in samples:
            lines = font.lines(text, cols * module, SIZE, weight)
            rows = -(-((len(lines) - 1) * LEADING + SIZE) // module)
            if row + rows > sheet.rows:
                sheet.page()
                sheet.header(job.family, 'Lines', f'Wght {weight:g}', sheet.size(SIZE, LEADING), job.stamp)
                row = 1
            sheet.rule(row)
            if font.covers(label.replace(' ', '')):
                sheet.label(label, 0, row)
            sheet.paragraph(text, LABELS, row, cols, SIZE, LEADING, weight, drop=16)
            row += rows + 1
