"""Tests of fgtools/check_repository.py on a small project in Git."""
import subprocess
import tempfile
import unittest
from pathlib import Path

from fgtools import check_repository
from tests import fixture

ROOT_FILES = ('.gitignore', 'AGENTS.md', 'AUTHORS.txt', 'CONTRIBUTORS.txt', 'OFL.txt', 'README.md',
              'STATUS.md', 'requirements.in', 'requirements.txt', '.github/workflows/build.yaml',
              '.agents/tasks/glyph-drafts.md', 'documentation/google-fonts.md')


class CheckRepository(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = fixture.write_project(Path(self.temp.name) / 'font')
        for name in ROOT_FILES:
            (self.root / name).parent.mkdir(parents=True, exist_ok=True)
            (self.root / name).write_text('text\n')
        (self.root / 'Makefile').write_text('build:\n\ttrue\n')
        subprocess.run(['git', 'init', '-q'], cwd=self.root, check=True)
        self.add()

    def tearDown(self):
        self.temp.cleanup()

    def add(self):
        subprocess.run(['git', 'add', '-A'], cwd=self.root, check=True)

    def test_a_project_in_the_layout_has_no_problems(self):
        self.assertEqual(check_repository.problems(self.root), [])

    def test_a_file_without_a_place_and_a_work_record_are_found(self):
        (self.root / 'notes.md').write_text('text\n')
        (self.root / 'documentation/handoff.md').write_text('text\n')
        self.add()
        found = check_repository.problems(self.root)
        self.assertIn('notes.md: no allowed place in the layout', found)
        self.assertIn('documentation/handoff.md: name of a work record', found)

    def test_a_missing_required_file_is_found(self):
        (self.root / 'AGENTS.md').unlink()
        self.assertIn('AGENTS.md: the layout requires it, and no file matches',
                      check_repository.problems(self.root))

    def test_stale_references_are_found(self):
        (self.root / 'README.md').write_text(
            'See [the notes](documentation/notes.md), `scripts/old.sh` and `make proof`.\n'
            'Run `make build`. `scripts/fontspector_checks.py` is optional.\n'
            'The file `scripts/gone.sh` is in the Git history.\n')
        self.add()
        self.assertEqual(check_repository.problems(self.root), [
            'README.md:1: link documentation/notes.md',
            'README.md:1: path scripts/old.sh',
            'README.md:1: make proof'])


if __name__ == '__main__':
    unittest.main()
