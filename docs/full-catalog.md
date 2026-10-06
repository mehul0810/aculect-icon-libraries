# Issue-backed catalog and pack preparation

The existing `data/catalog.json` is the sole catalog. It records all 15 families
planned in Aculect Icon Library issues and established integration work. Thirty-five
reviewed style/size packs across 13 families contain 38,720 icons. Each pack is
currently `pending-publication`: bounded previews can be fetched independently,
but no downloadable release asset has been approved or published by this change.
Simple Icons and Keyline remain explicitly gated rather than install-ready.
The catalog records the exact supported scope and exclusions for every family.

Previews are JSON containing at most 12 path-only SVG samples and the preserved
license text. Their URL is derived from this canonical repository and the immutable
`preview_revision`; hashes and byte counts are reviewed locally in the plugin.
Neither catalog refresh nor preview downloads the full archive or installs/enables
anything. Whole style packs remain the recommended release layout:
`<library>-<style>-<version>/<library>-<style>-<version>.zip`, with the matching
descriptor and optional sample alongside the asset. No runtime executable code,
fonts, JavaScript, PHP or upstream build scripts enter a package.

`data/source-pins.json` is build provenance, not a second catalog. It binds the
ten existing source manifests, each original license, upstream revision and public
plugin snapshot. Every source SVG is checked against its manifest hash before
conversion. Lucide and Hugeicons reuse their existing reviewed source exporters.
Their new build provenance is version 1.0.1; earlier 1.0.0 bytes and existing
installed content remain immutable. Other first prepared packs use 1.0.0.

The converter preserves original viewBoxes and saved names. It removes only
monochrome presentation attributes, non-clipping clip-rule attributes and
provably invisible unstroked paths. Polygon edges become equivalent closed paths.
The known Radix 90/-180 degree rotations and reflection are flattened with exact
decimal arithmetic, including circular-arc sweep reversal. Other transforms,
colors, strokes, opacity, references or geometry fail closed. The receiving plugin's
strict SVG allowlist remains unchanged.

Fluent uses the official `@fluentui/svg-icons` 1.1.341 archive, bound by SHA-256,
with Microsoft upstream revision `2e4da95009de778ae0f41ec6c17bc67c97f4dc56`.
The original MIT LICENSE and complete NOTICE from that revision are included.
There are 19,588 standard compatible Regular/Filled icons in 16 size/style packs;
45 unsupported files are individually hash-bound in `fluent-exclusions.json`.
945 localized files and Light/Color variants are outside the reviewed scope.
The older feasibility source revision was different; those earlier counts are
not substituted for this exact official archive.

The read-only `prepare-packs.yml` workflow uses standard public GitHub-hosted
runners, immutable action revisions, the system Python standard library and no
secrets or software installations. It builds twice, verifies exact catalog pins,
checks every archive and committed preview, then retains artifacts for seven days.
Source fetching is separate from the frozen converter: `fetch_sources.py` copies
only bounded data from six immutable public plugin snapshots, then supplies that
source tree to `build_catalog.py --plugin-source`. Source exclusion JSON uses the
8 MiB metadata bound; artwork retains its 64 KiB limit. The CI fix for this source
metadata boundary preserves the already reviewed package bytes and versions.
It cannot create tags or publish releases. Artifacts are preparation evidence,
not public install delivery. Approval to publish versioned release assets remains
a separate owner decision after the CI artifacts have been verified.

SHA-256 establishes byte integrity relative to the plugin-shipped trust anchors;
it is not a publisher signature. Authenticity depends on the reviewed immutable
source commits, TLS, control of this canonical GitHub repository and review of
plugin updates that introduce new pins. A compromised index cannot replace
package/preview hashes or redirect previews to an arbitrary host.

Fresh sites reserve no legacy collection namespaces and start with zero installed
or enabled collections. Upgraded sites retain their legacy libraries, enabled
choices and saved content; those namespaces remain reserved and the UI directs
users to manage the existing library. Installed packs are enabled only explicitly,
and disabling preserves saved content and installed files. A catalog outage keeps
the last verified index and preview cache; unpublished packs cannot start jobs.

WordPress.org directory acceptance remains unresolved. Its current detailed
guidelines, including remote consent and externally delivered assets, require
distribution review; passing these tests does not imply directory approval.
No repository permissions, production site options or stable plugin release are
changed by this catalog preparation.
