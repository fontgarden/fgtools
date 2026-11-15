"""Tests of the review classification in fontgarden/list_corrections.py."""
import subprocess
import tempfile
import unittest
from pathlib import Path

from fontgarden import list_corrections as corrections
from tests import fixture
from tests.fixture import GREEN, ORANGE, PURPLE, YELLOW


def glif(mark, right=100, advance=200):
    return fixture.glif('square', mark, right=right, advance=advance)


class Review(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        root = fixture.write_project(Path(self.temp.name) / 'font')
        self.directory = fixture.working_directory(root)
        self.directory.__enter__()

    def tearDown(self):
        self.directory.__exit__(None, None, None)
        self.temp.cleanup()

    def test_the_new_mark_of_a_purple_draft_is_the_grade(self):
        self.assertEqual(corrections.grade(glif(PURPLE), glif(ORANGE)), 'orange')
        self.assertEqual(corrections.grade(glif(PURPLE), glif(GREEN)), 'green')

    def test_a_change_that_keeps_or_never_had_purple_is_not_a_review(self):
        self.assertIsNone(corrections.grade(glif(PURPLE), glif(PURPLE, right=150)))
        self.assertIsNone(corrections.grade(glif(ORANGE), glif(GREEN)))

    def test_the_same_outline_is_accepted(self):
        row = corrections.outcome(glif(PURPLE), glif(GREEN))
        self.assertEqual((row['result'], row['iou']), ('accepted', 1.0))

    def test_another_outline_or_advance_is_corrected(self):
        row = corrections.outcome(glif(PURPLE), glif(GREEN, right=150))
        self.assertEqual(row['result'], 'corrected')
        self.assertLess(row['iou'], 1.0)
        self.assertEqual(corrections.outcome(glif(PURPLE), glif(GREEN, advance=220))['result'],
                         'corrected')


class History(unittest.TestCase):
    def test_a_yellow_draft_is_compared_with_its_later_green_version_and_cited(self):
        with tempfile.TemporaryDirectory() as temp:
            root = fixture.write_project(Path(temp) / 'font')
            path = root / 'sources/Test-Bold.ufo/glyphs/square.glif'

            def commit(message, text=None):
                if text:
                    path.write_text(text)
                subprocess.run(['git', 'add', '-A'], cwd=root, check=True)
                subprocess.run(['git', '-c', 'user.name=Test', '-c', 'user.email=test@example.com',
                                '-c', 'commit.gpgsign=false',
                                'commit', '-q', '--allow-empty', '-m', message], cwd=root, check=True)
                return subprocess.run(['git', 'rev-parse', 'HEAD'], cwd=root, check=True,
                                      capture_output=True, text=True).stdout.strip()

            subprocess.run(['git', 'init', '-q'], cwd=root, check=True)
            commit('Draft', glif(PURPLE))
            correction = commit('Grade yellow', glif(YELLOW, right=120))
            [row] = corrections.reviews(root)
            self.assertEqual((row['grade'], row['against'], row['result'], row['master']),
                             ('yellow', 'yellow', 'corrected', 'Bold'))
            commit('Redraft', glif(PURPLE, right=100))
            commit('Approve', glif(GREEN, right=150))
            first, second = corrections.reviews(root)
            self.assertEqual((first['commit'], first['glyph'], first['against']),
                             (correction, 'square', 'green'))
            self.assertAlmostEqual(first['iou'], 2 / 3, delta=0.03)
            self.assertEqual((second['grade'], second['against']), ('green', 'green'))
            self.assertNotIn(correction[:7], corrections.citations(root))
            commit(f'Add a rule entry from {correction[:8]}')
            self.assertIn(correction[:7], corrections.citations(root))

            # A review pass of glyphs that are not purple.
            start = commit('Before the pass', glif(ORANGE, right=150))
            self.assertEqual(corrections.pass_reviews(start, root), [])
            edit = commit('Thinner bar', glif(ORANGE, right=130))
            [row] = corrections.pass_reviews(start, root)
            self.assertEqual((row['commit'], row['was'], row['grade'], row['result']),
                             (edit, 'orange', 'orange', 'corrected'))
            commit('Approve', glif(GREEN, right=130))
            [row] = corrections.pass_reviews(start, root)
            self.assertEqual((row['grade'], row['result']), ('green', 'corrected'))


if __name__ == '__main__':
    unittest.main()
