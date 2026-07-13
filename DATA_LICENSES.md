# Data provenance & output licensing

**`svcoverage`'s AGPL-3.0 license covers the _code_, not the _data you extract with it_.**
The coverage GeoJSON you generate carries the **source's** terms, and those differ per
source. This page is the honest matrix. It is not legal advice.

| Source | How it's fetched | Data license / terms | What you may do with the OUTPUT | Attribution required |
|--------|------------------|----------------------|---------------------------------|----------------------|
| **Google** (via `streetlevel`) | Undocumented internal coverage-tile / photometa endpoints. No API key. | **No clean redistribution license.** Google's Terms of Service prohibit scraping / bulk extraction of Street View. "A given road is covered" is arguably a fact (facts aren't copyrightable in the US), but ToS + database-rights angles make **bulk redistribution legally murky**. | **Generate for your own use.** Do **not** assume a right to publicly redistribute Google-derived coverage datasets. | n/a (don't redistribute) |
| **Mapillary** | Documented Graph API + `mly1_public` vector tiles. Needs a free token. | **CC-BY-SA 4.0** (imagery + derived data; explicitly licenses EU sui-generis database rights). Plus Mapillary's API terms. | Redistribute freely **with attribution + share-alike** (your redistributed dataset must also be CC-BY-SA 4.0). | **Yes** — "© Mapillary contributors, CC-BY-SA 4.0" |
| **KartaView** | Documented public bbox API. Keyless. | **CC-BY-SA 4.0.** | Redistribute freely **with attribution + share-alike**. | **Yes** — "© KartaView contributors, CC-BY-SA 4.0" |

## Practical guidance

- **This repository ships the _tool_, not pre-extracted datasets.** We deliberately do **not**
  commit bulk coverage data — especially not Google-derived data — to avoid becoming an
  unlicensed redistribution point. (A tiny Mapillary/KartaView demo fixture, if present, carries
  its CC-BY-SA notice.)
- **If you redistribute output:** a fused GeoJSON is only as clean as its *dirtiest* source.
  A layer containing **any** Google-derived geometry inherits Google's ToS problem; a layer of
  only Mapillary/KartaView data is redistributable under **CC-BY-SA 4.0 with attribution +
  share-alike**. The tool tags every segment with its `source`, so you can filter before you share.
- **The `source` property on every output feature is your provenance record** — keep it.

## Summary

- **Google output → yours to use, not yours to redistribute.**
- **Mapillary / KartaView output → redistributable under CC-BY-SA 4.0 (attribute + share-alike).**
- **The tool itself → AGPL-3.0-or-later, freely.**
