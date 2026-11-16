"""Tests of the harness command lines and the task brief of the benchmark."""
import json
import unittest

from fgtools import benchmark
from fgtools.evaluate_drafting import brief


class HarnessCommands(unittest.TestCase):
    def test_the_prompt_and_model_are_filled_in(self):
        parts = benchmark.command('claude', 'opus', 600)
        self.assertIn(benchmark.PROMPT, parts)
        self.assertEqual(parts[parts.index('--model') + 1], 'opus')

    def test_the_model_arguments_are_left_out_without_a_model(self):
        for harness in benchmark.HARNESSES:
            with self.subTest(harness=harness):
                parts = benchmark.command(harness, None, 600)
                self.assertFalse([p for p in parts if 'model' in p], parts)
                self.assertFalse([p for p in parts if '{' in p], parts)

    def test_no_harness_turns_its_permission_checks_off(self):
        for harness, spec in benchmark.HARNESSES.items():
            with self.subTest(harness=harness):
                line = ' '.join(spec['command'])
                for flag in ('dangerously', 'yolo', 'bypass', 'danger-full-access'):
                    self.assertNotIn(flag, line)

    def test_the_cost_is_read_from_the_json_output(self):
        self.assertEqual(benchmark.cost('claude', json.dumps({'total_cost_usd': 1.25})), 1.25)
        self.assertIsNone(benchmark.cost('claude', 'not json'))
        self.assertIsNone(benchmark.cost('omp', '{}'))


class Brief(unittest.TestCase):
    def test_the_brief_names_each_glyph_its_masters_and_donors(self):
        text = brief('relatives', [{'glyph': 'h', 'changed': ['Regular', 'Bold'], 'donors': ['n']}])
        self.assertIn('- h: Regular, Bold (from n)', text)
        self.assertIn('Work only in this directory', text)


if __name__ == '__main__':
    unittest.main()
