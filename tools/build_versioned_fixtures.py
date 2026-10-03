#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-2.0-or-later
"""Build explicitly opted-in synthetic packages for update-policy tests."""

import argparse
import json
from pathlib import Path

import iconlib

ROOT = Path(__file__).resolve().parents[1]
FIXTURES = ROOT / "tests" / "fixtures"


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("output_dir", type=Path)
    parser.add_argument("--allow-test-fixtures", action="store_true", help="required opt-in; never use for production packages")
    args = parser.parse_args()
    if not args.allow_test_fixtures:
        parser.error("--allow-test-fixtures is required for synthetic data")
    args.output_dir.mkdir(parents=True, exist_ok=True)
    built = {}
    for name, source in (
        ("outline-1.0.0", FIXTURES / "synthetic"),
        ("outline-1.1.0", FIXTURES / "versioned" / "outline-1.1"),
        ("solid-1.0.0", FIXTURES / "versioned" / "solid-1.0"),
    ):
        package = args.output_dir / f"{name}.zip"
        descriptor = args.output_dir / f"{name}.descriptor.json"
        built[name] = iconlib.build(source / "manifest.json", source, package, descriptor, allow_test_fixture=True)
        iconlib.validate_trusted(package, descriptor, allow_test_fixture=True)
    print(json.dumps(built, sort_keys=True, indent=2))


if __name__ == "__main__":
    main()
