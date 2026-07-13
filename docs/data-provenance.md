# Data provenance & licensing

!!! danger "The code license is not the data license"
    `tracelines` is **AGPL-3.0-or-later** — that covers the *code*. The coverage GeoJSON you
    generate carries the **source's** terms, which differ per source. This is not legal advice.

## What each source lets you do with the OUTPUT

| Source | How it's fetched | Data terms | Redistribute the output? | Attribution |
|--------|------------------|-----------|--------------------------|-------------|
| **Google** (streetlevel) | undocumented internal coverage tiles; no key | **No clean redistribution license.** Google's ToS prohibits scraping/bulk extraction. "A road is covered" is arguably a fact, but ToS + database-rights make bulk redistribution murky. | **No** — generate for your own use. | n/a |
| **Mapillary** | documented Graph API + `mly1_public` tiles; free token | **CC-BY-SA 4.0** (incl. EU database rights) + API terms | **Yes**, with attribution + share-alike | © Mapillary contributors, CC-BY-SA 4.0 |
| **KartaView** | documented public bbox API; keyless | **CC-BY-SA 4.0** | **Yes**, with attribution + share-alike | © KartaView contributors, CC-BY-SA 4.0 |

## Rules of thumb

- **This repo ships the tool, not datasets.** No bulk coverage is committed — especially not
  Google-derived data — so the repo is not an unlicensed redistribution point.
- **A fused layer is only as clean as its dirtiest source.** Any Google-derived geometry inherits
  Google's ToS problem; a Mapillary/KartaView-only layer is redistributable under CC-BY-SA 4.0.
- **Every output feature carries a `source` property** — that's your provenance. Filter by it
  before you share.

## Summary

- **Google output** → yours to use, not to redistribute.
- **Mapillary / KartaView output** → redistributable under CC-BY-SA 4.0 (attribute + share-alike).
- **The tool** → AGPL-3.0-or-later.

See also the repository files [`DATA_LICENSES.md`](https://github.com/Prekzursil/tracelines/blob/main/DATA_LICENSES.md)
and [`THIRD_PARTY_LICENSES.md`](https://github.com/Prekzursil/tracelines/blob/main/THIRD_PARTY_LICENSES.md).
