#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-2.0-or-later
"""Export the pinned Hugeicons Free Stroke Rounded source snapshot."""

import argparse
import hashlib
import json
import subprocess
import sys
from pathlib import Path
from xml.etree import ElementTree as ET

SOURCE_COMMIT = "b05885affafa498def32b7ead86b86df01f03dbf"
UPSTREAM_REVISION = "bf880d758a69ab69edb278f8b529579fac54e5df"
SOURCE_MANIFEST_SHA256 = "d1e809bd0bd18066e105dabaee397bcdfaea559355876adf6795d2659142be3e"
SOURCE_LICENSE_SHA256 = "1658d8213209df7b9b86dfc05d724ede48d00dbc27abc15976ec7adec9601cde"
SOURCE_EXCLUSIONS_SHA256 = "2e20bf837c67a5d2dfae4151dd6acf36095d1ddd6a5e6562f292c932ccc6f642"
EXPECTED_ICONS = 6064
SVG_NS = "http://www.w3.org/2000/svg"
ET.register_namespace("", SVG_NS)


def sha256(data):
    return hashlib.sha256(data).hexdigest()


def committed_exporter_revision(exporter_path=None):
    exporter_path = Path(exporter_path or __file__).resolve(strict=True)
    repo_root = exporter_path.parent.parent
    relative_path = exporter_path.relative_to(repo_root).as_posix()
    if relative_path != "tools/export_hugeicons.py":
        raise ValueError("unexpected exporter path")
    revision = subprocess.check_output(
        ["git", "-C", str(repo_root), "rev-parse", "HEAD"], text=True
    ).strip()
    if len(revision) != 40 or any(c not in "0123456789abcdef" for c in revision):
        raise ValueError("exporter revision is not an immutable Git commit")
    committed_bytes = subprocess.check_output(
        ["git", "-C", str(repo_root), "show", f"{revision}:{relative_path}"]
    )
    if exporter_path.read_bytes() != committed_bytes:
        raise ValueError("exporter bytes differ from the recorded Git commit")
    return revision


def normalize_svg(raw, slug):
    """Remove currentColor only; preserve geometry and fill-rule values."""
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
        if set(child.attrib) not in ({"fill", "d"}, {"fill", "fill-rule", "d"}):
            raise ValueError(f"unsupported path attributes in {slug}")
        if child.attrib["fill"] != "currentColor":
            raise ValueError(f"unsupported path fill in {slug}")
        fill_rule = child.attrib.get("fill-rule", "nonzero")
        if fill_rule not in ("nonzero", "evenodd"):
            raise ValueError(f"unsupported path fill-rule in {slug}")
        if not child.attrib["d"].strip() or list(child) or child.text and child.text.strip() or child.tail and child.tail.strip():
            raise ValueError(f"unsupported path geometry in {slug}")
        attrs = {"d": child.attrib["d"]}
        if "fill-rule" in child.attrib:
            attrs["fill-rule"] = fill_rule
        ET.SubElement(out_root, f"{{{SVG_NS}}}path", attrs)
    return ET.tostring(out_root, encoding="utf-8", xml_declaration=False)


def export(source, output):
    source = Path(source)
    if source.is_symlink():
        raise ValueError("source must not be a symlink")
    source = source.resolve(strict=True)
    output = Path(output)
    if output.exists() or output.is_symlink():
        raise ValueError("output directory must not exist")
    manifest_bytes = (source / "manifest.json").read_bytes()
    license_bytes = (source / "LICENSE").read_bytes()
    exclusions_bytes = (source / "exclusions.json").read_bytes()
    if sha256(manifest_bytes) != SOURCE_MANIFEST_SHA256:
        raise ValueError("pinned Hugeicons source manifest hash mismatch")
    if sha256(license_bytes) != SOURCE_LICENSE_SHA256:
        raise ValueError("pinned Hugeicons MIT license hash mismatch")
    if sha256(exclusions_bytes) != SOURCE_EXCLUSIONS_SHA256:
        raise ValueError("pinned Hugeicons exclusions hash mismatch")
    source_manifest = json.loads(manifest_bytes)
    exclusions = json.loads(exclusions_bytes)
    if (source_manifest["source"]["revision"] != UPSTREAM_REVISION
            or source_manifest["source"]["name"] != "@hugeicons/core-free-icons"
            or source_manifest["version"] != "4.3.5"
            or source_manifest["variants"] != [{"slug": "stroke-rounded", "label": "Stroke Rounded", "coreCompatible": True, "defaultEnabled": False, "iconCount": EXPECTED_ICONS}]):
        raise ValueError("unexpected pinned Hugeicons source identity")
    if len(source_manifest["icons"]) != EXPECTED_ICONS or exclusions["includedIconCount"] != EXPECTED_ICONS:
        raise ValueError("unexpected pinned Hugeicons icon count")
    if exclusions.get("excludedIconCount") != 3 or len(exclusions.get("exclusions", [])) != 3:
        raise ValueError("unexpected pinned Hugeicons exclusions")

    filenames = sorted((source / "stroke-rounded").glob("*.svg"))
    if len(filenames) != EXPECTED_ICONS or any(path.is_symlink() for path in filenames):
        raise ValueError("pinned Hugeicons asset set is incomplete or unsafe")
    by_slug = {record["id"].removeprefix("hugeicons/stroke-rounded/"): record for record in source_manifest["icons"]}
    if len(by_slug) != EXPECTED_ICONS or {path.stem for path in filenames} != set(by_slug):
        raise ValueError("pinned Hugeicons asset and manifest identities differ")

    revision = committed_exporter_revision()
    output.mkdir(parents=True)
    (output / "icons").mkdir()
    (output / "licenses").mkdir()
    try:
        (output / "licenses/LICENSE.txt").write_bytes(license_bytes)
        icons = []
        for path in filenames:
            slug = path.stem
            record = by_slug[slug]
            if (record["id"] != f"hugeicons/stroke-rounded/{slug}"
                    or record["coreIconName"] != f"hugeicons/{slug}-stroke-rounded"
                    or record["variant"] != "stroke-rounded"):
                raise ValueError(f"pinned Hugeicons identity mismatch: {slug}")
            raw = path.read_bytes()
            if sha256(raw) != record["sha256"]:
                raise ValueError(f"pinned Hugeicons input SVG hash mismatch: {slug}")
            payload = normalize_svg(raw, slug)
            relative = f"icons/{slug}.svg"
            (output / relative).write_bytes(payload)
            icons.append({
                "id": slug,
                "core_icon_name": record["coreIconName"].removeprefix("hugeicons/"),
                "label": record["label"],
                "keywords": record["keywords"],
                "path": relative,
                "sha256": sha256(payload),
                "source_icon_id": record["id"],
            })
        package_manifest = {
            "schema_version": 1,
            "library_id": "hugeicons",
            "style_id": "stroke-rounded",
            "release_version": "1.0.0",
            "upstream": {"name": "@hugeicons/core-free-icons", "revision": UPSTREAM_REVISION},
            "source_snapshot": {"name": "Aculect Icon Library PR 55", "revision": SOURCE_COMMIT},
            "conversion": {"tool": "aculect-icon-libraries/tools/export_hugeicons.py", "revision": revision},
            "license": {"path": "licenses/LICENSE.txt", "sha256": sha256(license_bytes)},
            "icons": icons,
        }
        (output / "manifest.json").write_text(json.dumps(package_manifest, ensure_ascii=True, indent=2) + "\n", encoding="utf-8")
    except Exception:
        import shutil
        shutil.rmtree(output)
        raise
    return {"icons": len(icons), "excluded": 3, "upstream_revision": UPSTREAM_REVISION,
            "source_snapshot_revision": SOURCE_COMMIT, "conversion_revision": revision, "output": str(output)}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("source", type=Path, help="assets/icons/hugeicons extracted from the pinned PR 55 commit")
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
