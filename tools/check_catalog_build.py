#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-2.0-or-later
"""Check the two builds against reviewed pins and committed previews."""
import json
import sys
from pathlib import Path
import iconlib

root = Path(__file__).resolve().parents[1]
first,second = map(Path,sys.argv[1:])
expected = json.loads((root/"data/catalog.json").read_bytes())["libraries"]
actual = json.loads((first/"prepared-catalog.json").read_bytes())["libraries"]
repeat = json.loads((second/"prepared-catalog.json").read_bytes())["libraries"]
if actual != repeat: raise SystemExit("Build descriptors are not reproducible")
if len(expected) != len(actual): raise SystemExit("Prepared/catalog pack counts differ")
for pin,result in zip(expected,actual):
    for key,value in result.items():
        if pin.get(key) != value: raise SystemExit("Catalog pin differs: "+key)
    tag = pin["library_id"]+"-"+pin["style_id"]+"-"+pin["release_version"]
    for suffix in (".zip",".descriptor.json",".preview.json"):
        if (first/(tag+suffix)).read_bytes() != (second/(tag+suffix)).read_bytes(): raise SystemExit("Build bytes differ: "+tag+suffix)
    if (first/(tag+".preview.json")).read_bytes() != (root/"data/previews"/(tag+".preview.json")).read_bytes(): raise SystemExit("Committed preview differs: "+tag)
    iconlib.validate_trusted(first/(tag+".zip"),first/(tag+".descriptor.json"))
print(json.dumps({"packages":len(actual),"icons":sum(p["icon_count"] for p in actual),"reproducible":True,"reviewed_pins_match":True}))
