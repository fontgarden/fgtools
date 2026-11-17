"""Tests of fgtools/site.py."""
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace

from fgtools import site


class Site(unittest.TestCase):
    def test_the_site_holds_the_proof_and_the_media_without_build_files(self):
        root = Path(tempfile.mkdtemp())
        (root / 'output/proof').mkdir(parents=True)
        (root / 'output/proof/proof.pdf').write_bytes(b'%PDF')
        (root / 'output/media/images/poster').mkdir(parents=True)
        (root / 'output/media/.build').mkdir()
        (root / 'output/media/old-format').mkdir()
        (root / 'output/media/.build/media.rs').write_text('fn main() {}')
        (root / 'output/media/index.html').write_text('<html></html>')
        (root / 'output/media/images/poster/a_poster_square.png').write_bytes(b'png')
        (root / 'output/media/images/poster/a_poster_square_safe-areas.png').write_bytes(b'png')
        parts = site.build(SimpleNamespace(root=root, config={'familyName': 'A Font'}))
        self.assertEqual([path for path, _ in parts], ['proof.pdf', 'media/'])
        self.assertTrue((root / 'output/site/media/images/poster/a_poster_square.png').is_file())
        self.assertFalse((root / 'output/site/media/.build').exists())
        self.assertFalse((root / 'output/site/media/old-format').exists())
        self.assertFalse((root / 'output/site/media/images/poster/a_poster_square_safe-areas.png').exists())
        self.assertIn('A Font', (root / 'output/site/index.html').read_text())

    def test_a_project_without_renders_gets_an_index_only(self):
        root = Path(tempfile.mkdtemp())
        self.assertEqual(site.build(SimpleNamespace(root=root, config={})), [])
        self.assertTrue((root / 'output/site/index.html').is_file())


if __name__ == '__main__':
    unittest.main()
