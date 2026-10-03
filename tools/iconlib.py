#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-2.0-or-later
"""Build and validate bounded, data-only icon package archives."""

import argparse
import hashlib
import json
import math
import os
import re
import shutil
import stat
import sys
import tempfile
import zipfile
import zlib
from pathlib import Path
from xml.etree import ElementTree as ET

MAX_ARCHIVE = 32 * 1024 * 1024
MAX_MANIFEST = 8 * 1024 * 1024
MAX_DESCRIPTOR = 64 * 1024
MAX_LICENSE = 128 * 1024
MAX_SVG = 64 * 1024
MAX_TOTAL = 128 * 1024 * 1024
MAX_ICONS = 10000
CHUNK = 64 * 1024
ID_RE = re.compile(r"^[a-z0-9]+(?:-[a-z0-9]+)*$")
HEX_RE = re.compile(r"^[0-9a-f]{64}$")
REVISION_RE = re.compile(r"^(?:[0-9a-f]{40}|[0-9a-f]{64})$")
VERSION_RE = re.compile(r"^(0|[1-9][0-9]*)\.(0|[1-9][0-9]*)\.(0|[1-9][0-9]*)(?:-((?:0|[1-9][0-9]*|[0-9A-Za-z-]*[A-Za-z-][0-9A-Za-z-]*)(?:\.(?:0|[1-9][0-9]*|[0-9A-Za-z-]*[A-Za-z-][0-9A-Za-z-]*))*))?(?:\+[0-9A-Za-z-]+(?:\.[0-9A-Za-z-]+)*)?$")
SVG_NS = "http://www.w3.org/2000/svg"
PATH_NUMBER_RE = re.compile(r"[+-]?(?:[0-9]+(?:\.[0-9]*)?|\.[0-9]+)(?:[eE][+-]?[0-9]+)?")
PATH_ARITY = {"M": 2, "L": 2, "H": 1, "V": 1, "C": 6, "S": 4, "Q": 4, "T": 2, "A": 7, "Z": 0}


class PackageError(ValueError):
    pass


def fail(message):
    raise PackageError(message)


def sha256(data):
    return hashlib.sha256(data).hexdigest()


def version_key(version):
    """Return a SemVer ordering key for the supported numeric core and prerelease."""
    match = VERSION_RE.fullmatch(version) if isinstance(version, str) else None
    if not match:
        fail("invalid release_version")
    major, minor, patch, prerelease = match.groups()
    if prerelease is None:
        return (int(major), int(minor), int(patch), 1, ())
    identifiers = []
    for value in prerelease.split("."):
        if value.isdigit():
            if len(value) > 1 and value.startswith("0"):
                fail("invalid release_version prerelease")
            identifiers.append((0, int(value)))
        else:
            identifiers.append((1, value))
    return (int(major), int(minor), int(patch), 0, tuple(identifiers))


def check_update(previous_manifest, previous_sha256, candidate_manifest, candidate_sha256, retained_core_names=()):
    """Validate an update and return the full saved-name set, including removals."""
    for digest in (previous_sha256, candidate_sha256):
        if not isinstance(digest, str) or not HEX_RE.fullmatch(digest):
            fail("package digest must be SHA-256")
    identity = (previous_manifest.get("library_id"), previous_manifest.get("style_id"))
    candidate_identity = (candidate_manifest.get("library_id"), candidate_manifest.get("style_id"))
    if identity != candidate_identity:
        fail("update library/style identity mismatch")
    old_key = version_key(previous_manifest.get("release_version"))
    new_key = version_key(candidate_manifest.get("release_version"))
    if new_key < old_key:
        fail("release_version downgrade rejected")
    if new_key == old_key and previous_sha256 != candidate_sha256:
        fail("same release_version cannot identify different package bytes")
    previous_by_id = {icon["id"]: icon["core_icon_name"] for icon in previous_manifest["icons"]}
    candidate_by_id = {icon["id"]: icon["core_icon_name"] for icon in candidate_manifest["icons"]}
    if any(candidate_by_id.get(icon_id, name) != name for icon_id, name in previous_by_id.items()):
        fail("core_icon_name cannot change for an existing icon id")
    prior_names = {icon["core_icon_name"] for icon in previous_manifest["icons"]}
    candidate_names = {icon["core_icon_name"] for icon in candidate_manifest["icons"]}
    return sorted(set(retained_core_names) | prior_names | candidate_names)


def validate_library_styles(manifests):
    """Check identities across styles where saved names are prefixed by library only."""
    seen, styles = {}, set()
    for manifest in manifests:
        library_id = manifest.get("library_id")
        style_id = manifest.get("style_id")
        if (library_id, style_id) in styles:
            fail(f"duplicate library/style package: {library_id}/{style_id}")
        styles.add((library_id, style_id))
        for icon in manifest.get("icons", []):
            name = icon.get("core_icon_name")
            key = (library_id, name)
            if key in seen:
                fail(f"cross-style core_icon_name collision: {library_id}/{name} ({seen[key]}, {style_id})")
            seen[key] = style_id


def bounded_read(stream, limit):
    chunks = []
    total = 0
    while True:
        chunk = stream.read(min(CHUNK, limit + 1 - total))
        if not chunk:
            return b"".join(chunks)
        total += len(chunk)
        if total > limit:
            fail("member exceeds uncompressed byte limit")
        chunks.append(chunk)


def parse_json(data, label):
    def reject_duplicates(pairs):
        result = {}
        for key, value in pairs:
            if key in result:
                raise ValueError(f"duplicate JSON key: {key}")
            result[key] = value
        return result

    try:
        return json.loads(data.decode("utf-8"), object_pairs_hook=reject_duplicates)
    except (UnicodeDecodeError, ValueError) as exc:
        fail(f"{label} is not valid UTF-8 JSON: {exc}")


def validate_id(value, label):
    if not isinstance(value, str) or not ID_RE.fullmatch(value):
        fail(f"invalid {label}")


def validate_path(value, prefix):
    if not isinstance(value, str) or "\\" in value or value.startswith("/"):
        fail("invalid package path")
    parts = value.split("/")
    if not value or any(part in ("", ".", "..") for part in parts):
        fail("invalid package path")
    if not value.isascii() or any(not re.fullmatch(r"[A-Za-z0-9._-]+", part) for part in parts):
        fail("package paths must use ASCII-safe components")
    if not value.startswith(prefix) or value.endswith("/"):
        fail("package path outside allowed directory")
    return value


def validate_path_data(value):
    """Check bounded SVG 1.1 path syntax, not rendering or sanitizer semantics."""
    if not isinstance(value, str) or not value.strip() or len(value) > MAX_SVG:
        fail("invalid SVG path data")
    pos, first_command = 0, True

    def skip_space(offset):
        while offset < len(value) and value[offset] in " \t\r\n":
            offset += 1
        return offset

    while True:
        pos = skip_space(pos)
        if pos == len(value):
            return
        letter = value[pos]
        command = letter.upper()
        if letter not in "MmLlHhVvCcSsQqTtAaZz" or first_command and command != "M":
            fail("invalid SVG path command; path must start with moveto")
        first_command = False
        pos += 1
        arity = PATH_ARITY[command]
        if not arity:
            continue
        repeated = False
        while True:
            for index in range(arity):
                start = pos
                pos = skip_space(pos)
                if pos < len(value) and value[pos] == ",":
                    if index == 0 and not repeated:
                        fail("invalid SVG path separator")
                    pos = skip_space(pos + 1)
                if command == "A" and index == 3 and start == pos:
                    fail("SVG arc rotation and flag require a separator")
                if command == "A" and index in (3, 4):
                    if pos == len(value) or value[pos] not in "01":
                        fail("SVG arc flags must be 0 or 1")
                    pos += 1
                else:
                    number = PATH_NUMBER_RE.match(value, pos)
                    if not number or not math.isfinite(float(number.group())):
                        fail("invalid or incomplete SVG path parameters")
                    if command == "A" and index in (0, 1) and number.group()[0] in "+-":
                        fail("SVG arc radii must be unsigned")
                    pos = number.end()
            pos = skip_space(pos)
            if pos == len(value) or value[pos].isalpha():
                break
            repeated = True


def validate_svg(data):
    if len(data) > MAX_SVG:
        fail("SVG exceeds byte limit")
    try:
        text = data.decode("utf-8-sig")
    except UnicodeDecodeError:
        fail("SVG must be UTF-8")
    if "\x00" in text or any(ord(char) < 32 and char not in "\t\r\n" for char in text):
        fail("SVG contains forbidden control characters")
    declaration = re.match(r"^\s*<\?xml\s+([^?]*)\?>", text, re.IGNORECASE)
    if declaration:
        attrs = declaration.group(1)
        encoding = re.search(r"\bencoding\s*=\s*(['\"])(.*?)\1", attrs, re.IGNORECASE)
        if encoding and encoding.group(2).lower() not in ("utf-8", "utf8"):
            fail("SVG XML declaration must specify UTF-8")
        remainder = text[declaration.end():]
    else:
        remainder = text
    if "<?" in (remainder if declaration else text):
        fail("processing instructions are forbidden")
    upper = text.upper()
    if "<!DOCTYPE" in upper or "<!ENTITY" in upper:
        fail("DTD and entity declarations are forbidden")
    try:
        root = ET.fromstring(text)
    except ET.ParseError as exc:
        fail(f"invalid SVG XML: {exc}")
    if root.tag != f"{{{SVG_NS}}}svg":
        fail("SVG root must use the SVG namespace")
    allowed_root = {"viewBox", "width", "height"}
    if any(k not in allowed_root and k != "xmlns" for k in root.attrib):
        fail("unsupported SVG root attribute")
    if "viewBox" in root.attrib:
        values = root.attrib["viewBox"].replace(",", " ").split()
        if len(values) != 4 or any(not re.fullmatch(r"[-+]?(?:\d+(?:\.\d*)?|\.\d+)", item) for item in values):
            fail("invalid SVG viewBox")
        if float(values[2]) <= 0 or float(values[3]) <= 0:
            fail("SVG viewBox dimensions must be positive")
    for dimension in ("width", "height"):
        if dimension in root.attrib and not re.fullmatch(r"(?:\d+(?:\.\d*)?|\.\d+)(?:px)?", root.attrib[dimension]):
            fail("invalid SVG dimensions")
    count = 0
    for elem in root.iter():
        if (elem is root and elem.tag != f"{{{SVG_NS}}}svg") or (elem is not root and elem.tag != f"{{{SVG_NS}}}path") or elem.attrib.get("id"):
            fail("only id-less SVG path geometry is supported")
        if elem is root:
            if list(root).count(elem):
                fail("invalid SVG structure")
            continue
        count += 1
        if count > 1000 or elem.attrib.keys() - {"d", "fill-rule"}:
            fail("unsupported SVG element or attribute")
        if "d" not in elem.attrib or elem.attrib.get("fill-rule", "nonzero") not in ("nonzero", "evenodd"):
            fail("path requires geometry and a supported fill-rule")
        validate_path_data(elem.attrib["d"])
        if list(elem) or elem.text and elem.text.strip() or elem.tail and elem.tail.strip():
            fail("SVG paths cannot contain nested or textual content")
    if not count or root.text and root.text.strip() or root.tail and root.tail.strip():
        fail("SVG must contain path geometry only")


def validate_manifest(manifest, member_data, *, allow_test_fixture=False):
    if not isinstance(manifest, dict) or manifest.get("schema_version") != 1:
        fail("unsupported manifest schema")
    for field in ("library_id", "style_id"):
        validate_id(manifest.get(field), field)
    if not isinstance(manifest.get("release_version"), str) or not VERSION_RE.fullmatch(manifest["release_version"]):
        fail("invalid release_version")
    for field in ("upstream", "conversion"):
        record = manifest.get(field)
        if not isinstance(record, dict) or not all(isinstance(record.get(k), str) and record[k] for k in ("name" if field == "upstream" else "tool", "revision")):
            fail(f"invalid {field} identity")
        rev = record["revision"]
        synthetic = allow_test_fixture and manifest.get("test_fixture") is True and manifest.get("library_id") == "synthetic-test"
        if not (synthetic and rev.startswith("synthetic-test:")) and not REVISION_RE.fullmatch(rev):
            fail(f"{field} revision must be immutable")
    license_record = manifest.get("license")
    if not isinstance(license_record, dict):
        fail("license record required")
    license_path = validate_path(license_record.get("path"), "licenses/")
    if not license_path.lower().endswith(".txt"):
        fail("license member must use .txt extension")
    if not HEX_RE.fullmatch(str(license_record.get("sha256", ""))) or license_path not in member_data:
        fail("invalid or missing license member")
    if len(member_data[license_path]) > MAX_LICENSE:
        fail("license text exceeds byte limit")
    if sha256(member_data[license_path]) != license_record["sha256"]:
        fail("license hash mismatch")
    try:
        license_text = member_data[license_path].decode("utf-8")
    except UnicodeDecodeError:
        fail("license text must be UTF-8")
    if not license_text.strip() or any(ord(char) < 32 and char not in "\t\r\n" for char in license_text):
        fail("license text cannot be empty")
    icons = manifest.get("icons")
    if not isinstance(icons, list) or not 1 <= len(icons) <= MAX_ICONS:
        fail("icon count outside limits")
    ids, core_names, paths = set(), set(), set()
    for icon in icons:
        if not isinstance(icon, dict):
            fail("invalid icon record")
        for key in ("id", "core_icon_name"):
            validate_id(icon.get(key), key)
        if icon["core_icon_name"] in core_names:
            fail("duplicate core_icon_name")
        core_names.add(icon["core_icon_name"])
        if not isinstance(icon.get("label"), str) or not icon["label"].strip() or len(icon["label"]) > 120:
            fail("invalid icon label")
        keywords = icon.get("keywords")
        if not isinstance(keywords, list) or any(not isinstance(k, str) or len(k) > 40 for k in keywords):
            fail("invalid icon keywords")
        path = validate_path(icon.get("path"), "icons/")
        if not path.lower().endswith(".svg"):
            fail("icon member must use .svg extension")
        digest = icon.get("sha256", "")
        if icon["id"] in ids or path in paths or not HEX_RE.fullmatch(str(digest)):
            fail("duplicate icon identity/path or invalid hash")
        ids.add(icon["id"])
        paths.add(path)
        payload = member_data.get(path)
        if payload is None or sha256(payload) != digest:
            fail("missing icon or icon hash mismatch")
        validate_svg(payload)
    expected = {license_path, *paths}
    if set(member_data) != expected:
        fail("unexpected or undeclared package member")


def read_archive(path, *, allow_test_fixture=False):
    if path.stat().st_size > MAX_ARCHIVE:
        fail("archive exceeds compressed byte limit")
    try:
        archive = zipfile.ZipFile(path)
    except (zipfile.BadZipFile, OSError) as exc:
        fail(f"invalid ZIP archive: {exc}")
    with archive:
        infos = archive.infolist()
        if len(infos) > MAX_ICONS + 2:
            fail("too many archive entries")
        exact, folded, sizes = set(), set(), 0
        for info in infos:
            if info.orig_filename != info.filename:
                fail("ZIP member name contains NUL truncation")
            name = info.filename
            validate_path(name, "")
            if name in exact or name.casefold() in folded:
                fail("duplicate or case-colliding ZIP path")
            exact.add(name)
            folded.add(name.casefold())
            mode = info.external_attr >> 16
            if stat.S_ISLNK(mode) or (mode and not stat.S_ISREG(mode)) or mode & 0o111:
                fail("non-regular or executable ZIP member")
            if info.flag_bits & 0x1:
                fail("encrypted ZIP members are not supported")
            if name == "manifest.json":
                member_limit = MAX_MANIFEST
            elif name.startswith("licenses/") and name.lower().endswith(".txt"):
                member_limit = MAX_LICENSE
            elif name.startswith("icons/") and name.lower().endswith(".svg"):
                member_limit = MAX_SVG
            else:
                fail("unexpected package member type or path")
            if info.file_size > member_limit:
                fail("ZIP member exceeds type-specific byte limit")
            sizes += info.file_size
            if sizes > MAX_TOTAL:
                fail("archive exceeds expanded byte limit")
        data = {}
        for info in infos:
            if info.filename == "manifest.json":
                member_limit = MAX_MANIFEST
            elif info.filename.startswith("licenses/"):
                member_limit = MAX_LICENSE
            else:
                member_limit = MAX_SVG
            try:
                with archive.open(info) as stream:
                    raw = bounded_read(stream, member_limit)
            except (zipfile.BadZipFile, zlib.error, EOFError, OSError, NotImplementedError) as exc:
                fail(f"invalid ZIP member data: {exc}")
            if len(raw) != info.file_size:
                fail("ZIP entry size mismatch")
            data[info.filename] = raw
    if "manifest.json" not in data:
        fail("manifest.json is required")
    manifest_bytes = data.pop("manifest.json")
    if len(manifest_bytes) > MAX_MANIFEST:
        fail("manifest exceeds byte limit")
    manifest = parse_json(manifest_bytes, "manifest.json")
    validate_manifest(manifest, data, allow_test_fixture=allow_test_fixture)
    return manifest_bytes, manifest


def descriptor_for(path, *, allow_test_fixture=False):
    manifest_bytes, manifest = read_archive(path, allow_test_fixture=allow_test_fixture)
    return {
        "schema_version": 1,
        "library_id": manifest["library_id"],
        "style_id": manifest["style_id"],
        "release_version": manifest["release_version"],
        "package_sha256": sha256(path.read_bytes()),
        "manifest_sha256": sha256(manifest_bytes),
        "package_bytes": path.stat().st_size,
    }


def validate_trusted(path, descriptor_path, *, allow_test_fixture=False):
    with descriptor_path.open("rb") as stream:
        descriptor_bytes = bounded_read(stream, MAX_DESCRIPTOR)
    trusted = parse_json(descriptor_bytes, "trusted descriptor")
    if not isinstance(trusted, dict) or trusted.get("schema_version") != 1:
        fail("invalid trusted descriptor")
    actual = descriptor_for(path, allow_test_fixture=allow_test_fixture)
    for key in ("package_sha256", "manifest_sha256", "package_bytes", "library_id", "style_id", "release_version"):
        if trusted.get(key) != actual[key]:
            fail(f"trusted descriptor mismatch: {key}")
    return actual


def zip_info(path):
    info = zipfile.ZipInfo(path, (1980, 1, 1, 0, 0, 0))
    info.compress_type = zipfile.ZIP_DEFLATED
    info.create_system = 3
    info.external_attr = (stat.S_IFREG | 0o644) << 16
    return info


def source_member(root, member):
    if root.is_symlink() or not root.is_dir():
        fail("source directory must be a real directory")
    base = root.resolve(strict=True)
    candidate = root
    for part in member.split("/"):
        candidate = candidate / part
        if candidate.is_symlink():
            fail(f"symlink source path is not allowed: {member}")
    try:
        resolved = candidate.resolve(strict=True)
        resolved.relative_to(base)
    except (OSError, ValueError):
        fail(f"source path escapes or is missing: {member}")
    if not resolved.is_file():
        fail(f"source path is not a regular file: {member}")
    return resolved


def preflight_output(path):
    if path.is_symlink() or path.exists() and not path.is_file():
        fail("output destination must be a regular non-symlink file or absent")


def publish_outputs(outputs):
    """Roll back handled publication failures; the pair is not crash-atomic."""
    backups, published = {}, []
    keep_backups = False
    try:
        for _, destination in outputs:
            preflight_output(destination)
            backups[destination] = None
            if destination.exists():
                with tempfile.NamedTemporaryFile(dir=destination.parent, prefix=".iconlib-backup-", delete=False) as temp:
                    backups[destination] = Path(temp.name)
                shutil.copy2(destination, backups[destination])
        try:
            for temporary, destination in outputs:
                os.replace(temporary, destination)
                published.append(destination)
        except OSError as exc:
            for destination in reversed(published):
                try:
                    if backups[destination] is None:
                        destination.unlink()
                    else:
                        os.replace(backups[destination], destination)
                except OSError as rollback_exc:
                    keep_backups = True
                    recovery = ", ".join(str(p) for p in backups.values() if p is not None and p.exists())
                    fail(f"output publication failed ({exc}); rollback failed ({rollback_exc}); retained backups: {recovery}")
            fail(f"output publication failed; previous outputs restored: {exc}")
    finally:
        if not keep_backups:
            for backup in backups.values():
                if backup is not None:
                    backup.unlink(missing_ok=True)


def build(manifest_path, source_dir, archive_path, descriptor_path, *, allow_test_fixture=False):
    manifest_path, source_dir = Path(manifest_path), Path(source_dir)
    if manifest_path.is_symlink() or not manifest_path.is_file():
        fail("manifest must be a regular non-symlink file")
    with manifest_path.open("rb") as stream:
        manifest_bytes = bounded_read(stream, MAX_MANIFEST)
    manifest = parse_json(manifest_bytes, "manifest")
    if not isinstance(manifest, dict):
        fail("manifest root must be an object")
    license_record = manifest.get("license")
    icons = manifest.get("icons")
    if not isinstance(license_record, dict) or not isinstance(icons, list) or not 1 <= len(icons) <= MAX_ICONS:
        fail("manifest requires a license object and icons array")
    members = {"manifest.json": manifest_bytes}
    records = [(license_record, "licenses/")]
    records += [(record, "icons/") for record in icons]
    for record, prefix in records:
        if not isinstance(record, dict):
            fail("invalid manifest file record")
        member = validate_path(record.get("path"), prefix)
        if prefix == "licenses/" and not member.lower().endswith(".txt"):
            fail("license member must use .txt extension")
        if prefix == "icons/" and not member.lower().endswith(".svg"):
            fail("icon member must use .svg extension")
        source = source_member(source_dir, member)
        limit = MAX_LICENSE if prefix == "licenses/" else MAX_SVG
        with source.open("rb") as stream:
            members[member] = bounded_read(stream, limit)
    validate_manifest(manifest, {k: v for k, v in members.items() if k != "manifest.json"}, allow_test_fixture=allow_test_fixture)
    archive_path, descriptor_path = Path(archive_path), Path(descriptor_path)
    protected = {Path(manifest_path).resolve(), *(source_member(source_dir, p).resolve() for p in members if p != "manifest.json")}
    if archive_path.resolve() == descriptor_path.resolve() or archive_path.resolve() in protected or descriptor_path.resolve() in protected:
        fail("output paths must not overwrite inputs or each other")
    preflight_output(archive_path)
    preflight_output(descriptor_path)
    archive_path.parent.mkdir(parents=True, exist_ok=True)
    descriptor_path.parent.mkdir(parents=True, exist_ok=True)
    temp_archive = temp_descriptor = None
    try:
        with tempfile.NamedTemporaryFile(dir=archive_path.parent, prefix=".iconlib-", suffix=".zip", delete=False) as temp:
            temp_archive = Path(temp.name)
        with zipfile.ZipFile(temp_archive, "w", compression=zipfile.ZIP_DEFLATED, compresslevel=9) as archive:
            for name in sorted(members):
                archive.writestr(zip_info(name), members[name], compress_type=zipfile.ZIP_DEFLATED, compresslevel=9)
        if temp_archive.stat().st_size > MAX_ARCHIVE:
            fail("built archive exceeds compressed byte limit")
        descriptor = descriptor_for(temp_archive, allow_test_fixture=allow_test_fixture)
        with tempfile.NamedTemporaryFile(mode="w", encoding="utf-8", dir=descriptor_path.parent, prefix=".iconlib-", suffix=".json", delete=False) as temp:
            temp_descriptor = Path(temp.name)
            temp.write(json.dumps(descriptor, sort_keys=True, indent=2) + "\n")
        publish_outputs(((temp_archive, archive_path), (temp_descriptor, descriptor_path)))
        return descriptor
    finally:
        for temporary in (temp_archive, temp_descriptor):
            if temporary is not None:
                temporary.unlink(missing_ok=True)


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="command", required=True)
    b = sub.add_parser("build")
    b.add_argument("manifest", type=Path)
    b.add_argument("source_dir", type=Path)
    b.add_argument("archive", type=Path)
    b.add_argument("descriptor", type=Path)
    v = sub.add_parser("validate")
    v.add_argument("archive", type=Path)
    v.add_argument("--trusted-descriptor", type=Path, required=True)
    for command_parser in (b, v):
        command_parser.add_argument("--allow-test-fixture", action="store_true", help="test only: allow synthetic-test fixture revision labels")
    args = parser.parse_args(argv)
    try:
        result = build(args.manifest, args.source_dir, args.archive, args.descriptor, allow_test_fixture=args.allow_test_fixture) if args.command == "build" else validate_trusted(args.archive, args.trusted_descriptor, allow_test_fixture=args.allow_test_fixture)
        print(json.dumps(result, sort_keys=True, indent=2))
    except (PackageError, OSError, zipfile.LargeZipFile) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
