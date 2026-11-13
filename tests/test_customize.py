"""Tests of fontgarden/customize.py."""
import subprocess
import tempfile
import unittest
from pathlib import Path

from fontgarden import customize


class Customize(unittest.TestCase):
    def test_the_placeholders_are_replaced_in_files_and_names(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            ufo = root / 'sources/FontGardenTemplate-Regular.ufo'
            ufo.mkdir(parents=True)
            (ufo / 'fontinfo.plist').write_text('Font Garden Template FontGardenTemplate-Regular')
            (root / 'sources/config.yaml').write_text('sources:\n  - FontGardenTemplate-Regular.ufo\n')
            (root / 'README.md').write_text(
                'https://github.com/fontgarden/font-project-template ofl/fontgardentemplate '
                'Designer Name <designer@example.com>')
            subprocess.run(['git', 'init', '-q'], cwd=root, check=True)
            subprocess.run(['git', 'add', '-A'], cwd=root, check=True)
            pairs = customize.replacements('My Face', 'Ada Example', 'ada@example.org')
            customize.customize(root, pairs)
            new = root / 'sources/MyFace-Regular.ufo'
            self.assertEqual((new / 'fontinfo.plist').read_text(), 'My Face MyFace-Regular')
            self.assertIn('MyFace-Regular.ufo', (root / 'sources/config.yaml').read_text())
            self.assertEqual((root / 'README.md').read_text(),
                             'https://github.com/fontgarden/my-face ofl/myface '
                             'Ada Example <ada@example.org>')
            self.assertEqual(customize.customize(root, pairs), [])


if __name__ == '__main__':
    unittest.main()
