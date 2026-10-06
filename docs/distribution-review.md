# Distribution Review (Open)

Current distribution status (2026-10-06): the owner authorized publication of
35 reviewed exact-version GitHub data releases and catalog installation wiring.
All public archives, descriptors and licensed previews were independently
HTTPS-verified before the entries were marked available. Simple Icons and
Keyline remain noninstallable. The foundation discussion below is historical;
its empty-catalog gate is superseded for this authorized GitHub distribution.
WordPress.org policy acceptance remains unresolved. The plugin's
`release/1.2.0` branch includes a pinned, consent-based data installer and preview
flow. Passing its tests is not directory approval.

Issue #1 tracks the initial data-library foundation. The main plugin's distribution/integration tracker is [issue #64](https://github.com/mehul0810/aculect-icon-library/issues/64).

## Historical foundation proposal

GitHub Releases with exact-version asset URLs and SHA-256 checksums are a candidate distribution mechanism only. Exact-version URLs are not inherently immutable; protection against replacement depends on release/repository policy and must be reviewed. A future plugin-shipped, reviewed catalog must anchor the expected checksum independently of the download source; a checksum fetched from the same mutable source as the package is not a trust anchor. No production package, release, hosting URL, or live catalog exists. Consumers must not resolve a moving `latest` URL. This repository does not currently implement a release workflow or consumer installer.

## WordPress.org clarification required

Before a WordPress.org release, confirm how plugin guidelines 7 (external service/offloading) and 8 (executable code) apply to downloadable icon data and package handling. No answer has been submitted or received. Owner-authorized GitHub publication does not establish directory acceptance.

Unsent question draft:

> We are evaluating a WordPress plugin that may offer optional icon libraries as user-selected, versioned data packages. Packages would contain SVG artwork plus JSON metadata and license/provenance text, with no PHP, JavaScript, or other executable code. The plugin may download an exact-version package from a GitHub Release and verify it against a checksum anchored in a plugin-shipped catalog before installation. Would this distribution model comply with guidelines 7 and 8, and are there additional requirements for user consent, attribution, caching, or availability? We have not published or enabled this behavior.

This is a draft, not a policy determination or a submitted support request. Third-party assets remain subject to their own license terms; this repository does not grant rights in them.
