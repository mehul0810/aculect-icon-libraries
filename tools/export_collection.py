#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-2.0-or-later
"""Convert reviewed monochrome snapshots to the strict data-only contract.

No upstream code runs. Unsupported styling/geometry fails closed. Polygon
conversion and the three orthogonal Radix transforms preserve exact geometry.
"""
import json
import re
import shutil
from decimal import Decimal
from pathlib import Path
from xml.etree import ElementTree as ET

import iconlib

NS = iconlib.SVG_NS
ET.register_namespace("", NS)
NUMBER = r"[+-]?(?:\d+(?:\.\d*)?|\.\d+)(?:[eE][+-]?\d+)?"


def number(value):
    value = Decimal(value)
    if not value.is_finite() or abs(value) > 1000000:
        raise ValueError("coordinate outside reviewed bounds")
    return value


def spelling(value):
    return format(value, "f").rstrip("0").rstrip(".") if "." in format(value, "f") else str(value)


def transform_path(data, transform):
    iconlib.validate_path_data(data)
    rotation = re.fullmatch(r"rotate\((90|-180)\s+(" + NUMBER + r")\s+(" + NUMBER + r")\)", transform)
    reflection = re.fullmatch(r"matrix\(0\s+1\s+1\s+0\s+(" + NUMBER + r")\s+(" + NUMBER + r")\)", transform)
    if rotation:
        angle, cx, cy = rotation.groups()
        cx, cy = number(cx), number(cy)
        a,b,c,d,e,f = (0,1,-1,0,cx+cy,cy-cx) if angle == "90" else (-1,0,0,-1,2*cx,2*cy)
    elif reflection:
        a,b,c,d,e,f = 0,1,1,0,number(reflection[1]),number(reflection[2])
    else:
        raise ValueError("unreviewed transform")
    tokens = re.findall(r"[A-Za-z]|" + NUMBER, data)
    output, index, command = [], 0, None
    x = y = sx = sy = Decimal(0)
    def point(px, py):
        return spelling(a*px+c*py+e) + " " + spelling(b*px+d*py+f)
    while index < len(tokens):
        if tokens[index].isalpha():
            command = tokens[index]
            index += 1
        if command not in ("M", "L", "H", "V", "A", "Z"):
            raise ValueError("unreviewed transformed path command")
        if command == "Z":
            output.append("Z")
            x,y = sx,sy
            command = None
            continue
        arity = iconlib.PATH_ARITY[command]
        values = [number(v) for v in tokens[index:index+arity]]
        if len(values) != arity:
            raise ValueError("incomplete transformed path")
        index += arity
        if command in ("M", "L"):
            x,y = values
            output.append(command + " " + point(x,y))
            if command == "M":
                sx,sy = x,y
                command = "L"
        elif command in ("H", "V"):
            if command == "H": x = values[0]
            else: y = values[0]
            output.append("L " + point(x,y))
        else:
            rx,ry,axis,large,sweep,x,y = values
            if rx != ry or axis != 0 or large not in (0,1) or sweep not in (0,1):
                raise ValueError("only reviewed circular arcs may be transformed")
            if a*d-b*c < 0: sweep = 1-sweep
            output.append("A " + " ".join(map(spelling,(rx,ry,axis,large,sweep))) + " " + point(x,y))
    return " ".join(output)


def polygon_path(points):
    if re.sub(NUMBER, "", points).strip(" ,\t\r\n"):
        raise ValueError("invalid polygon points")
    values = re.findall(NUMBER, points)
    if len(values) < 6 or len(values) % 2:
        raise ValueError("incomplete polygon")
    values = [spelling(number(v)) for v in values]
    return "M " + " ".join(values[:2]) + " L " + " ".join(values[2:]) + " Z"


def normalize_svg(raw):
    if len(raw) > iconlib.MAX_SVG or re.search(br"<!\s*(?:DOCTYPE|ENTITY)",raw,re.I) or b"<?" in raw or b"\x00" in raw:
        raise ValueError("unsupported XML declaration or size")
    root = ET.fromstring(raw.decode("utf-8"))
    if root.tag != "{"+NS+"}svg" or not set(root.attrib) <= {"viewBox","height","width","fill","class","aria-hidden"} or "viewBox" not in root.attrib:
        raise ValueError("unsupported SVG root")
    if root.attrib.get("fill", "currentColor") not in ("currentColor", "black", "#000", "#000000"):
        raise ValueError("unsupported root fill")
    if root.text and root.text.strip(): raise ValueError("unexpected text")
    output = ET.Element("{"+NS+"}svg", {"viewBox":root.attrib["viewBox"]})
    for child in root:
        if list(child) or child.text and child.text.strip() or child.tail and child.tail.strip():
            raise ValueError("unsupported nested SVG data")
        if child.tag not in ("{"+NS+"}path", "{"+NS+"}polygon"):
            raise ValueError("unsupported SVG geometry")
        attrs = dict(child.attrib)
        fill = attrs.pop("fill", "currentColor")
        if fill not in ("none", "currentColor", "black", "#000", "#000000"):
            raise ValueError("unsupported path fill")
        clip = attrs.pop("clip-rule", None)
        if clip not in (None,"evenodd","nonzero"):
            raise ValueError("unsupported clip rule")
        transform = attrs.pop("transform", None)
        if child.tag.endswith("polygon"):
            if set(attrs) != {"points"} or transform:
                raise ValueError("unsupported polygon attributes")
            attrs = {"d":polygon_path(attrs["points"])}
        if not set(attrs) <= {"d","fill-rule"} or "d" not in attrs:
            raise ValueError("unsupported path attributes")
        iconlib.validate_path_data(attrs["d"])
        if attrs.get("fill-rule", "nonzero") not in ("nonzero","evenodd"):
            raise ValueError("invalid fill rule")
        if transform: attrs["d"] = transform_path(attrs["d"],transform)
        # An unpainted, unstroked path is invisible. clip-rule has no effect
        # outside a clipPath; clipPaths and references are rejected above.
        if fill != "none": ET.SubElement(output,"{"+NS+"}path",attrs)
    payload = ET.tostring(output,encoding="utf-8")
    iconlib.validate_svg(payload)
    return payload


def export(source, output, pin, style, revision):
    source,output = Path(source),Path(output)
    if source.is_symlink() or output.exists() or output.is_symlink():
        raise ValueError("unsafe source or existing destination")
    raw_manifest = (source/"manifest.json").read_bytes()
    license_bytes = (source/"LICENSE").read_bytes()
    if iconlib.sha256(raw_manifest) != pin["manifest_sha256"] or iconlib.sha256(license_bytes) != pin["license_sha256"]:
        raise ValueError("source manifest or license pin mismatch")
    manifest = iconlib.parse_json(raw_manifest,"source manifest")
    if manifest["source"]["revision"] != pin["upstream_revision"]:
        raise ValueError("upstream provenance mismatch")
    records = sorted((r for r in manifest["icons"] if r["variant"] == style),key=lambda r:r["id"])
    if len(records) != pin["styles"][style]: raise ValueError("source count mismatch")
    output.mkdir(parents=True)
    (output/"icons").mkdir()
    (output/"licenses").mkdir()
    try:
        (output/"licenses/LICENSE.txt").write_bytes(license_bytes)
        icons = []
        for record in records:
            iconlib.validate_path(record["path"], style+"/")
            path = source/record["path"]
            if path.is_symlink() or any(p.is_symlink() for p in path.parents if p != source.parent): raise ValueError("symlink input")
            raw = path.read_bytes()
            if iconlib.sha256(raw) != record["sha256"]: raise ValueError("source SVG pin mismatch")
            name = record["coreIconName"].removeprefix(pin["library_id"]+"/")
            iconlib.validate_id(name,"saved name")
            payload = normalize_svg(raw)
            relative = "icons/"+name+".svg"
            (output/relative).write_bytes(payload)
            icons.append({"id":name,"core_icon_name":name,"label":record["label"],"keywords":record["keywords"],"path":relative,"sha256":iconlib.sha256(payload),"source_icon_id":record["id"]})
        package = {"schema_version":1,"library_id":pin["library_id"],"style_id":style,"release_version":"1.0.0","upstream":{"name":manifest["source"]["name"],"revision":pin["upstream_revision"]},"source_snapshot":{"name":"mehul0810/aculect-icon-library","revision":pin["snapshot_revision"]},"conversion":{"tool":"aculect-icon-libraries/tools/export_collection.py","revision":revision},"license":{"path":"licenses/LICENSE.txt","sha256":iconlib.sha256(license_bytes)},"icons":icons}
        (output/"manifest.json").write_text(json.dumps(package,ensure_ascii=True,indent=2)+"\n",encoding="utf-8")
        return package
    except Exception:
        shutil.rmtree(output)
        raise
