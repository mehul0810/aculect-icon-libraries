# Aculect Icon Libraries

Versioned, data-only icon packages and build-time tooling for Aculect Icon Library. The existing catalog records all 15 planned families, with 35 published, independently verified packs across 13 families and separate licensed previews. Simple Icons and Keyline remain gated. See [the full catalog and CI verification](docs/full-catalog.md) for exact scope, source pins, exclusions and distribution boundaries.

See [the draft format specification](docs/format-v1.md) and [open distribution review](docs/distribution-review.md). Main plugin integration is tracked in [issue #64](https://github.com/mehul0810/aculect-icon-library/issues/64); this repository foundation is tracked in [issue #1](https://github.com/mehul0810/aculect-icon-libraries/issues/1).

Local preview tooling now provides a separate, deterministic sample artifact:
`python3 tools/build_preview.py PACKAGE.zip DESCRIPTOR.json RELEASE.preview.json`.
It first validates the full data pack against the caller's reviewed descriptor,
then writes at most 12 static SVG samples and returns their SHA-256/byte count.
It refuses an existing destination and leaves the source ZIP untouched. These
sample pins belong in the existing catalog descriptor when publication is
authorized. Preview data is committed separately from the full packs. The 35 public releases contain the exact reviewed CI bytes and are marked available only after HTTPS hash, package and original-attribution verification.

The foundation's runtime contract is recorded in [runtime-contract.md](docs/runtime-contract.md); the plugin's local release/1.2.0 branch now implements reviewed discovery, previews and installation. See the current [integration and distribution status](docs/full-catalog.md).

The standard-library-only builder is `tools/iconlib.py` and requires Python 3.9 or newer. Run checks with `python3 -m unittest discover -s tests -v`. Build with `python3 tools/iconlib.py build MANIFEST SOURCE_DIR PACKAGE.zip DESCRIPTOR.json`, then validate with `python3 tools/iconlib.py validate PACKAGE.zip --trusted-descriptor DESCRIPTOR.json`.

Per-style version identity and update rules are documented in [update-policy.md](docs/update-policy.md). To reproduce the synthetic `1.0.0` to `1.1.0` update and second-style packages, run `python3 tools/build_versioned_fixtures.py /tmp/iconlib-fixtures --allow-test-fixtures`. The explicit opt-in is required; these packages are test-only and do not populate the production catalog.

Synthetic fixture revision labels are rejected by default, even with a matching trusted descriptor. For test-only fixture builds, explicitly pass `--allow-test-fixture` to both commands:

```sh
python3 tools/iconlib.py build tests/fixtures/synthetic/manifest.json tests/fixtures/synthetic /tmp/synthetic-package.zip /tmp/synthetic-descriptor.json --allow-test-fixture
python3 tools/iconlib.py validate /tmp/synthetic-package.zip --trusted-descriptor /tmp/synthetic-descriptor.json --allow-test-fixture
```

Python callers must likewise pass `allow_test_fixture=True` explicitly. A manifest or descriptor never grants this exception by itself. Do not enable it for production packages.

Build output destinations must be absent or regular non-symlink files. The builder preflights both destinations and backs up existing output files before replacement. Handled publication failures restore replaced outputs or remove newly created outputs; a failed rollback reports retained recovery backups. This is not a two-file atomic transaction: process crashes and concurrent writers are not covered. Use exclusive, local build destinations.

Its synthetic geometric fixture is test-only and does not represent upstream artwork or a production library. Local validation checks a deliberately narrow SVG subset; it does not prove WordPress Core sanitizer or plugin importer compatibility. Original tooling and synthetic test material are licensed GPL-2.0-or-later; see [COPYING](COPYING). Third-party libraries retain their own licenses. This repository does not grant rights in third-party artwork.
