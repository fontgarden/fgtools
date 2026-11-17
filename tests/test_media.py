"""Tests of fgtools/media.py: the formats of a project and the outputs."""
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace

from fgtools import media


def project_with(formats='', scripts=None):
    """A project with formats.toml and the scripts {name: folder}."""
    root = Path(tempfile.mkdtemp())
    folder = root / 'documentation/media'
    folder.mkdir(parents=True)
    (folder / 'brand.toml').write_text('[text]\nwords = ["A"]\n')
    if formats:
        (folder / 'formats.toml').write_text(formats)
    for name, kind_folder in (scripts or {}).items():
        (folder / kind_folder).mkdir(exist_ok=True)
        (folder / kind_folder / f'{name}.py').write_text('def draw(sheet, job):\n    sheet.page()\n')
    return SimpleNamespace(root=root)


class Media(unittest.TestCase):
    def test_a_project_without_files_has_the_default_formats(self):
        formats = media.load_brand(SimpleNamespace(root=Path(tempfile.mkdtemp())))['format']
        self.assertEqual((formats['weight-axis']['kind'], formats['weight-axis']['own']), ('video', False))
        self.assertEqual(formats['glyph']['kind'], 'carousel')
        for name, table in formats.items():
            self.assertTrue(table['script'].is_file(), name)
            for canvas in table['canvases']:
                self.assertIn(canvas, media.canvases(), name)

    def test_a_project_changes_a_default_format_and_adds_its_own(self):
        layout = project_with('[words]\ncanvases = ["square"]\ncaption = "Words"\n\n[loop]\ncanvases = ["vertical"]\n',
                              {'loop': 'videos', 'release': 'images'})
        formats = media.load_brand(layout)['format']
        self.assertEqual((formats['words']['canvases'], formats['words']['caption']), (['square'], 'Words'))
        self.assertEqual((formats['loop']['kind'], formats['loop']['own']), ('video', True))
        self.assertTrue(formats['release']['own'])
        self.assertFalse(formats['link-card']['own'])
        found = media.outputs({'format': formats}, ['words', 'loop'])
        self.assertEqual([(name, canvas) for name, _, canvas, _ in found], [('words', 'square'), ('loop', 'vertical')])

    def test_a_format_without_a_script_or_with_an_unknown_canvas_stops_the_command(self):
        with self.assertRaises(SystemExit):
            media.load_brand(project_with('[poster]\ncanvases = ["portrait"]\n'))
        layout = project_with('[poster]\ncanvases = ["poster-size"]\n', {'poster': 'images'})
        with self.assertRaises(SystemExit):
            media.outputs(media.load_brand(layout))

    def test_the_description_is_the_first_paragraph_of_the_design_file(self):
        root = Path(tempfile.mkdtemp())
        (root / 'CONTEXT.md').write_text('# A Font\n\nA Font is a `typeface`\nfor tests.\n\nSecond paragraph.\n')
        self.assertEqual(media.description(SimpleNamespace(root=root)), 'A Font is a typeface for tests.')

    def test_the_commit_of_a_folder_outside_git_is_none(self):
        self.assertIsNone(media.commit(tempfile.mkdtemp()))


if __name__ == '__main__':
    unittest.main()
