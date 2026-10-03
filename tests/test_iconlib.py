# SPDX-License-Identifier: GPL-2.0-or-later
import hashlib
import json
import shutil
import stat
import tempfile
import unittest
import zipfile
from pathlib import Path

sys_path = Path(__file__).resolve().parents[1] / "tools"
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
            base.replace(b" viewBox=", b' fill="url(https://example.invalid/paint.svg#p)" viewBox='),
            b'<!DOCTYPE svg [<!ENTITY x "boom">]><svg xmlns="http://www.w3.org/2000/svg"><path d="&x;"/></svg>'.decode("utf-8").encode("utf-16le"),
            b'<?xml-stylesheet href="https://example.invalid/a.css"?><svg xmlns="http://www.w3.org/2000/svg"><path d="M0 0"/></svg>'.decode("utf-8").encode("utf-16le"),
        ]:
            with self.subTest(svg=unsafe[:60]):
                with self.assertRaises(iconlib.PackageError):
                    iconlib.validate_svg(unsafe)

    def test_license_php_path_rejected_by_builder_and_archive(self):
        manifest = json.loads((FIXTURE / "manifest.json").read_text())
        manifest["license"] = {"path": "licenses/run.php", "sha256": digest(b"<?php echo 123; ?>")}
        manifest_path = self.root / "manifest.json"
        manifest_path.write_text(json.dumps(manifest))
        (self.root / "licenses").mkdir()
        (self.root / "licenses" / "run.php").write_bytes(b"<?php echo 123; ?>")
        shutil.copytree(FIXTURE / "icons", self.root / "icons")
        with self.assertRaisesRegex(iconlib.PackageError, r"\.txt extension"):
            iconlib.build(manifest_path, self.root, self.archive, self.descriptor)

        data = self.fixture_members()
        attacker_manifest = json.loads(data[0][1])
        attacker_manifest["license"] = manifest["license"]
        self.repack([
            ("manifest.json", json.dumps(attacker_manifest).encode(), stat.S_IFREG | 0o644),
            ("licenses/run.php", b"<?php echo 123; ?>", stat.S_IFREG | 0o644),
            *data[2:],
        ])
        with self.assertRaisesRegex(iconlib.PackageError, "unexpected package member"):
            iconlib.read_archive(self.archive)

    def test_source_parent_symlink_rejected(self):
        source = self.root / "source"
        source.mkdir()
        shutil.copy(FIXTURE / "manifest.json", source / "manifest.json")
        shutil.copytree(FIXTURE / "licenses", source / "licenses")
        outside = self.root / "outside"
        shutil.copytree(FIXTURE / "icons", outside)
        (source / "icons").symlink_to(outside, target_is_directory=True)
        with self.assertRaisesRegex(iconlib.PackageError, "symlink source path"):
            iconlib.build(source / "manifest.json", source, self.archive, self.descriptor)
        self.assertFalse(self.archive.exists())

    def test_manifest_bad_shapes_and_duplicate_core_identity_fail_cleanly(self):
        for invalid in ([], {"schema_version": 1, "license": {}, "icons": [None]}):
            manifest_path = self.root / "bad.json"
            manifest_path.write_text(json.dumps(invalid))
            with self.assertRaises(iconlib.PackageError):
                iconlib.build(manifest_path, FIXTURE, self.archive, self.descriptor)

        manifest = json.loads((FIXTURE / "manifest.json").read_text())
        repeated = dict(manifest["icons"][0], id="second-icon", path="icons/second.svg")
        manifest["icons"].append(repeated)
        member_data = {
            "licenses/LICENSE.txt": (FIXTURE / "licenses/LICENSE.txt").read_bytes(),
            "icons/test-square.svg": (FIXTURE / "icons/test-square.svg").read_bytes(),
            "icons/second.svg": (FIXTURE / "icons/test-square.svg").read_bytes(),
        }
        with self.assertRaisesRegex(iconlib.PackageError, "duplicate core_icon_name"):
            iconlib.validate_manifest(manifest, member_data)

    def test_failed_build_does_not_replace_existing_output_or_input(self):
        self.archive.write_bytes(b"preserve existing output")
        before = self.archive.read_bytes()
        bad_manifest = self.root / "bad.json"
        bad_manifest.write_text("[]")
        with self.assertRaises(iconlib.PackageError):
            iconlib.build(bad_manifest, FIXTURE, self.archive, self.descriptor)
        self.assertEqual(before, self.archive.read_bytes())
        icon = FIXTURE / "icons" / "test-square.svg"
        with self.assertRaisesRegex(iconlib.PackageError, "overwrite inputs"):
            iconlib.build(FIXTURE / "manifest.json", FIXTURE, icon, self.descriptor)

    def test_manifest_capacity_is_larger_than_svg_capacity(self):
        source = self.root / "large-manifest-source"
        shutil.copytree(FIXTURE, source)
        manifest = json.loads((source / "manifest.json").read_text())
        manifest["metadata_padding"] = "x" * (2 * 1024 * 1024 + 1)
        (source / "manifest.json").write_text(json.dumps(manifest))
        iconlib.build(source / "manifest.json", source, self.archive, self.descriptor)
        self.assertGreater(self.archive.stat().st_size, 0)

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

    def test_moving_revisions_are_rejected(self):
        manifest = json.loads((FIXTURE / "manifest.json").read_text())
        manifest["test_fixture"] = False
        member_data = {
            "licenses/LICENSE.txt": (FIXTURE / "licenses/LICENSE.txt").read_bytes(),
            "icons/test-square.svg": (FIXTURE / "icons/test-square.svg").read_bytes(),
        }
        manifest["upstream"]["revision"] = "main"
        with self.assertRaisesRegex(iconlib.PackageError, "immutable"):
            iconlib.validate_manifest(manifest, member_data)


if __name__ == "__main__":
    unittest.main()
