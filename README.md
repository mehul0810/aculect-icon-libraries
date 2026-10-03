# Aculect Icon Libraries

Versioned, data-only icon packages and build-time tooling for Aculect Icon Library. This repository is at foundation stage: the production catalog is empty, the package format is a draft, and no runtime importer or distribution workflow is implemented.

See [the draft format specification](docs/format-v1.md) and [open distribution review](docs/distribution-review.md). Main plugin integration is tracked in [issue #64](https://github.com/mehul0810/aculect-icon-library/issues/64); this repository foundation is tracked in [issue #1](https://github.com/mehul0810/aculect-icon-libraries/issues/1).

The standard-library-only builder is `tools/iconlib.py` and requires Python 3.9 or newer. Run checks with `python3 -m unittest discover -s tests -v`. Build with `python3 tools/iconlib.py build MANIFEST SOURCE_DIR PACKAGE.zip DESCRIPTOR.json`, then validate with `python3 tools/iconlib.py validate PACKAGE.zip --trusted-descriptor DESCRIPTOR.json`.

Its synthetic geometric fixture is test-only and does not represent upstream artwork or a production library. Local validation checks a deliberately narrow SVG subset; it does not prove WordPress Core sanitizer or plugin importer compatibility. Original tooling and synthetic test material are licensed GPL-2.0-or-later; see [COPYING](COPYING). Third-party libraries retain their own licenses. This repository does not grant rights in third-party artwork.
