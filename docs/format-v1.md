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
  "upstream": {"name": "", "revision": ""},
  "conversion": {"tool": "", "revision": ""},
  "license": {"path": "licenses/LICENSE.txt", "sha256": "64 lowercase hex digits"},
  "icons": [{"id": "example-icon", "core_icon_name": "example-icon", "label": "Example icon", "keywords": ["example"], "path": "icons/example-icon.svg", "sha256": "64 lowercase hex digits"}]
}
```

IDs are stable lowercase identifiers. `core_icon_name` is the explicitly stored stable saved identity for a mapped Core icon; future unmapped/custom identity behavior requires a separately documented integration decision. Labels and keywords are plain text metadata, not HTML. `upstream.revision` and `conversion.revision` must be immutable revision identifiers, not moving branch names. The license path/hash bind the exact included license text. Each icon path/hash bind exact SVG bytes. A generated descriptor is stored outside the ZIP and records the package SHA-256, manifest SHA-256, and byte count. This avoids circular hashing. Validation against an archive must use a caller-supplied trusted descriptor; a digest found only inside the untrusted archive is not a trust anchor.

The local builder applies conservative initial limits: 32 MiB compressed package, 2 MiB per archive member, 8 MiB manifest, 128 KiB license text, 128 MiB total expanded content, 10,000 icons, and 64 KiB per SVG. SVG support is intentionally restricted to SVG root plus `path` elements with `d` geometry and optional `fill-rule`; this synthetic subset is not a claim of full upstream SVG support. XML DTDs/entities, namespaces other than SVG, scripts, events, style, references, and external resources are rejected. Parsing uses Python's standard XML parser only after bounded reads and declaration checks.

The format remains provisional. Exact Core/plugin sanitizer golden compatibility, importer compatibility, official WordPress.org policy interpretation, upstream rights, and distribution are separate reviews and are not established by passing this validator.
