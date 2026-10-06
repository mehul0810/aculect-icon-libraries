#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-2.0-or-later
"""Build a deterministic bounded sample from a validated data-only package.

Output stays outside the production catalog until publication is authorized.
"""

import argparse
import json
import zipfile
from pathlib import Path

import iconlib

MAX_SAMPLES = 12
MAX_PREVIEW = 256 * 1024


def build_preview(archive, descriptor, output, *, allow_test_fixture=False):
    archive, descriptor, output = map(Path, (archive, descriptor, output))
    if output.exists() or output.is_symlink():
        raise iconlib.PackageError("preview destination must be absent")
    verified = iconlib.validate_trusted(archive, descriptor, allow_test_fixture=allow_test_fixture)
    with zipfile.ZipFile(archive) as package:
        manifest = json.loads(package.read("manifest.json"))
        samples = []
        for icon in sorted(manifest["icons"], key=lambda item: item["id"])[:MAX_SAMPLES]:
            svg = package.read(icon["path"])
            iconlib.validate_svg(svg)
            samples.append({"label": icon["label"], "svg": svg.decode("utf-8")})
        license_text = package.read(manifest["license"]["path"]).decode("utf-8")
    data = {"schema_version": 1, **{key: verified[key] for key in ("library_id", "style_id", "release_version")}, "license": license_text, "samples": samples}
    raw = (json.dumps(data, ensure_ascii=False, sort_keys=True, separators=(",", ":")) + "\n").encode("utf-8")
    if len(raw) > MAX_PREVIEW:
        raise iconlib.PackageError("preview exceeds byte limit")
    with output.open("xb") as stream:
        stream.write(raw)
    return {**verified, "preview_sha256": iconlib.sha256(raw), "preview_bytes": len(raw)}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("archive", type=Path)
    parser.add_argument("descriptor", type=Path)
    parser.add_argument("output", type=Path)
    args = parser.parse_args()
    print(json.dumps(build_preview(args.archive, args.descriptor, args.output), sort_keys=True))


if __name__ == "__main__":
    main()
