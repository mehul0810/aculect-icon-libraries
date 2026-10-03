#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-2.0-or-later
"""Export the pinned PR 50 Lucide outline data as a strict package source tree."""

import argparse
import hashlib
import json
import subprocess
import sys
from pathlib import Path
from xml.etree import ElementTree as ET

UPSTREAM_COMMIT = "47ed6c90654254277297e4ec27a367cc777baca9"
UPSTREAM_REVISION = "3b9ea6d08707edc439f25a4c354cb0d6b8bee973"
MANIFEST_SHA256 = "0e1f90318f27f9d7ba0fc244add54a480830689dbf09498453b6519332adddc6"
LICENSE_SHA256 = "b495047bd93a9b06913511076f504daba17d5bbeb3e0650f3bb53a4220329c57"
EXPECTED_ICONS = 1848
SVG_NS = "http://www.w3.org/2000/svg"
ET.register_namespace("", SVG_NS)


def sha256(data):
    return hashlib.sha256(data).hexdigest()


def title(slug):
    return " ".join(word.capitalize() for word in slug.split("-"))


def normalize_svg(raw, slug):
    """Remove only the pinned source's per-path currentColor presentation attribute."""
    root = ET.fromstring(raw)
    if root.tag != f"{{{SVG_NS}}}svg" or set(root.attrib) != {"viewBox"}:
        raise ValueError(f"unsupported SVG root in {slug}")
    children = list(root)
    if not children or any(child.tag != f"{{{SVG_NS}}}path" for child in children):
        raise ValueError(f"unsupported SVG geometry in {slug}")
    if root.text and root.text.strip() or root.tail and root.tail.strip():
        raise ValueError(f"unexpected SVG text in {slug}")
    out_root = ET.Element(f"{{{SVG_NS}}}svg", {"viewBox": root.attrib["viewBox"]})
    for child in children:
        if set(child.attrib) != {"fill", "d"} or child.attrib["fill"] != "currentColor":
            raise ValueError(f"unsupported path attributes in {slug}")
        if not child.attrib["d"].strip() or list(child) or child.text and child.text.strip() or child.tail and child.tail.strip():
            raise ValueError(f"unsupported path geometry in {slug}")
        # In this geometry-only package, currentColor is presentation only. The receiving
        # renderer supplies icon color; SVG's implicit black fill is not package styling.
        ET.SubElement(out_root, f"{{{SVG_NS}}}path", {"d": child.attrib["d"]})
    return ET.tostring(out_root, encoding="utf-8", xml_declaration=False)


def export(source, output):
    source = Path(source)
    if source.is_symlink():
        raise ValueError("source must not be a symlink")
    source = source.resolve(strict=True)
    output = Path(output)
    if source.is_symlink() or not source.is_dir():
        raise ValueError("source must be a real directory")
    if output.exists() or output.is_symlink():
        raise ValueError("output directory must not exist")

    manifest_bytes = (source / "manifest.json").read_bytes()
    license_bytes = (source / "LICENSE").read_bytes()
    if sha256(manifest_bytes) != MANIFEST_SHA256:
        raise ValueError("pinned source manifest hash mismatch")
    if sha256(license_bytes) != LICENSE_SHA256:
        raise ValueError("pinned combined ISC/MIT license hash mismatch")
    source_manifest = json.loads(manifest_bytes)
    if source_manifest["source"]["revision"] != UPSTREAM_REVISION:
        raise ValueError("upstream Lucide revision mismatch")
    if source_manifest["version"] != "1.47.0" or source_manifest["variants"][0]["iconCount"] != EXPECTED_ICONS:
        raise ValueError("unexpected pinned upstream version or count")

    entries = source_manifest["icons"]
    if len(entries) != EXPECTED_ICONS:
        raise ValueError("unexpected manifest icon count")
    filenames = sorted((source / "outline").glob("*.svg"))
    if len(filenames) != EXPECTED_ICONS or any(path.is_symlink() for path in filenames):
        raise ValueError("pinned outline asset set is incomplete or unsafe")
    by_slug = {entry["id"].removeprefix("lucide/outline/"): entry for entry in entries}
    if len(by_slug) != EXPECTED_ICONS or {path.stem for path in filenames} != set(by_slug):
        raise ValueError("pinned asset and manifest icon identities differ")

    exporter_root = Path(__file__).resolve().parent.parent
    revision = subprocess.check_output(
        ["git", "-C", str(exporter_root), "rev-parse", "HEAD"], text=True
    ).strip()
    if len(revision) != 40 or any(c not in "0123456789abcdef" for c in revision):
        raise ValueError("exporter revision is not an immutable Git commit")

    output.mkdir(parents=True)
    (output / "icons").mkdir()
    (output / "licenses").mkdir()
    try:
        (output / "licenses/LICENSE.txt").write_bytes(license_bytes)
        icons = []
        for path in filenames:
            slug = path.stem
            record = by_slug[slug]
            if record["id"] != f"lucide/outline/{slug}" or record["coreIconName"] != f"lucide/{slug}-outline" or record["variant"] != "outline":
                raise ValueError(f"pinned core identity mismatch: {slug}")
            raw = path.read_bytes()
            if sha256(raw) != record["sha256"]:
                raise ValueError(f"pinned input SVG hash mismatch: {slug}")
            payload = normalize_svg(raw, slug)
            relative = f"icons/{slug}.svg"
            (output / relative).write_bytes(payload)
            core_name = record["coreIconName"].removeprefix("lucide/")
            icons.append({
                "id": slug,
                "core_icon_name": core_name,
                "label": record["label"],
                "keywords": record["keywords"],
                "path": relative,
                "sha256": sha256(payload),
                "source_icon_id": record["id"],
            })

        license_path = "licenses/LICENSE.txt"
        package_manifest = {
            "schema_version": 1,
            "library_id": "lucide",
            "style_id": "outline",
            "release_version": "1.0.0",
            "upstream": {"name": "lucide-icons/lucide", "revision": UPSTREAM_REVISION},
            "source_snapshot": {"name": "Aculect Icon Library PR 50", "revision": UPSTREAM_COMMIT},
            "conversion": {"tool": "aculect-icon-libraries/tools/export_lucide.py", "revision": revision},
            "license": {"path": license_path, "sha256": sha256(license_bytes)},
            "icons": icons,
        }
        (output / "manifest.json").write_text(json.dumps(package_manifest, ensure_ascii=True, indent=2) + "\n", encoding="utf-8")
    except Exception:
        import shutil
        shutil.rmtree(output)
        raise
    return {"icons": len(icons), "upstream_revision": UPSTREAM_COMMIT, "conversion_revision": revision, "output": str(output)}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("source", type=Path, help="assets/icons/lucide extracted from the pinned PR 50 commit")
    parser.add_argument("output", type=Path, help="new, absent package source directory")
    args = parser.parse_args()
    try:
        print(json.dumps(export(args.source, args.output), sort_keys=True))
    except (OSError, ValueError, KeyError, ET.ParseError, subprocess.CalledProcessError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
