import hashlib
import json
import stat
import tempfile
import unittest
import zipfile
from pathlib import Path

sys_path = Path(__file__).resolve().parents[1] / "tools"
# SPDX-License-Identifier: GPL-2.0-or-later
import sys
sys.path.insert(0, str(sys_path))
import iconlib

FIXTURE = Path(__file__).parent / "fixtures" / "synthetic"


def digest(data):
    return hashlib.sha256(data).hexdigest()


class PackageTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        self.archive = self.root / "package.zip"
        self.descriptor = self.root / "trusted.json"

    def tearDown(self):
        self.temp.cleanup()

    def build(self):
        return iconlib.build(FIXTURE / "manifest.json", FIXTURE, self.archive, self.descriptor)

    def repack(self, members):
        with zipfile.ZipFile(self.archive, "w") as zf:
            for name, content, mode in members:
                info = zipfile.ZipInfo(name, (2020, 1, 1, 0, 0, 0))
                if mode is not None:
                    info.create_system = 3
                    info.external_attr = mode << 16
                zf.writestr(info, content)

    def fixture_members(self):
        return [
            ("manifest.json", (FIXTURE / "manifest.json").read_bytes(), stat.S_IFREG | 0o644),
            ("licenses/LICENSE.txt", (FIXTURE / "licenses/LICENSE.txt").read_bytes(), stat.S_IFREG | 0o644),
            ("icons/test-square.svg", (FIXTURE / "icons/test-square.svg").read_bytes(), stat.S_IFREG | 0o644),
        ]

    def test_reproducible_archive_and_descriptor(self):
        first = self.build()
        first_bytes = self.archive.read_bytes()
        self.build()
        self.assertEqual(first_bytes, self.archive.read_bytes())
        self.assertEqual(first, json.loads(self.descriptor.read_text()))
        self.assertEqual(first["package_bytes"], len(first_bytes))
        self.assertEqual(first["package_sha256"], digest(first_bytes))

    def test_caller_supplied_trust_descriptor_required(self):
        self.build()
        iconlib.validate_trusted(self.archive, self.descriptor)
        trusted = json.loads(self.descriptor.read_text())
        trusted["package_sha256"] = "0" * 64
        self.descriptor.write_text(json.dumps(trusted))
        with self.assertRaisesRegex(iconlib.PackageError, "trusted descriptor mismatch"):
            iconlib.validate_trusted(self.archive, self.descriptor)

    def test_rejects_traversal_and_case_collision(self):
        members = self.fixture_members()
        members.append(("icons/../escape", b"x", stat.S_IFREG | 0o644))
        self.repack(members)
        with self.assertRaises(iconlib.PackageError):
            iconlib.read_archive(self.archive)
        members = self.fixture_members()
        members.append(("ICONS/test-square.svg", b"x", stat.S_IFREG | 0o644))
        self.repack(members)
        with self.assertRaisesRegex(iconlib.PackageError, "duplicate or case-colliding"):
            iconlib.read_archive(self.archive)
        members = self.fixture_members()
        members.append(members[-1])
        self.repack(members)
        with self.assertRaisesRegex(iconlib.PackageError, "duplicate or case-colliding"):
            iconlib.read_archive(self.archive)
        for unsafe_path in ("/icons/absolute.svg", r"icons\\backslash.svg"):
            self.repack(self.fixture_members() + [(unsafe_path, b"x", stat.S_IFREG | 0o644)])
            with self.assertRaises(iconlib.PackageError):
                iconlib.read_archive(self.archive)

    def test_rejects_symlink_executable_and_unexpected_members(self):
        for extra in [
            ("icons/link.svg", b"x", stat.S_IFLNK | 0o777),
            ("icons/run.svg", b"x", stat.S_IFREG | 0o755),
            ("notes.txt", b"x", stat.S_IFREG | 0o644),
        ]:
            with self.subTest(extra=extra[0]):
                self.repack(self.fixture_members() + [extra])
                with self.assertRaises(iconlib.PackageError):
                    iconlib.read_archive(self.archive)

    def test_rejects_unsafe_svg_documents(self):
        base = (FIXTURE / "icons/test-square.svg").read_bytes()
        for unsafe in [
            b'<!DOCTYPE svg [<!ENTITY x "y">]>' + base,
            base.replace(b"</svg>", b"<?xml-stylesheet href='https://example.invalid/x'?></svg>"),
            base.replace(b"<path", b"<script><path").replace(b"/></svg>", b"/></script></svg>"),
            base.replace(b"<path", b'<path onclick="x"'),
            base.replace(b"<path", b'<path href="https://example.invalid/x"'),
            base.replace(b"<path", b'<path style="fill:url(#x)"'),
        ]:
            with self.subTest(svg=unsafe[:60]):
                with self.assertRaises(iconlib.PackageError):
                    iconlib.validate_svg(unsafe)

    def test_bounded_read_stops_at_limit(self):
        class LargeStream:
            def read(self, amount):
                return b"x" * amount
        with self.assertRaisesRegex(iconlib.PackageError, "byte limit"):
            iconlib.bounded_read(LargeStream(), 1024)

    def test_fixture_bytes_match_manifest_hashes(self):
        manifest = json.loads((FIXTURE / "manifest.json").read_text())
        for record in [manifest["license"], *manifest["icons"]]:
            self.assertEqual(record["sha256"], digest((FIXTURE / record["path"]).read_bytes()))


if __name__ == "__main__":
    unittest.main()
