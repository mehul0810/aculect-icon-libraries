#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-2.0-or-later
"""Verify published data assets against reviewed catalog pins without credentials."""

import argparse
import concurrent.futures
import json
import tempfile
import urllib.parse
import urllib.request
from pathlib import Path

import build_preview
import iconlib

RELEASE_BASE = "https://github.com/mehul0810/aculect-icon-libraries/releases/download/"
ASSET_HOSTS = {"github.com", "release-assets.githubusercontent.com", "objects.githubusercontent.com"}


def require_asset_url(url):
    parsed = urllib.parse.urlsplit(url)
    if (parsed.scheme != "https" or parsed.hostname not in ASSET_HOSTS
            or parsed.username or parsed.password or parsed.port not in (None, 443)
            or parsed.fragment):
        raise iconlib.PackageError("release redirect leaves the trusted HTTPS asset hosts")


class AssetRedirects(urllib.request.HTTPRedirectHandler):
    max_redirections = 3
    max_repeats = 1

    def redirect_request(self, request, fp, code, message, headers, url):
        require_asset_url(url)
        return super().redirect_request(request, fp, code, message, headers, url)


def fetch_asset(url, limit, opener=None):
    require_asset_url(url)
    opener = opener or urllib.request.build_opener(AssetRedirects())
    request = urllib.request.Request(url, headers={"User-Agent": "Aculect-reviewed-release-verifier/1"})
    with opener.open(request, timeout=60) as response:
        if response.status != 200:
            raise iconlib.PackageError("release asset did not return HTTP 200")
        require_asset_url(response.geturl())
        return iconlib.bounded_read(response, limit)


def validate_assets(directory, pin):
    tag = "-".join(pin[key] for key in ("library_id", "style_id", "release_version"))
    directory = Path(directory)
    archive = directory / (tag + ".zip")
    descriptor = directory / (tag + ".descriptor.json")
    preview = directory / (tag + ".preview.json")
    verified = iconlib.validate_trusted(archive, descriptor)
    for key, value in verified.items():
        if pin.get(key) != value:
            raise iconlib.PackageError("published descriptor differs from reviewed pin: " + key)
    raw = preview.read_bytes()
    if len(raw) != pin["preview_bytes"] or iconlib.sha256(raw) != pin["preview_sha256"]:
        raise iconlib.PackageError("published preview differs from reviewed pin")
    # Rebuild from the validated package: every sample and original license must
    # match, not merely an internally consistent remote descriptor.
    with tempfile.TemporaryDirectory() as temporary:
        rebuilt = Path(temporary) / "preview.json"
        build_preview.build_preview(archive, descriptor, rebuilt)
        if rebuilt.read_bytes() != raw:
            raise iconlib.PackageError("preview samples or attribution differ from the package")
    return {"tag": tag, "icons": pin["icon_count"], "package_sha256": verified["package_sha256"],
            "package_bytes": verified["package_bytes"], "preview_sha256": pin["preview_sha256"],
            "preview_bytes": pin["preview_bytes"], "url": RELEASE_BASE + tag + "/" + tag + ".zip"}


def verify_one(pin, directory):
    tag = "-".join(pin[key] for key in ("library_id", "style_id", "release_version"))
    try:
        for suffix, limit in ((".zip", iconlib.MAX_ARCHIVE),
                              (".descriptor.json", iconlib.MAX_DESCRIPTOR),
                              (".preview.json", build_preview.MAX_PREVIEW)):
            destination = directory / (tag + suffix)
            iconlib.preflight_output(destination)
            raw = fetch_asset(RELEASE_BASE + tag + "/" + tag + suffix, limit)
            destination.write_bytes(raw)
        result = validate_assets(directory, pin)
    except Exception as error:
        # Signed CDN redirect URLs are transport details, not receipt/log data.
        raise iconlib.PackageError("public verification failed for " + tag + " (" + type(error).__name__ + ")") from None
    print("Verified " + tag, flush=True)
    return result


def verify_releases(catalog, directory):
    directory = Path(directory)
    if directory.is_symlink():
        raise iconlib.PackageError("verification directory must not be a symlink")
    directory.mkdir(parents=True, exist_ok=True)
    pins, seen = [], set()
    for pin in catalog["libraries"]:
        if pin.get("availability") != "available":
            continue
        for key in ("library_id", "style_id"):
            iconlib.validate_id(pin[key], key)
        iconlib.version_key(pin["release_version"])
        identity = tuple(pin[key] for key in ("library_id", "style_id", "release_version"))
        if identity in seen:
            raise iconlib.PackageError("duplicate public release identity")
        seen.add(identity)
        pins.append(pin)
    # Bound independent pack downloads; each archive still has strict byte,
    # redirect and package limits. Receipt order follows the reviewed catalog.
    with concurrent.futures.ThreadPoolExecutor(max_workers=4) as workers:
        results = list(workers.map(lambda pin: verify_one(pin, directory), pins))
    return {"packages": len(results), "icons": sum(result["icons"] for result in results),
            "public_http_verified": True, "assets_per_package": 3, "releases": results}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("catalog", type=Path)
    parser.add_argument("directory", type=Path)
    parser.add_argument("--receipt", type=Path)
    args = parser.parse_args()
    catalog = iconlib.parse_json(args.catalog.read_bytes(), "catalog")
    result = verify_releases(catalog, args.directory)
    raw = json.dumps(result, indent=2) + "\n"
    if args.receipt:
        args.receipt.write_text(raw)
    print(json.dumps({key: value for key, value in result.items() if key != "releases"}))


if __name__ == "__main__":
    main()
