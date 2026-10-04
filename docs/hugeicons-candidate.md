# Hugeicons Stroke Rounded Candidate

This is a local, data-only package candidate. It is not a production catalog
entry, approved distribution, or release. Keep the production catalog empty
pending separate plugin distribution review and owner approval.

## Pinned Inputs

- Package: `@hugeicons/core-free-icons` 4.3.5, upstream revision
  `bf880d758a69ab69edb278f8b529579fac54e5df`.
- Source snapshot: `mehul0810/aculect-icon-library` PR 55 commit
  `b05885affafa498def32b7ead86b86df01f03dbf`, path
  `assets/icons/hugeicons/`.
- Source manifest SHA-256:
  `d1e809bd0bd18066e105dabaee397bcdfaea559355876adf6795d2659142be3e`.
- MIT license SHA-256:
  `1658d8213209df7b9b86dfc05d724ede48d00dbc27abc15976ec7adec9601cde`.
- Exclusions record SHA-256:
  `2e20bf837c67a5d2dfae4151dd6acf36095d1ddd6a5e6562f292c932ccc6f642`.
- The pinned source contains 6,064 Stroke Rounded SVGs. Three upstream icons
  were excluded because their per-element opacity is not preserved by Core:
  `arrow-big-right-dash`, `hamburger01`, and `right-to-left-list-bullet`.

The exporter checks pinned metadata and license hashes, the exact source icon
and filename set, every input SVG hash, source IDs, Core names, and variant.
It removes only `fill="currentColor"`; it preserves each `viewBox`, each path
in order, every path-data string, and any `fill-rule`. Other SVG shapes,
attributes, fill values, nested content, or fill rules fail closed. The MIT
notice is included in the package. No artwork is committed to this repository.

## Reproduction

From the plugin's local Git object database, extract only the pinned source
directory and export after committing the converter:

```sh
git -C /path/to/aculect-icon-library archive b05885affafa498def32b7ead86b86df01f03dbf assets/icons/hugeicons | tar -x -C /private/tmp/hugeicons-source
python3 tools/export_hugeicons.py /private/tmp/hugeicons-source/assets/icons/hugeicons /private/tmp/hugeicons-package-root
python3 tools/iconlib.py build /private/tmp/hugeicons-package-root/manifest.json /private/tmp/hugeicons-package-root /private/tmp/hugeicons-stroke-rounded-1.0.0.zip /private/tmp/hugeicons-stroke-rounded-1.0.0.descriptor.json
python3 tools/iconlib.py validate /private/tmp/hugeicons-stroke-rounded-1.0.0.zip --trusted-descriptor /private/tmp/hugeicons-stroke-rounded-1.0.0.descriptor.json
```

The package release version begins at `1.0.0`, independent of upstream 4.3.5.
The converter refuses to export unless its working bytes exactly match its
recorded Git commit. GitHub Releases and any plugin download URL remain
provisional and are not distribution authorization.
