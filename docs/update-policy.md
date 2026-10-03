# Package Update Policy (Draft)

This policy describes the identity and compatibility rules a future installer must enforce. The current builder does not install, upgrade, or publish packages.

- A package identity is `(library_id, style_id)`. `release_version` versions that package only; it is not `schema_version` and is not the upstream library's version.
- Releases use SemVer. A package's initial release is `1.0.0`. Prereleases compare below the final release with the same numeric core; build metadata does not affect precedence.
- The exact package SHA-256 is immutable for an identity and exact release version. Reinstalling the same version and digest is an idempotent no-op; the same version with different bytes is rejected.
- A candidate with lower SemVer precedence than the installed version is rejected. Downgrades require a separate, explicit rollback workflow and are outside this draft.
- `core_icon_name` is a stable saved-content identity, not an upstream filename. The plugin currently prefixes it with `library_id`, so names must be unique across all styles in one library as well as within each package. Renaming an identity is a compatibility change, not an ordinary metadata edit.
- On update, retain mappings for all prior names, including names absent from the candidate. Removed names are tombstones and must continue resolving through the installed prior asset or an equivalent preserved mapping; do not silently drop saved content.
- Keep the previous active package until the candidate is fully validated and atomically activated. Storage, concurrency, rollback, and deletion details remain subject to runtime architecture review.

The synthetic fixture builder demonstrates one `synthetic-test/outline` update from `1.0.0` to `1.1.0` with a changed name, a removed name, and an added name, plus a second style. It does not implement or prove runtime installation.
