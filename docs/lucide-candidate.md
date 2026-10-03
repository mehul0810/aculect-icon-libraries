# Lucide Outline Candidate

This is a local, data-only interop candidate. It is not a production catalog entry, approved distribution, or release. Production catalog remains empty pending separate WordPress.org distribution review.

## Pinned Inputs

- Main-repository source snapshot: PR 50 source commit `47ed6c90654254277297e4ec27a367cc777baca9`, read from Git objects rather than the dirty source checkout.
- Vendored upstream: `lucide-icons/lucide` version `1.47.0`, revision `3b9ea6d08707edc439f25a4c354cb0d6b8bee973`.
- Source manifest SHA-256: `0e1f90318f27f9d7ba0fc244add54a480830689dbf09498453b6519332adddc6`.
- Combined ISC and MIT license-notice SHA-256: `b495047bd93a9b06913511076f504daba17d5bbeb3e0650f3bb53a4220329c57`.
- Expected outline count: 1,848, with no exclusions.

The exporter validates both pinned file hashes, each of the 1,848 source asset hashes against the pinned manifest, the complete asset/name set, and the exact `lucide/<slug>-outline` Core identity mapping. Package `core_icon_name` retains `<slug>-outline`; `source_icon_id` retains `lucide/outline/<slug>` for traceability. It carries the supported label and keyword metadata; source categories are intentionally omitted because format v1 has no category field.

## Conversion Boundary

The pinned snapshot contains only an SVG root with a `viewBox` and path children with `d` plus `fill="currentColor"`. The exporter preserves the `viewBox`, every path in order, and each `d` string byte-for-byte as XML attribute content. It removes only `fill="currentColor"`: package records carry geometry, not color styling, and the consuming renderer owns icon color. This intentionally does not preserve an SVG's external CSS `color` inheritance behavior. Any additional root/path attribute, non-path element, nested content, or different fill value fails the export. No `clip-rule` appears in the pinned set; the exporter does not normalize it.

The package version begins at `1.0.0`, independently of upstream `1.47.0`. Before recording `conversion.revision`, the exporter verifies that its exact bytes match the file at `HEAD`; unrelated working-tree changes do not affect this check. Any exporter change requires a new commit and rebuilt candidate.

## Reproduction

Extract only the pinned asset directory from Git, then export to an absent task-local directory:

```sh
git -C /path/to/ail-pr50-source archive 47ed6c90654254277297e4ec27a367cc777baca9 assets/icons/lucide | tar -x -C /private/tmp/lucide-pr50-pinned
python3 tools/export_lucide.py /private/tmp/lucide-pr50-pinned/assets/icons/lucide /private/tmp/lucide-package-root
python3 tools/iconlib.py build /private/tmp/lucide-package-root/manifest.json /private/tmp/lucide-package-root /private/tmp/lucide-outline-1.0.0.zip /private/tmp/lucide-outline-1.0.0.descriptor.json
python3 tools/iconlib.py validate /private/tmp/lucide-outline-1.0.0.zip --trusted-descriptor /private/tmp/lucide-outline-1.0.0.descriptor.json
```

The exporter and package builder are local tooling. No icon artwork ZIP, package catalog entry, release, publication, or activation belongs in this repository as part of this candidate setup.
