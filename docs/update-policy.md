# Package Update Policy (Draft)

This policy describes the identity and compatibility rules a future installer must enforce. The current builder does not install, upgrade, or publish packages.

- A package identity is `(library_id, style_id)`. `release_version` versions that package only; it is not `schema_version` and is not the upstream library's version.
- Releases use SemVer, bounded to 64 characters and nine digits per numeric core or prerelease component. A package's initial release is `1.0.0`. Prereleases compare below the final release with the same numeric core; build metadata does not affect precedence.
- The exact package SHA-256 is immutable for an identity and exact release version. Reinstalling the same version and digest is an idempotent no-op; the same version with different bytes is rejected.
- A candidate with lower SemVer precedence than the installed version is rejected. Downgrades require a separate, explicit rollback workflow and are outside this draft.
- `core_icon_name` is a stable saved-content identity, not an upstream filename. The plugin currently prefixes it with `library_id`, so names must be unique across all styles in one library as well as within each package. Renaming an identity is a compatibility change, not an ordinary metadata edit.
- On update, retain historical `(library_id, style_id, id, core_icon_name)` ownership records, including icons absent from the candidate. Both ID-to-name/style and name-to-ID/style ownership are immutable. Removed records must continue resolving through the prior asset; neither another ID nor another style may claim their names. The same exact identity may return in a later version.
- Keep the previous active package until the candidate is fully validated and atomically activated. Storage, concurrency, rollback, and deletion details remain subject to runtime architecture review.

`check_update(..., historical_owners=())` returns the complete ownership record list. Persist that result, then pass it to every subsequent `check_update` and `validate_library_styles` call. Omitting earlier history cannot protect identities no longer present in the supplied manifests. These helpers consume validated manifests and caller-owned history; a package cannot supply its own trusted history.

The synthetic fixture builder demonstrates one `synthetic-test/outline` update from `1.0.0` to `1.1.0` with changed artwork for one stable name, a removed name, and an added name, plus a second style. It does not implement or prove runtime installation.
