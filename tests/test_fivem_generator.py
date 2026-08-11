import tempfile
import unittest
from pathlib import Path

from app.generators.fivem import build_manifest, inspect_resource


class FiveMGeneratorTests(unittest.TestCase):
    def test_resource_without_nui_is_scanned(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            (root / 'client').mkdir()
            (root / 'server').mkdir()
            (root / 'client' / 'main.lua').write_text('print(1)', encoding='utf-8')
            (root / 'server' / 'main.lua').write_text('print(2)', encoding='utf-8')

            info = inspect_resource(root)
            manifest = build_manifest(info)

            self.assertFalse(info['nui'])
            self.assertIn("'client/main.lua'", manifest)
            self.assertIn("'server/main.lua'", manifest)


if __name__ == '__main__':
    unittest.main()
