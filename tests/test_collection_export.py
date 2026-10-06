import sys
import unittest
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/"tools"))
from export_collection import normalize_svg, transform_path, polygon_path


class CollectionExportTest(unittest.TestCase):
    def test_polygon_closes_exact_vertices(self):
        self.assertEqual("M 1 2 L 3 4 5 6 Z",polygon_path("1,2 3,4 5,6"))
        for points in ("1,2 3", "1,2 NaN,4 5,6", "1,2 3,4 5,6<script>"):
            with self.assertRaises(ValueError): polygon_path(points)

    def test_orthogonal_transform_preserves_points_and_arc_orientation(self):
        self.assertEqual("M 2 1 L 2 3 L 0 3 Z",transform_path("M 1 2 H 3 V 4 Z","rotate(90 2 2)"))
        self.assertEqual("M 2 1 A 0.5 0.5 0 0 0 3 2 Z",transform_path("M 1 2 A .5 .5 0 0 1 2 3 Z","matrix(0 1 1 0 0 0)"))
        for transform in ("scale(2)","rotate(45 0 0)","matrix(0 1 1 0 0 0) url(x)"):
            with self.assertRaises(ValueError): transform_path("M 0 0 L 1 1",transform)
        with self.assertRaises(ValueError): transform_path("M 0 0 A 1 2 0 0 1 3 4","rotate(90 0 0)")

    def test_only_invisible_paths_and_non_clipping_presentation_are_removed(self):
        svg = b'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" fill="currentColor"><path fill="none" d="M 0 0 H 24 V 24 Z"/><path fill="black" clip-rule="evenodd" fill-rule="evenodd" d="M 1 1 H 2 V 2 Z"/></svg>'
        output = normalize_svg(svg)
        self.assertNotIn(b'fill="',output)
        self.assertNotIn(b'clip-rule',output)
        self.assertIn(b'fill-rule="evenodd"',output)
        self.assertNotIn(b'M 0 0',output)

    def test_unsafe_or_unfaithful_artwork_fails_closed(self):
        cases = ('<path stroke="black" d="M 0 0 L 1 1"/>','<path opacity=".5" d="M 0 0 L 1 1"/>','<path fill="#123456" d="M 0 0 L 1 1"/>','<g><path d="M 0 0 L 1 1"/></g>','<script>alert(1)</script>','<path onclick="alert(1)" d="M 0 0 L 1 1"/>','<path fill="none" stroke="black" d="M 0 0 L 1 1"/>')
        for child in cases:
            with self.subTest(child=child),self.assertRaises(ValueError):
                normalize_svg(('<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24">'+child+'</svg>').encode())
