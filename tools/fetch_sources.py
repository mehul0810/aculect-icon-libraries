#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-2.0-or-later
"""Fetch immutable source data separately from the frozen package converter."""
import json
import sys
import tarfile
import tempfile
from pathlib import Path
import iconlib
from build_catalog import ROOT, download
import export_lucide
import export_hugeicons


def snapshot(archive, destination, libraries):
    total = 0
    with tarfile.open(archive) as source:
        for member in source:
            parts = member.name.split("/")
            if len(parts) < 5 or parts[1:3] != ["assets","icons"] or parts[3] not in libraries:
                continue
            relative = "/".join(parts[3:])
            if not (relative.endswith(".svg") or relative.endswith("/manifest.json") or relative.endswith("/LICENSE") or relative.endswith("/exclusions.json")):
                continue
            if not member.isfile() or any(p in ("",".","..") for p in parts) or "\\" in member.name:
                raise ValueError("unsafe source member")
            # Exclusion metadata is JSON, not an SVG; its source snapshot can
            # legitimately exceed the per-artwork 64 KiB limit.
            limit = iconlib.MAX_MANIFEST if relative.endswith(".json") else iconlib.MAX_LICENSE if relative.endswith("LICENSE") else iconlib.MAX_SVG
            if member.size > limit: raise ValueError("source member exceeds bound")
            total += member.size
            if total > 256*1024*1024: raise ValueError("expanded source snapshot exceeds bound")
            target = destination/relative
            target.parent.mkdir(parents=True,exist_ok=True)
            with target.open("xb") as output:
                output.write(iconlib.bounded_read(source.extractfile(member),limit))


def fetch(destination):
    destination = Path(destination)
    if destination.exists() or destination.is_symlink(): raise ValueError("source destination must be absent")
    destination.mkdir(parents=True)
    plan = json.loads((ROOT/"data/source-pins.json").read_bytes())
    refs = {}
    for pin in plan["collections"]: refs.setdefault(pin["snapshot_revision"],[]).append(pin["library_id"])
    refs[export_lucide.UPSTREAM_COMMIT] = ["lucide"]
    refs[export_hugeicons.SOURCE_COMMIT] = ["hugeicons"]
    with tempfile.TemporaryDirectory(prefix="aculect-source-download-") as temporary:
        for revision,libraries in refs.items():
            archive = Path(temporary)/(revision+".tgz")
            download("https://codeload.github.com/mehul0810/aculect-icon-library/tar.gz/"+revision,archive)
            snapshot(archive,destination,libraries)
    print(json.dumps({"snapshots":len(refs),"collections":sum(map(len,refs.values()))}))


if __name__ == "__main__": fetch(sys.argv[1])
