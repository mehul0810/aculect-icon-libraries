#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-2.0-or-later
"""Prepare all reviewed packs; never publish or run upstream software."""
import argparse
import hashlib
import json
import re
import shutil
import subprocess
import tarfile
import tempfile
import urllib.request
from pathlib import Path

import iconlib
import export_collection
import export_lucide
import export_hugeicons
from build_preview import build_preview

ROOT = Path(__file__).resolve().parents[1]
TOOLS = ("tools/build_catalog.py", "tools/export_collection.py", "tools/export_lucide.py", "tools/export_hugeicons.py", "tools/iconlib.py", "tools/build_preview.py", "data/source-pins.json", "data/fluent-exclusions.json")


def verify_converter(revision):
    if not re.fullmatch(r"[a-f0-9]{40}", revision): raise ValueError("immutable converter revision required")
    for relative in TOOLS:
        expected = subprocess.check_output(["git","-C",str(ROOT),"show",revision+":"+relative])
        if (ROOT/relative).read_bytes() != expected:
            raise ValueError("converter/source pins differ from recorded commit: "+relative)


def download(url, destination, limit=128*1024*1024):
    if not url.startswith(("https://codeload.github.com/mehul0810/aculect-icon-library/tar.gz/", "https://registry.npmjs.org/@fluentui/svg-icons/-/", "https://raw.githubusercontent.com/microsoft/fluentui-system-icons/")):
        raise ValueError("unreviewed source location")
    with urllib.request.urlopen(url,timeout=30) as response, destination.open("xb") as target:
        total = 0
        while True:
            chunk = response.read(65536)
            if not chunk: break
            total += len(chunk)
            if total > limit: raise ValueError("source exceeds download limit")
            target.write(chunk)


def snapshot(archive, destination, libraries):
    """Copy only bounded non-executable source data, never extract an archive."""
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
            limit = iconlib.MAX_MANIFEST if relative.endswith("manifest.json") else iconlib.MAX_LICENSE if relative.endswith("LICENSE") else iconlib.MAX_SVG
            if member.size > limit: raise ValueError("source member exceeds bound")
            total += member.size
            if total > 256*1024*1024: raise ValueError("source snapshot exceeds expanded bound")
            payload = iconlib.bounded_read(source.extractfile(member),limit)
            target = destination/relative
            target.parent.mkdir(parents=True,exist_ok=True)
            with target.open("xb") as output: output.write(payload)


def fluent(archive, license_bytes, notice_bytes, output, pin, style, revision):
    if iconlib.sha256(archive.read_bytes()) != pin["archive_sha256"]:
        raise ValueError("Fluent archive integrity mismatch")
    if iconlib.sha256(license_bytes) != pin["license_sha256"] or iconlib.sha256(notice_bytes) != pin["notice_sha256"]:
        raise ValueError("Fluent license/notice integrity mismatch")
    review = json.loads((ROOT/"data/fluent-exclusions.json").read_bytes())
    excluded = {r["path"]:r for r in review["exclusions"]}
    shape,size = style.split("-")
    icons,seen_excluded = [],set()
    output.mkdir(parents=True)
    (output/"icons").mkdir()
    (output/"licenses").mkdir()
    with tarfile.open(archive) as source:
        for member in source:
            match = re.fullmatch(r"package/icons/([^/]+)_"+size+"_"+shape+r"\.svg",member.name)
            if not match: continue
            if not member.isfile() or member.size > iconlib.MAX_SVG: raise ValueError("unsafe Fluent member")
            raw = iconlib.bounded_read(source.extractfile(member),iconlib.MAX_SVG)
            if member.name in excluded:
                if iconlib.sha256(raw) != excluded[member.name]["sha256"]: raise ValueError("exclusion hash mismatch")
                try: export_collection.normalize_svg(raw)
                except ValueError as exc:
                    if str(exc) != excluded[member.name]["reason"]: raise ValueError("exclusion reason changed")
                else: raise ValueError("stale exclusion")
                seen_excluded.add(member.name)
                continue
            slug = match[1].replace("_","-")
            name = slug+"-"+style
            iconlib.validate_id(name,"Fluent saved identity")
            payload = export_collection.normalize_svg(raw)
            path = "icons/"+name+".svg"
            with (output/path).open("xb") as target: target.write(payload)
            icons.append({"id":name,"core_icon_name":name,"label":" ".join(w.capitalize() for w in slug.split("-")),"keywords":slug.split("-"),"path":path,"sha256":iconlib.sha256(payload),"source_icon_id":member.name})
    expected = {p for p in excluded if re.fullmatch(r"package/icons/[^/]+_"+size+"_"+shape+r"\.svg",p)}
    if seen_excluded != expected or len(icons) != pin["styles"][style]: raise ValueError("Fluent reviewed count/exclusions mismatch")
    combined = license_bytes+b"\n\n--- Preserved upstream NOTICE ---\n\n"+notice_bytes
    (output/"licenses/LICENSE.txt").write_bytes(combined)
    manifest = {"schema_version":1,"library_id":"fluent-ui","style_id":style,"release_version":"1.0.0","upstream":{"name":"microsoft/fluentui-system-icons","revision":pin["upstream_revision"]},"conversion":{"tool":"aculect-icon-libraries/tools/build_catalog.py","revision":revision},"license":{"path":"licenses/LICENSE.txt","sha256":iconlib.sha256(combined)},"icons":sorted(icons,key=lambda i:i["id"])}
    (output/"manifest.json").write_text(json.dumps(manifest,ensure_ascii=True,indent=2)+"\n",encoding="utf-8")
    return manifest


def build(output, revision, plugin_source=None, fluent_archive=None, fluent_notices=None):
    verify_converter(revision)
    output = Path(output)
    if output.exists() or output.is_symlink(): raise ValueError("build destination must be absent")
    output.mkdir(parents=True)
    plan = json.loads((ROOT/"data/source-pins.json").read_bytes())
    descriptors,manifests = [],[]
    with tempfile.TemporaryDirectory(prefix="aculect-catalog-") as temporary:
        temporary = Path(temporary)
        sources = Path(plugin_source) if plugin_source else temporary/"sources"
        refs = {}
        for pin in plan["collections"]: refs.setdefault(pin["snapshot_revision"],[]).append(pin["library_id"])
        refs[export_lucide.UPSTREAM_COMMIT] = ["lucide"]
        refs[export_hugeicons.SOURCE_COMMIT] = ["hugeicons"]
        if not plugin_source:
            for ref,libs in refs.items():
                archive = temporary/(ref+".tgz")
                download("https://codeload.github.com/mehul0810/aculect-icon-library/tar.gz/"+ref,archive)
                snapshot(archive,sources,libs)
        def package(tree,manifest):
            manifests.append(manifest)
            tag = manifest["library_id"]+"-"+manifest["style_id"]+"-"+manifest["release_version"]
            archive,descriptor = output/(tag+".zip"),output/(tag+".descriptor.json")
            iconlib.build(tree/"manifest.json",tree,archive,descriptor)
            result = build_preview(archive,descriptor,output/(tag+".preview.json"))
            result.update({"icon_count":len(manifest["icons"]),"availability":"pending-publication"})
            descriptors.append(result)
        for pin in plan["collections"]:
            for style in sorted(pin["styles"]):
                tree = temporary/(pin["library_id"]+"-"+style)
                manifest = export_collection.export(sources/pin["library_id"],tree,pin,style,revision)
                package(tree,manifest)
        for module,library in ((export_lucide,"lucide"),(export_hugeicons,"hugeicons")):
            # This entry point first binds all converter bytes to revision.
            module.committed_exporter_revision = lambda: revision
            tree = temporary/library
            module.export(sources/library,tree)
            manifest = json.loads((tree/"manifest.json").read_bytes())
            # Earlier 1.0.0 candidate hashes remain immutable. New provenance
            # produces a new version rather than replacing those bytes.
            manifest["release_version"] = "1.0.1"
            manifest["conversion"] = {"tool":"aculect-icon-libraries/tools/build_catalog.py","revision":revision}
            (tree/"manifest.json").write_text(json.dumps(manifest,ensure_ascii=True,indent=2)+"\n",encoding="utf-8")
            package(tree,manifest)
        pin = plan["fluent"]
        archive = Path(fluent_archive) if fluent_archive else temporary/"fluent.tgz"
        if not fluent_archive: download(pin["archive_url"],archive)
        notices = {}
        for name in ("LICENSE","NOTICE"):
            target = Path(fluent_notices)/("fluent-"+name+".txt") if fluent_notices else temporary/name
            if not fluent_notices: download("https://raw.githubusercontent.com/microsoft/fluentui-system-icons/"+pin["upstream_revision"]+"/"+name,target,iconlib.MAX_LICENSE)
            notices[name] = target.read_bytes()
        for style in sorted(pin["styles"]):
            tree = temporary/("fluent-ui-"+style)
            manifest = fluent(archive,notices["LICENSE"],notices["NOTICE"],tree,pin,style,revision)
            package(tree,manifest)
        iconlib.validate_library_styles(manifests)
    descriptors.sort(key=lambda d:(d["library_id"],d["style_id"]))
    (output/"prepared-catalog.json").write_text(json.dumps({"schema_version":1,"libraries":descriptors},indent=2)+"\n",encoding="utf-8")
    print(json.dumps({"packages":len(descriptors),"icons":sum(d["icon_count"] for d in descriptors),"conversion_revision":revision}))


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("output",type=Path)
    parser.add_argument("--revision",required=True)
    parser.add_argument("--plugin-source",type=Path)
    parser.add_argument("--fluent-archive",type=Path)
    parser.add_argument("--fluent-notices",type=Path)
    args = parser.parse_args()
    build(args.output,args.revision,args.plugin_source,args.fluent_archive,args.fluent_notices)
