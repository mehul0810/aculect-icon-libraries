# SPDX-License-Identifier: GPL-2.0-or-later
import hashlib
import json
import shutil
import stat
import struct
import subprocess
import tempfile
import unittest
import zipfile
from unittest import mock
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
        return iconlib.build(FIXTURE / "manifest.json", FIXTURE, self.archive, self.descriptor, allow_test_fixture=True)

    def repack(self, members, compression=zipfile.ZIP_STORED):
        with zipfile.ZipFile(self.archive, "w") as zf:
            for name, content, mode in members:
                info = zipfile.ZipInfo(name, (2020, 1, 1, 0, 0, 0))
                if mode is not None:
                    info.create_system = 3
                    info.external_attr = mode << 16
                zf.writestr(info, content, compress_type=compression)

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

    def test_versioned_fixture_build_and_update_policy(self):
        output = self.root / "versioned"
        denied = subprocess.run(
            [sys.executable, str(sys_path / "build_versioned_fixtures.py"), str(output)],
            capture_output=True, text=True,
        )
        self.assertEqual(denied.returncode, 2)
        self.assertIn("--allow-test-fixtures is required", denied.stderr)
        result = subprocess.run(
            [sys.executable, str(sys_path / "build_versioned_fixtures.py"), str(output), "--allow-test-fixtures"],
            capture_output=True, text=True,
        )
        self.assertEqual(result.returncode, 0, result.stderr)
        manifests, descriptors = {}, {}
        for name in ("outline-1.0.0", "outline-1.1.0", "solid-1.0.0"):
            package = output / f"{name}.zip"
            descriptor_path = output / f"{name}.descriptor.json"
            descriptors[name] = json.loads(descriptor_path.read_text())
            manifests[name] = iconlib.read_archive(package, allow_test_fixture=True)[1]
            iconlib.validate_trusted(package, descriptor_path, allow_test_fixture=True)
        first_hashes = {name: item["package_sha256"] for name, item in descriptors.items()}
        rerun = subprocess.run(
            [sys.executable, str(sys_path / "build_versioned_fixtures.py"), str(output), "--allow-test-fixtures"],
            capture_output=True, text=True,
        )
        self.assertEqual(rerun.returncode, 0, rerun.stderr)
        self.assertEqual({name: json.loads((output / f"{name}.descriptor.json").read_text())["package_sha256"] for name in first_hashes}, first_hashes)
        old, new = manifests["outline-1.0.0"], manifests["outline-1.1.0"]
        self.assertEqual((old["library_id"], old["style_id"], old["release_version"]), ("synthetic-test", "outline", "1.0.0"))
        self.assertEqual((new["library_id"], new["style_id"], new["release_version"]), ("synthetic-test", "outline", "1.1.0"))
        self.assertEqual(manifests["solid-1.0.0"]["style_id"], "solid")
        self.assertNotEqual(descriptors["outline-1.0.0"]["package_sha256"], descriptors["outline-1.1.0"]["package_sha256"])
        retained = iconlib.check_update(old, descriptors["outline-1.0.0"]["package_sha256"], new, descriptors["outline-1.1.0"]["package_sha256"])
        self.assertEqual(sorted(row["core_icon_name"] for row in retained), ["new-mark", "retired-mark", "test-square"])
        iconlib.validate_library_styles((new, manifests["solid-1.0.0"]), retained)
        colliding_style = json.loads(json.dumps(manifests["solid-1.0.0"]))
        colliding_style["icons"][0]["core_icon_name"] = "test-square"
        with self.assertRaisesRegex(iconlib.PackageError, "cross-style core_icon_name collision"):
            iconlib.validate_library_styles((new, colliding_style))

    def test_version_policy_rejects_digest_reuse_and_downgrade(self):
        manifest = json.loads((FIXTURE / "manifest.json").read_text())
        digest_1, digest_2 = "1" * 64, "2" * 64
        with self.assertRaisesRegex(iconlib.PackageError, "same release_version"):
            iconlib.check_update(manifest, digest_1, manifest, digest_2)
        older = json.loads(json.dumps(manifest))
        older["release_version"] = "0.9.9"
        newer = json.loads(json.dumps(manifest))
        newer["release_version"] = "1.0.0-rc.1"
        with self.assertRaisesRegex(iconlib.PackageError, "downgrade"):
            iconlib.check_update(manifest, digest_1, newer, digest_1)
        with self.assertRaisesRegex(iconlib.PackageError, "downgrade"):
            iconlib.check_update(manifest, digest_1, older, digest_1)
        renamed = json.loads(json.dumps(manifest))
        renamed["release_version"] = "1.1.0"
        renamed["icons"][0]["core_icon_name"] = "changed-saved-name"
        with self.assertRaisesRegex(iconlib.PackageError, "cannot change"):
            iconlib.check_update(manifest, digest_1, renamed, digest_2)
        self.assertLess(iconlib.version_key("1.0.0-alpha.1"), iconlib.version_key("1.0.0-alpha.beta"))
        self.assertLess(iconlib.version_key("1.0.0-rc.1"), iconlib.version_key("1.0.0"))
        with self.assertRaisesRegex(iconlib.PackageError, "invalid release_version"):
            iconlib.version_key("1.0.0-alpha..beta")

    def test_identity_ownership_survives_removal_and_multiple_updates(self):
        original = json.loads((FIXTURE / "manifest.json").read_text())
        removed = json.loads(json.dumps(original))
        removed["release_version"] = "1.1.0"
        removed["icons"] = removed["icons"][1:]
        history = iconlib.check_update(original, "1" * 64, removed, "2" * 64)
        restored = json.loads(json.dumps(original))
        restored["release_version"] = "1.2.0"
        self.assertEqual(history, iconlib.check_update(removed, "2" * 64, restored, "3" * 64, history))
        for key, value in (("id", "unrelated-replacement"), ("core_icon_name", "renamed-square")):
            candidate = json.loads(json.dumps(restored))
            candidate["icons"][0][key] = value
            with self.subTest(key=key), self.assertRaises(iconlib.PackageError):
                iconlib.check_update(removed, "2" * 64, candidate, "3" * 64, history)
        moved = json.loads(json.dumps(restored))
        moved["style_id"] = "another-style"
        moved["icons"] = moved["icons"][:1]
        with self.assertRaises(iconlib.PackageError):
            iconlib.validate_library_styles((removed, moved), history)

    def test_update_rejects_reverse_identity_reassignment(self):
        original = json.loads((FIXTURE / "manifest.json").read_text())
        candidate = json.loads(json.dumps(original))
        candidate["release_version"] = "1.1.0"
        candidate["icons"][0]["id"] = "unrelated-replacement"
        with self.assertRaisesRegex(iconlib.PackageError, "reassignment"):
            iconlib.check_update(original, "1" * 64, candidate, "2" * 64)

    def test_version_numeric_bounds_fail_cleanly(self):
        for version in ("9" * 5000 + ".0.0", "1.0.0-" + "9" * 5000, "1000000000.0.0", "1.0.0-1000000000", "1.0.0+" + "x" * 60):
            with self.subTest(length=len(version)), self.assertRaisesRegex(iconlib.PackageError, "invalid release_version"):
                iconlib.version_key(version)
        self.assertGreater(iconlib.version_key("999999999.0.0"), iconlib.version_key("1.0.0"))

    def test_caller_supplied_trust_descriptor_required(self):
        self.build()
        iconlib.validate_trusted(self.archive, self.descriptor, allow_test_fixture=True)
        trusted = json.loads(self.descriptor.read_text())
        trusted["package_sha256"] = "0" * 64
        self.descriptor.write_text(json.dumps(trusted))
        with self.assertRaisesRegex(iconlib.PackageError, "trusted descriptor mismatch"):
            iconlib.validate_trusted(self.archive, self.descriptor, allow_test_fixture=True)

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
            b'<svg xmlns="http://www.w3.org/2000/svg"><svg d="M0 0h1v1z"/></svg>',
            b'<!DOCTYPE svg [<!ENTITY x "boom">]><svg xmlns="http://www.w3.org/2000/svg"><path d="&x;"/></svg>'.decode("utf-8").encode("utf-16le"),
            b'<?xml-stylesheet href="https://example.invalid/a.css"?><svg xmlns="http://www.w3.org/2000/svg"><path d="M0 0"/></svg>'.decode("utf-8").encode("utf-16le"),
        ]:
            with self.subTest(svg=unsafe[:60]):
                with self.assertRaises(iconlib.PackageError):
                    iconlib.validate_svg(unsafe)

    def test_zip_member_name_nul_truncation_is_rejected(self):
        members = self.fixture_members()
        members[-1] = (members[-1][0] + "X", members[-1][1], members[-1][2])
        self.repack(members)
        package = self.archive.read_bytes()
        old_name = b"icons/test-square.svgX"
        self.assertEqual(package.count(old_name), 2)
        self.archive.write_bytes(package.replace(old_name, b"icons/test-square.svg\x00"))
        with self.assertRaisesRegex(iconlib.PackageError, "NUL truncation"):
            iconlib.read_archive(self.archive)

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
            "icons/retired-mark.svg": (FIXTURE / "icons/retired-mark.svg").read_bytes(),
            "icons/second.svg": (FIXTURE / "icons/test-square.svg").read_bytes(),
        }
        with self.assertRaisesRegex(iconlib.PackageError, "duplicate core_icon_name"):
            iconlib.validate_manifest(manifest, member_data, allow_test_fixture=True)

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
            iconlib.build(FIXTURE / "manifest.json", FIXTURE, icon, self.descriptor, allow_test_fixture=True)

    def test_manifest_capacity_is_larger_than_svg_capacity(self):
        source = self.root / "large-manifest-source"
        shutil.copytree(FIXTURE, source)
        manifest = json.loads((source / "manifest.json").read_text())
        manifest["metadata_padding"] = "x" * (2 * 1024 * 1024 + 1)
        (source / "manifest.json").write_text(json.dumps(manifest))
        iconlib.build(source / "manifest.json", source, self.archive, self.descriptor, allow_test_fixture=True)
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

    def test_synthetic_provenance_requires_explicit_test_mode(self):
        with self.assertRaisesRegex(iconlib.PackageError, "immutable"):
            iconlib.build(FIXTURE / "manifest.json", FIXTURE, self.archive, self.descriptor)
        self.assertFalse(self.archive.exists())
        self.build()
        trusted = json.loads(self.descriptor.read_text())
        trusted["test_fixture"] = True
        self.descriptor.write_text(json.dumps(trusted))
        for validate in (
            lambda: iconlib.read_archive(self.archive),
            lambda: iconlib.descriptor_for(self.archive),
            lambda: iconlib.validate_trusted(self.archive, self.descriptor),
        ):
            with self.assertRaisesRegex(iconlib.PackageError, "immutable"):
                validate()
        iconlib.validate_trusted(self.archive, self.descriptor, allow_test_fixture=True)

    def test_fixture_mode_does_not_allow_other_moving_provenance(self):
        manifest = json.loads((FIXTURE / "manifest.json").read_text())
        data = {name: content for name, content, _ in self.fixture_members()[1:]}
        for field in ("upstream", "conversion"):
            with self.subTest(field=field):
                modified = json.loads(json.dumps(manifest))
                modified[field]["revision"] = "main"
                with self.assertRaisesRegex(iconlib.PackageError, "immutable"):
                    iconlib.validate_manifest(modified, data, allow_test_fixture=True)
        manifest["library_id"] = "other-library"
        with self.assertRaisesRegex(iconlib.PackageError, "immutable"):
            iconlib.validate_manifest(manifest, data, allow_test_fixture=True)

    def test_immutable_provenance_is_accepted_without_fixture_mode(self):
        manifest = json.loads((FIXTURE / "manifest.json").read_text())
        manifest.pop("test_fixture")
        manifest["upstream"]["revision"] = "a" * 40
        manifest["conversion"]["revision"] = "b" * 64
        manifest_path = self.root / "manifest.json"
        manifest_path.write_text(json.dumps(manifest))
        iconlib.build(manifest_path, FIXTURE, self.archive, self.descriptor)
        iconlib.validate_trusted(self.archive, self.descriptor)

    def test_valid_path_commands_and_parameter_forms(self):
        paths = [
            "M0 0", "m0,0 1,1 2-3z", "M.6.5L1e2-2E-1Z",
            "M0 0H1 2h-1V3 4v-2L5 6l-1-1z",
            "M0 0C1 2 3 4 5 6 7 8 9 10 11 12c1 2 3 4 5 6S1 2 3 4s1 2 3 4",
            "M0 0Q1 2 3 4q1 2 3 4T5 6t-1-2",
            "M0 0A10 20 30 0 1 40 50a1,2,-30,10-4-5Z",
            "M0 0A1 2 0 0110 20 3 4 5 0 0 6 7zM1 2L3 4",
        ]
        for path in paths:
            with self.subTest(path=path):
                iconlib.validate_svg(f'<svg xmlns="http://www.w3.org/2000/svg"><path d="{path}"/></svg>'.encode())

    def test_malformed_path_geometry_is_rejected(self):
        paths = [
            "", "   ", "definitely not SVG path data", "L0 0", "M", "M0", "M0 0L",
            "M0 0L1", "M0 0C1 2 3 4 5", "M0 0Q1 2 3", "M0 0S1 2 3",
            "M0 0T1", "M0 0A1 2 3 0 1 4", "M0 0A1 2 3 2 1 4 5",
            "M0 0A1 2 3 0 -1 4 5", "M0 0A-1 2 3 0 1 4 5",
            "M0 0A1 2 3.0.0 1 4 5", "M0 0A1 2 3 0.0 1 4 5",
            "M0 0R1 2", "M0 0Z1 2", "M,0 0", "M0,,0", "M0 0,",
            "M0 0,L1 2", "M0 0L1e 2", "M0 0L1e999 2", "M0 0LNaN 2",
            "M0 0L1;2", "M0 0L1 2 garbage", "M0 0L1\u00a02", "M0 0\u017f1 2 3 4",
        ]
        for path in paths:
            with self.subTest(path=path):
                with self.assertRaises(iconlib.PackageError):
                    iconlib.validate_svg(f'<svg xmlns="http://www.w3.org/2000/svg"><path d="{path}"/></svg>'.encode())

    def test_malformed_path_is_rejected_by_build_and_archive_validation(self):
        source = self.root / "bad-geometry"
        shutil.copytree(FIXTURE, source)
        payload = b'<svg xmlns="http://www.w3.org/2000/svg"><path d="definitely not SVG path data"/></svg>'
        (source / "icons/test-square.svg").write_bytes(payload)
        manifest = json.loads((source / "manifest.json").read_text())
        manifest["icons"][0]["sha256"] = digest(payload)
        manifest_bytes = json.dumps(manifest).encode()
        (source / "manifest.json").write_bytes(manifest_bytes)
        with self.assertRaisesRegex(iconlib.PackageError, "SVG path"):
            iconlib.build(source / "manifest.json", source, self.archive, self.descriptor, allow_test_fixture=True)
        members = self.fixture_members()
        members[0] = ("manifest.json", manifest_bytes, members[0][2])
        members[2] = ("icons/test-square.svg", payload, members[2][2])
        self.repack(members)
        with self.assertRaisesRegex(iconlib.PackageError, "SVG path"):
            iconlib.read_archive(self.archive, allow_test_fixture=True)

    def test_second_output_failure_restores_existing_or_absent_outputs(self):
        replace = iconlib.os.replace
        for existing in (False, True):
            with self.subTest(existing=existing):
                if existing:
                    self.archive.write_bytes(b"old archive")
                    self.descriptor.write_bytes(b"old descriptor")

                def fail_descriptor(source, destination):
                    if destination == self.descriptor:
                        raise OSError("injected descriptor publication failure")
                    return replace(source, destination)

                with mock.patch.object(iconlib.os, "replace", side_effect=fail_descriptor):
                    with self.assertRaisesRegex(iconlib.PackageError, "previous outputs restored"):
                        self.build()
                if existing:
                    self.assertEqual(self.archive.read_bytes(), b"old archive")
                    self.assertEqual(self.descriptor.read_bytes(), b"old descriptor")
                else:
                    self.assertFalse(self.archive.exists())
                    self.assertFalse(self.descriptor.exists())
                self.assertFalse(list(self.root.glob(".iconlib-*")))

    def test_rollback_failure_reports_and_retains_recovery_backups(self):
        self.archive.write_bytes(b"old archive")
        self.descriptor.write_bytes(b"old descriptor")
        replace = iconlib.os.replace

        def fail_publication_and_rollback(source, destination):
            if destination == self.descriptor or source.name.startswith(".iconlib-backup-"):
                raise OSError("injected publication/rollback failure")
            return replace(source, destination)

        with mock.patch.object(iconlib.os, "replace", side_effect=fail_publication_and_rollback):
            with self.assertRaisesRegex(iconlib.PackageError, "rollback failed.*retained backups") as caught:
                self.build()
        backups = list(self.root.glob(".iconlib-backup-*"))
        self.assertEqual({p.read_bytes() for p in backups}, {b"old archive", b"old descriptor"})
        for backup in backups:
            self.assertIn(str(backup), str(caught.exception))
        self.assertEqual(self.descriptor.read_bytes(), b"old descriptor")

    def test_directory_destination_is_rejected_before_publication(self):
        for directory in (self.archive, self.descriptor):
            with self.subTest(directory=directory.name):
                other = self.descriptor if directory == self.archive else self.archive
                directory.mkdir()
                other.write_bytes(b"preserve output")
                with self.assertRaisesRegex(iconlib.PackageError, "output destination"):
                    self.build()
                self.assertTrue(directory.is_dir())
                self.assertEqual(other.read_bytes(), b"preserve output")
                self.assertFalse(list(self.root.glob(".iconlib-*")))
                directory.rmdir()
                other.unlink()

    def test_corrupt_crc_and_deflate_members_fail_cleanly(self):
        for compression in (zipfile.ZIP_STORED, zipfile.ZIP_DEFLATED):
            with self.subTest(compression=compression):
                self.build()
                self.repack(self.fixture_members(), compression=compression)
                with zipfile.ZipFile(self.archive) as zf:
                    info = zf.getinfo("icons/test-square.svg")
                data = bytearray(self.archive.read_bytes())
                name_length, extra_length = struct.unpack_from("<HH", data, info.header_offset + 26)
                offset = info.header_offset + 30 + name_length + extra_length
                if compression == zipfile.ZIP_DEFLATED:
                    data[offset] = (data[offset] & 0xf8) | 0x07  # Reserved DEFLATE block type.
                else:
                    data[offset] ^= 1
                self.archive.write_bytes(data)
                with self.assertRaisesRegex(iconlib.PackageError, "invalid ZIP member data"):
                    iconlib.read_archive(self.archive, allow_test_fixture=True)
                result = subprocess.run([sys.executable, str(sys_path / "iconlib.py"), "validate", str(self.archive), "--trusted-descriptor", str(self.descriptor), "--allow-test-fixture"], capture_output=True, text=True)
                self.assertEqual(result.returncode, 1)
                self.assertEqual(result.stdout, "")
                self.assertTrue(result.stderr.startswith("error: invalid ZIP member data:"))
                self.assertNotIn("Traceback", result.stderr)

    def test_cli_fixture_opt_in_is_required_for_build_and_validate(self):
        commands = [
            ["build", str(FIXTURE / "manifest.json"), str(FIXTURE), str(self.archive), str(self.descriptor)],
            ["validate", str(self.archive), "--trusted-descriptor", str(self.descriptor)],
        ]
        for command in commands:
            result = subprocess.run([sys.executable, str(sys_path / "iconlib.py"), *command], capture_output=True, text=True)
            self.assertEqual(result.returncode, 1)
            self.assertIn("revision must be immutable", result.stderr)
            result = subprocess.run([sys.executable, str(sys_path / "iconlib.py"), *command, "--allow-test-fixture"], capture_output=True, text=True)
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertEqual(json.loads(result.stdout)["library_id"], "synthetic-test")


if __name__ == "__main__":
    unittest.main()
