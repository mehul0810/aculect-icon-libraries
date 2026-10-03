# Runtime Contract (Not Implemented)

This repository currently contains only a package builder/validator. The following constraints are proposed for any future plugin importer; they are not evidence of implemented runtime behavior.

- Store each installed library/style/version in per-site persistent storage using immutable versioned directories. Do not rely on temporary cache storage for the only copy.
- Install into a new version directory, validate every member and expected digest, then atomically switch a small active-version pointer only after the full install succeeds.
- Make retries idempotent. Serialize competing installs with a per-library lock and fencing token/generation check so an expired worker cannot replace a newer active pointer.
- Frontend rendering must use locally stored package data and remain available without network access. Remote checks/downloads must not be required on the render path.
- Disabling the plugin or a library must stop registration/use but retain installed assets. Do not purge user data or packages automatically; deletion needs an explicit, separately reviewed action.
- Keep upstream source, exact revision, conversion procedure, license/attribution, package hash, and Core/plugin sanitizer compatibility as release gates. Passing this local validator is not sufficient.

Storage layout, lock implementation, multisite ownership, schema migration, cleanup policy, and importer permissions still need architecture review before runtime work begins.
