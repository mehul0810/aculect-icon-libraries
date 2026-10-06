import json
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "tools"))
import iconlib
from build_preview import build_preview


class PreviewTest(unittest.TestCase):
    def test_preview_reproducible_and_does_not_modify_package(self):
        fixture = Path(__file__).parent / "fixtures" / "synthetic"
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            archive, descriptor = root / "package.zip", root / "descriptor.json"
            iconlib.build(fixture / "manifest.json", fixture, archive, descriptor, allow_test_fixture=True)
            original = archive.read_bytes()
            first = build_preview(archive, descriptor, root / "first.json", allow_test_fixture=True)
            second = build_preview(archive, descriptor, root / "second.json", allow_test_fixture=True)
            self.assertEqual(first, second)
            self.assertEqual((root / "first.json").read_bytes(), (root / "second.json").read_bytes())
            self.assertEqual(original, archive.read_bytes())
            self.assertLessEqual(len(json.loads((root / "first.json").read_text())["samples"]), 12)
            self.assertEqual(json.loads((root / "first.json").read_text())["license"], (fixture / "licenses" / "LICENSE.txt").read_text())
            self.assertEqual(first["preview_bytes"], (root / "first.json").stat().st_size)
            with self.assertRaises(iconlib.PackageError):
                build_preview(archive, descriptor, root / "first.json", allow_test_fixture=True)
            with self.assertRaises(iconlib.PackageError):
                build_preview(archive, descriptor, root / "production.json")

    def test_corrupt_package_cannot_produce_preview(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            (root / "broken.zip").write_bytes(b"invalid")
            (root / "descriptor.json").write_text("{}")
            with self.assertRaises((iconlib.PackageError, ValueError)):
                build_preview(root / "broken.zip", root / "descriptor.json", root / "preview.json")
            self.assertFalse((root / "preview.json").exists())
