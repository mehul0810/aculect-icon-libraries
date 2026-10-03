import unittest
from xml.etree import ElementTree as ET

from tools.export_lucide import SVG_NS, normalize_svg


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


if __name__ == "__main__":
    unittest.main()
