#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-2.0-or-later
"""Build and validate bounded, data-only icon package archives."""

import argparse
import hashlib
import json
import os
import re
import stat
import sys
import zipfile
from pathlib import Path, PurePosixPath
from xml.etree import ElementTree as ET

MAX_ARCHIVE = 32 * 1024 * 1024
MAX_MEMBER = 2 * 1024 * 1024
MAX_TOTAL = 128 * 1024 * 1024
MAX_MANIFEST = 8 * 1024 * 1024
MAX_LICENSE = 128 * 1024
MAX_SVG = 64 * 1024
MAX_ICONS = 10000
CHUNK = 64 * 1024
ID_RE = re.compile(r"^[a-z0-9]+(?:-[a-z0-9]+)*$")
HEX_RE = re.compile(r"^[0-9a-f]{64}$")
VERSION_RE = re.compile(r"^(0|[1-9][0-9]*)\.(0|[1-9][0-9]*)\.(0|[1-9][0-9]*)(?:-[0-9A-Za-z.-]+)?(?:\+[0-9A-Za-z.-]+)?$")
SVG_NS = "http://www.w3.org/2000/svg"
SVG_TAGS = {f"{{{SVG_NS}}}svg", f"{{{SVG_NS}}}path"}


class PackageError(ValueError):
    pass


def fail(message):
    raise PackageError(message)


def sha256(data):
    return hashlib.sha256(data).hexdigest()


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
    try:
        return json.loads(data.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        fail(f"{label} is not valid UTF-8 JSON: {exc}")


def validate_id(value, label):
    if not isinstance(value, str) or not ID_RE.fullmatch(value):
        fail(f"invalid {label}")


def validate_path(value, prefix):
    if not isinstance(value, str) or "\\" in value or value.startswith("/"):
        fail("invalid package path")
    parts = value.split("/")
    path = PurePosixPath(value)
    if not path.parts or any(part in ("", ".", "..") for part in parts):
        fail("invalid package path")
    if not value.isascii() or any(not re.fullmatch(r"[A-Za-z0-9._-]+", part) for part in path.parts):
        fail("package paths must use ASCII-safe components")
    if not value.startswith(prefix) or value.endswith("/"):
        fail("package path outside allowed directory")
    return value


def validate_svg(data):
    if len(data) > MAX_SVG:
        fail("SVG exceeds byte limit")
    try:
        data.decode("utf-8")
    except UnicodeDecodeError:
        fail("SVG must be UTF-8")
    if data.startswith(b"<?"):
        decl_end = data.find(b"?>")
        if decl_end < 0 or not data[:decl_end + 2].lower().startswith(b"<?xml"):
            fail("processing instructions are forbidden")
        remainder = data[decl_end + 2:]
    else:
        remainder = data
    if b"<?" in remainder:
        fail("processing instructions are forbidden")
    upper = data.upper()
    if b"<!DOCTYPE" in upper or b"<!ENTITY" in upper:
        fail("DTD and entity declarations are forbidden")
    try:
        root = ET.fromstring(data)
    except ET.ParseError as exc:
        fail(f"invalid SVG XML: {exc}")
    if root.tag != f"{{{SVG_NS}}}svg":
        fail("SVG root must use the SVG namespace")
    allowed_root = {"viewBox", "width", "height", "fill", "fill-rule"}
    if any(k not in allowed_root and k != "xmlns" for k in root.attrib):
        fail("unsupported SVG root attribute")
    count = 0
    for elem in root.iter():
        if elem.tag not in SVG_TAGS or elem.attrib.get("id"):
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
        if list(elem) or elem.text and elem.text.strip() or elem.tail and elem.tail.strip():
            fail("SVG paths cannot contain nested or textual content")
    if not count or root.text and root.text.strip() or root.tail and root.tail.strip():
        fail("SVG must contain path geometry only")


def validate_manifest(manifest, member_data):
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
        if rev.lower() in ("main", "master", "head", "latest", "develop") or len(rev) < 7:
            fail(f"{field} revision must be immutable")
    license_record = manifest.get("license")
    if not isinstance(license_record, dict):
        fail("license record required")
    license_path = validate_path(license_record.get("path"), "licenses/")
    if not HEX_RE.fullmatch(str(license_record.get("sha256", ""))) or license_path not in member_data:
        fail("invalid or missing license member")
    if len(member_data[license_path]) > MAX_LICENSE:
        fail("license text exceeds byte limit")
    if sha256(member_data[license_path]) != license_record["sha256"]:
        fail("license hash mismatch")
    if not member_data[license_path].strip():
        fail("license text cannot be empty")
    icons = manifest.get("icons")
    if not isinstance(icons, list) or not 1 <= len(icons) <= MAX_ICONS:
        fail("icon count outside limits")
    ids, paths = set(), set()
    for icon in icons:
        if not isinstance(icon, dict):
            fail("invalid icon record")
        for key in ("id", "core_icon_name"):
            validate_id(icon.get(key), key)
        if not isinstance(icon.get("label"), str) or not icon["label"].strip() or len(icon["label"]) > 120:
            fail("invalid icon label")
        keywords = icon.get("keywords")
        if not isinstance(keywords, list) or any(not isinstance(k, str) or len(k) > 40 for k in keywords):
            fail("invalid icon keywords")
        path = validate_path(icon.get("path"), "icons/")
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


def read_archive(path):
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
            if info.file_size > MAX_MEMBER:
                fail("ZIP member exceeds uncompressed byte limit")
            sizes += info.file_size
            if sizes > MAX_TOTAL:
                fail("archive exceeds expanded byte limit")
        data = {}
        for info in infos:
            with archive.open(info) as stream:
                raw = bounded_read(stream, MAX_MEMBER)
            if len(raw) != info.file_size:
                fail("ZIP entry size mismatch")
            data[info.filename] = raw
    if "manifest.json" not in data:
        fail("manifest.json is required")
    manifest_bytes = data.pop("manifest.json")
    if len(manifest_bytes) > MAX_MANIFEST:
        fail("manifest exceeds byte limit")
    manifest = parse_json(manifest_bytes, "manifest.json")
    validate_manifest(manifest, data)
    return manifest_bytes, manifest


def descriptor_for(path):
    manifest_bytes, manifest = read_archive(path)
    return {
        "schema_version": 1,
        "library_id": manifest["library_id"],
        "style_id": manifest["style_id"],
        "release_version": manifest["release_version"],
        "package_sha256": sha256(path.read_bytes()),
        "manifest_sha256": sha256(manifest_bytes),
        "package_bytes": path.stat().st_size,
    }


def validate_trusted(path, descriptor_path):
    trusted = parse_json(descriptor_path.read_bytes(), "trusted descriptor")
    if not isinstance(trusted, dict) or trusted.get("schema_version") != 1:
        fail("invalid trusted descriptor")
    actual = descriptor_for(path)
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


def build(manifest_path, source_dir, archive_path, descriptor_path):
    with manifest_path.open("rb") as stream:
        manifest_bytes = bounded_read(stream, MAX_MANIFEST)
    manifest = parse_json(manifest_bytes, "manifest")
    members = {"manifest.json": manifest_bytes}
    license_record = manifest.get("license", {})
    records = [(license_record, "licenses/")]
    records += [(record, "icons/") for record in manifest.get("icons", []) if isinstance(record, dict)]
    for record, prefix in records:
        member = validate_path(record.get("path"), prefix)
        source = source_dir / member
        if not source.is_file() or source.is_symlink():
            fail(f"missing or unsafe source file: {member}")
        limit = MAX_LICENSE if prefix == "licenses/" else MAX_SVG
        with source.open("rb") as stream:
            members[member] = bounded_read(stream, limit)
    validate_manifest(manifest, {k: v for k, v in members.items() if k != "manifest.json"})
    archive_path.parent.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(archive_path, "w", compression=zipfile.ZIP_DEFLATED, compresslevel=9) as archive:
        for name in sorted(members):
            archive.writestr(zip_info(name), members[name], compress_type=zipfile.ZIP_DEFLATED, compresslevel=9)
    if archive_path.stat().st_size > MAX_ARCHIVE:
        fail("built archive exceeds compressed byte limit")
    descriptor = descriptor_for(archive_path)
    descriptor_path.write_text(json.dumps(descriptor, sort_keys=True, indent=2) + "\n", encoding="utf-8")
    return descriptor


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
    args = parser.parse_args(argv)
    try:
        result = build(args.manifest, args.source_dir, args.archive, args.descriptor) if args.command == "build" else validate_trusted(args.archive, args.trusted_descriptor)
        print(json.dumps(result, sort_keys=True, indent=2))
    except (PackageError, OSError, zipfile.LargeZipFile) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
