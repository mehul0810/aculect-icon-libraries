import unittest
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch
from xml.etree import ElementTree as ET

from tools.export_lucide import SVG_NS, committed_exporter_revision, normalize_svg


class LucideExportTest(unittest.TestCase):
    def test_removes_only_current_color_presentation_attribute(self):
        source = (
            f'<svg xmlns="{SVG_NS}" viewBox="0 0 24 24">'
            '<path fill="currentColor" d="M1 2L3 4Z"/>'
            '<path fill="currentColor" d="M4 5L6 7Z"/>'
            '</svg>'
        ).encode()
        result = normalize_svg(source, "test-mark")
        root = ET.fromstring(result)
        self.assertEqual(root.attrib, {"viewBox": "0 0 24 24"})
        self.assertEqual([child.attrib for child in root], [{"d": "M1 2L3 4Z"}, {"d": "M4 5L6 7Z"}])

    def test_rejects_unverified_presentation_and_geometry(self):
        cases = (
            f'<svg xmlns="{SVG_NS}" viewBox="0 0 24 24"><path fill="red" d="M1 2Z"/></svg>',
            f'<svg xmlns="{SVG_NS}" viewBox="0 0 24 24"><path fill="currentColor" clip-rule="evenodd" d="M1 2Z"/></svg>',
            f'<svg xmlns="{SVG_NS}" viewBox="0 0 24 24"><circle cx="1" cy="1" r="1"/></svg>',
            f'<svg xmlns="{SVG_NS}" viewBox="0 0 24 24"><path fill="currentColor" d="M1 2Z"><title>x</title></path></svg>',
        )
        for source in cases:
            with self.subTest(source=source), self.assertRaises(ValueError):
                normalize_svg(source.encode(), "unsupported-mark")

    def test_converter_revision_rejects_dirty_exporter_bytes(self):
        with TemporaryDirectory() as temp:
            exporter = Path(temp) / "tools/export_lucide.py"
            exporter.parent.mkdir()
            exporter.write_bytes(b"working-tree version")
            with patch("tools.export_lucide.subprocess.check_output", side_effect=["a" * 40, b"committed version"]):
                with self.assertRaisesRegex(ValueError, "differ from the recorded Git commit"):
                    committed_exporter_revision(exporter)

    def test_converter_revision_accepts_exact_committed_bytes(self):
        with TemporaryDirectory() as temp:
            exporter = Path(temp) / "tools/export_lucide.py"
            exporter.parent.mkdir()
            exporter.write_bytes(b"committed version")
            with patch("tools.export_lucide.subprocess.check_output", side_effect=["b" * 40, b"committed version"]):
                self.assertEqual(committed_exporter_revision(exporter), "b" * 40)


if __name__ == "__main__":
    unittest.main()
