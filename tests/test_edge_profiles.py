import unittest

from fgtools.edge_profiles import edge_profile


class TestEdgeProfiles(unittest.TestCase):
    def test_a_crossing_ends_the_stem_instead_of_measuring_the_bar_tips(self):
        cross = 'M40 0H60V40H100V60H60V100H40V60H0V40H40Z'
        rows = edge_profile(cross, (50, 10), (50, 90), 64)['samples']
        self.assertTrue(all(r['width'] == 20 for r in rows[:-1]))
        self.assertEqual(rows[-1]['point'], [50, 40])
        self.assertNotIn('width', rows[-1])
        self.assertNotEqual(rows[-1]['status'], 'paired')

    def test_measurement_stops_at_a_counter(self):
        ring = 'M0 0H100V100H0Z M20 20V80H80V20Z'
        rows = edge_profile(ring, (10, 30), (10, 60), 64)['samples']
        self.assertTrue(all(abs(r['width'] - 20) < 1e-7 for r in rows))
        empty = edge_profile(ring, (50, 50), (50, 60), 64)['samples']
        self.assertEqual(empty[0]['status'], 'outside-ink')
