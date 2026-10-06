#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-2.0-or-later
"""Bound Fluent installation state by size; preserve SVG bytes and licenses."""
import argparse
import json
import re
import shutil
import subprocess
import tempfile
import zipfile
from pathlib import Path
import iconlib
from build_preview import build_preview

ROOT = Path(__file__).resolve().parents[1]
ORIGINAL_PINS = "49696626d6095f424a01d87d523faa4316a84596"


def resize(manifest,size,style,revision):
    library = "fluent-ui-"+size
    original_style = style+"-"+size
    if manifest["library_id"] != "fluent-ui" or manifest["style_id"] != original_style:
        raise ValueError("unexpected source identity")
    converted = json.loads(json.dumps(manifest))
    converted.update(library_id=library,style_id=style)
    converted["source_snapshot"] = {"name":"aculect-icon-libraries/frozen Fluent export","revision":manifest["conversion"]["revision"]}
    converted["conversion"] = {"tool":"aculect-icon-libraries/tools/size_fluent.py","revision":revision}
    for icon in converted["icons"]:
        suffix = "-"+original_style
        if not icon["core_icon_name"].endswith(suffix) or icon["id"] != icon["core_icon_name"]:
            raise ValueError("unexpected Fluent identity")
        name = icon["core_icon_name"][:-len(suffix)]+"-"+style
        icon.update(id=name,core_icon_name=name,path="icons/"+name+".svg")
    iconlib.validate_library_styles([converted])
    return converted


def repack(directory,revision):
    if not re.fullmatch(r"[a-f0-9]{40}",revision): raise ValueError("immutable size-converter revision required")
    committed = subprocess.check_output(["git","-C",str(ROOT),"show",revision+":tools/size_fluent.py"])
    if committed != Path(__file__).read_bytes(): raise ValueError("size converter differs from its recorded commit")
    original = json.loads(subprocess.check_output(["git","-C",str(ROOT),"show",ORIGINAL_PINS+":data/catalog.json"]))["libraries"]
    pins = {p["style_id"]:p for p in original if p["library_id"] == "fluent-ui"}
    directory = Path(directory)
    catalog = json.loads((directory/"prepared-catalog.json").read_bytes())
    result = [p for p in catalog["libraries"] if p["library_id"] != "fluent-ui"]
    manifests = []
    for old_style,pin in sorted(pins.items()):
        style,size = old_style.split("-")
        old_tag = "fluent-ui-"+old_style+"-1.0.0"
        archive = directory/(old_tag+".zip")
        descriptor = directory/(old_tag+".descriptor.json")
        # Source authority is the earlier immutable reviewed catalog, not a
        # checksum obtained from the package being converted.
        actual = iconlib.descriptor_for(archive)
        for key,value in actual.items():
            if pin.get(key) != value: raise ValueError("frozen Fluent source pin differs: "+key)
        iconlib.validate_trusted(archive,descriptor)
        with tempfile.TemporaryDirectory(prefix="aculect-fluent-size-") as temporary:
            tree = Path(temporary)
            (tree/"icons").mkdir(); (tree/"licenses").mkdir()
            with zipfile.ZipFile(archive) as source:
                old_manifest = json.loads(source.read("manifest.json"))
                manifest = resize(old_manifest,size,style,revision)
                for old,new in zip(old_manifest["icons"],manifest["icons"]):
                    (tree/new["path"]).write_bytes(source.read(old["path"]))
                (tree/manifest["license"]["path"]).write_bytes(source.read(old_manifest["license"]["path"]))
            (tree/"manifest.json").write_text(json.dumps(manifest,ensure_ascii=True,indent=2)+"\n",encoding="utf-8")
            tag = manifest["library_id"]+"-"+style+"-1.0.0"
            target,desc = directory/(tag+".zip"),directory/(tag+".descriptor.json")
            iconlib.build(tree/"manifest.json",tree,target,desc)
            entry = build_preview(target,desc,directory/(tag+".preview.json"))
            entry.update(icon_count=len(manifest["icons"]),availability="pending-publication")
            result.append(entry);manifests.append(manifest)
        for suffix in (".zip",".descriptor.json",".preview.json"): (directory/(old_tag+suffix)).unlink()
    iconlib.validate_library_styles(manifests)
    catalog["libraries"] = sorted(result,key=lambda p:(p["library_id"],p["style_id"]))
    (directory/"prepared-catalog.json").write_text(json.dumps(catalog,indent=2)+"\n",encoding="utf-8")
    print(json.dumps({"packs":len(result),"fluent_sizes":8,"fluent_style_packs":16,"fluent_icons":sum(len(m["icons"]) for m in manifests),"svg_bytes_preserved":True}))


if __name__ == "__main__":
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument("directory",type=Path)
    parser.add_argument("--revision",required=True)
    args=parser.parse_args();repack(args.directory,args.revision)
