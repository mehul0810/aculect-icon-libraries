# Distribution Review (Open)

Current preparation status (2026-10-06): the owner authorized the existing
repository's issue-backed catalog, bounded previews and read-only CI preparation.
The catalog now records unpublished packs and explicit gates; it does not grant
installation availability. No release assets were published by this work.
The foundation discussion below is historical. Its empty-catalog gate has been
superseded for this authorized repository preparation, while release publication
and WordPress.org policy review remain separate decisions. The plugin's local
`release/1.2.0` branch includes a pinned, consent-based data installer and preview
flow. Passing its tests is not directory approval.

Issue #1 tracks the initial data-library foundation. The main plugin's distribution/integration tracker is [issue #64](https://github.com/mehul0810/aculect-icon-library/issues/64).

## Provisional option

GitHub Releases with exact-version asset URLs and SHA-256 checksums are a candidate distribution mechanism only. Exact-version URLs are not inherently immutable; protection against replacement depends on release/repository policy and must be reviewed. A future plugin-shipped, reviewed catalog must anchor the expected checksum independently of the download source; a checksum fetched from the same mutable source as the package is not a trust anchor. No production package, release, hosting URL, or live catalog exists. Consumers must not resolve a moving `latest` URL. This repository does not currently implement a release workflow or consumer installer.

## WordPress.org clarification required

Before choosing external distribution, confirm how plugin guidelines 7 (external service/offloading) and 8 (executable code) apply to downloadable icon data and package handling. No answer has been submitted or received. Keep the production catalog empty pending that review and owner approval.

Unsent question draft:

> We are evaluating a WordPress plugin that may offer optional icon libraries as user-selected, versioned data packages. Packages would contain SVG artwork plus JSON metadata and license/provenance text, with no PHP, JavaScript, or other executable code. The plugin may download an exact-version package from a GitHub Release and verify it against a checksum anchored in a plugin-shipped catalog before installation. Would this distribution model comply with guidelines 7 and 8, and are there additional requirements for user consent, attribution, caching, or availability? We have not published or enabled this behavior.

This is a draft, not a policy determination or a submitted support request. Third-party assets remain subject to their own license terms; this repository does not grant rights in them.
