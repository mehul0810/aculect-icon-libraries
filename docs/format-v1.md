# Package Format v1 (Draft)

Status: draft; not a compatibility guarantee for the WordPress plugin or its eventual importer.

A package is a ZIP containing exactly `manifest.json`, one declared license text file under `licenses/`, and the declared SVG files under `icons/`. Package members are regular, non-executable files. Paths use forward slashes and ASCII-safe relative components. Duplicate paths, case-fold collisions, traversal, absolute paths, backslashes, symlinks, and undeclared members are invalid.

The UTF-8 JSON manifest has this shape:

```json
{
  "schema_version": 1,
  "library_id": "example-library",
  "style_id": "outline",
  "release_version": "1.0.0",
  "upstream": {"name": "", "revision": "40- or 64-character lowercase commit hash"},
  "conversion": {"tool": "", "revision": "40- or 64-character lowercase commit hash"},
  "license": {"path": "licenses/LICENSE.txt", "sha256": "64 lowercase hex digits"},
  "icons": [{"id": "example-icon", "core_icon_name": "example-icon", "label": "Example icon", "keywords": ["example"], "path": "icons/example-icon.svg", "sha256": "64 lowercase hex digits"}]
}
```

IDs are stable lowercase identifiers. `core_icon_name` is the explicitly stored stable saved identity for a mapped Core icon and must be unique within the library/style; future unmapped/custom identity behavior requires a separately documented integration decision. Labels and keywords are plain text metadata, not HTML. Production `upstream.revision` and `conversion.revision` are full lowercase 40- or 64-character hexadecimal immutable revision hashes, never moving branch names. The checked-in geometric fixture is marked `test_fixture: true`; its `synthetic-test:` revision labels are test-only and must not be treated as upstream or converter commits. The license path/hash bind the exact included UTF-8 `.txt` license text. Each `.svg` icon path/hash bind exact SVG bytes. A generated descriptor is stored outside the ZIP and records the package SHA-256, manifest SHA-256, and byte count. This avoids circular hashing. Validation against an archive must use a caller-supplied trusted descriptor; a digest found only inside the untrusted archive is not a trust anchor.

The local builder applies conservative initial limits: 32 MiB compressed package, 8 MiB manifest, 128 KiB license text, 64 KiB per SVG, and 128 MiB total expanded content, with at most 10,000 icons. SVG support is intentionally restricted to SVG root plus `path` elements with `d` geometry and optional `fill-rule`; root dimensions are numeric and root fill is unsupported. XML DTDs/entities, non-UTF-8 data, NUL/control characters, processing instructions, namespaces other than SVG, scripts, events, style, references, and external resources are rejected. Parsing uses Python's standard XML parser on validated UTF-8 Unicode text after bounded reads and declaration checks.

The format remains provisional. Exact Core/plugin sanitizer golden compatibility, importer compatibility, official WordPress.org policy interpretation, upstream rights, and distribution are separate reviews and are not established by passing this validator.
