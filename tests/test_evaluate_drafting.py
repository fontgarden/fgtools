"""Tests of the scores and the task preparation in fgtools/evaluate_drafting.py."""
import contextlib
import io
import json
import os
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from fgtools import check_design
from fgtools import evaluate_drafting as evaluation
from fgtools import project
from tests import fixture

SQUARE = [(0, 0), (100, 0), (100, 100), (0, 100)]


def glyph(contours, advance=200):
    points = [p for c in contours for p in c]
    return dict(advance=advance, contours=contours, points=points,
                structure=[['line'] * len(c) for c in contours])


class DraftingEvaluation(unittest.TestCase):
    def test_identical_outlines_score_as_identical(self):
        row = evaluation.compare(glyph([SQUARE]), glyph([SQUARE]))
        self.assertEqual((row['iou'], row['distance'], row['moved']), (1.0, 0.0, '0 of 4'))

    def test_a_shifted_outline_loses_overlap_and_reports_moved_points(self):
        shifted = [(x + 50, y) for x, y in SQUARE]
        row = evaluation.compare(glyph([SQUARE]), glyph([shifted], advance=240))
        self.assertAlmostEqual(row['iou'], 1 / 3, delta=0.05)
        self.assertEqual((row['moved'], row['advance']), ('4 of 4', 40))

    def test_an_empty_candidate_scores_zero(self):
        row = evaluation.compare(glyph([SQUARE]), glyph([]))
        self.assertEqual((row['iou'], row['moved']), (0.0, 'no outline'))


class Cases:
    """Case checks for one project, given by `root`."""
    root = None

    def test_every_case_is_green_where_it_is_scored(self):
        masters = project.load(self.root).masters
        green = evaluation.green_masters(self.root)
        for task in evaluation.TASKS:
            for case in evaluation.cases(task, self.root):
                with self.subTest(task=task, glyph=case['glyph']):
                    self.assertTrue(case['scored'])
                    if task == 'bold':
                        self.assertIn(masters[0], green[case['glyph']])
                    targets = {c['glyph'] for c in evaluation.cases(task, self.root)}
                    for donor in case['donors']:
                        self.assertNotIn(donor, targets)
                        self.assertTrue(set(green.get(donor, [])) >= set(case['scored']), donor)

    def test_prepare_sets_each_task(self):
        masters = project.load(self.root).masters
        with tempfile.TemporaryDirectory() as temp, fixture.working_directory(self.root):
            for task in evaluation.TASKS:
                run = Path(temp) / task
                with contextlib.redirect_stdout(io.StringIO()):
                    evaluation.prepare(task, run, self.root)
                case = evaluation.cases(task, self.root)[0]
                for master in masters:
                    with self.subTest(task=task, master=master):
                        before = evaluation.read(evaluation.glif_path(self.root, master, case['glyph']))
                        after = evaluation.read(evaluation.glif_path(run, master, case['glyph']))
                        if master not in case['changed']:
                            self.assertEqual(after, before)
                        elif task == 'repair':
                            self.assertEqual(after['structure'], before['structure'])
                            self.assertNotEqual(after['points'], before['points'])
                        else:
                            self.assertEqual((after['contours'], after['advance']), ([], 0))
                        for donor in case['donors']:
                            self.assertEqual(
                                evaluation.read(evaluation.glif_path(run, master, donor)),
                                evaluation.read(evaluation.glif_path(self.root, master, donor)))


class FixtureCases(Cases, unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = fixture.write_project(Path(self.temp.name) / 'font')

    def tearDown(self):
        self.temp.cleanup()

    def test_the_bold_task_hides_only_the_masters_after_the_first(self):
        [case] = evaluation.cases('bold', self.root)
        self.assertEqual((case['changed'], case['scored']), (['Bold'], ['Bold']))
        [case] = evaluation.cases('redraw', self.root)
        self.assertEqual(case['changed'], ['Regular', 'Bold'])

    def test_a_scored_copy_of_the_sources_matches_itself(self):
        # Without Runebender the design column is empty, which keeps the test
        # independent of the Runebender binary.
        with (tempfile.TemporaryDirectory() as temp, fixture.working_directory(self.root),
              mock.patch.object(check_design, 'find_runebender', return_value=None)):
            run = Path(temp) / 'run'
            with contextlib.redirect_stdout(io.StringIO()):
                evaluation.prepare('repair', run, self.root)
                (run / 'sources/Test-Bold.ufo/glyphs/square.glif').write_text(
                    (self.root / 'sources/Test-Bold.ufo/glyphs/square.glif').read_text())
                evaluation.score(run, self.root)
            rows = {r['master']: r for r in
                    json.loads((run / 'scores.json').read_text())['rows']}
            self.assertEqual(rows['Bold']['iou'], 1.0)
            self.assertLess(rows['Regular']['iou'], 1.0)
            self.assertTrue(all(r['compatible'] for r in rows.values()))


@unittest.skipUnless(os.environ.get('FONTGARDEN_TEST_PROJECT'),
                     'set FONTGARDEN_TEST_PROJECT to a font project to run these')
class ProjectCases(Cases, unittest.TestCase):
    """The same checks on a real project, for example Virtua Grotesk."""
    def setUp(self):
        self.root = Path(os.environ['FONTGARDEN_TEST_PROJECT'])


if __name__ == '__main__':
    unittest.main()
