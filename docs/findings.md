# Findings

Empirical + reverse-engineered facts the tool relies on. Each is tagged **[VERIFIED]** or
**[PLAUSIBLE]** and **date-stamped** — these describe undocumented behaviour observed on
**2026-07-13** and MAY change. This is a living log; see [Contributing](contributing.md) for how to
update a finding.

## The `source` taxonomy [VERIFIED · 2026-07-13]

From streetlevel's documentation and confirmed against live metadata:

| `source` | What it is | Rendered as | svcoverage default |
|----------|-----------|-------------|--------------------|
| `launch` | **regular car coverage** (sometimes trekker), **road-snapped** | solid blue lines | ✅ kept |
| `scout` | trekker / tripod (sometimes car), **not** road-snapped | blue lines | kept unless `--precision`; `--include-trekker` to force-keep |
| `innerspace` | Business View indoor tripods | — | dropped under `--precision` |
| `cultural_institute` | Arts & Culture tripods | — | dropped under `--precision` |
| `photos:*` | third-party uploads (`photos:street_view_android`, `photos:gmm_android`, …) | blue dots | **never** in output (Layers 0+1) |

**Key nuance:** the field encodes the **road-snapping pipeline**, not the physical platform, so
`launch` ⊋ car and `scout` ⊋ trekker. No metadata field cleanly separates car from trekker.

## Pano-id format [VERIFIED · 2026-07-13]

- Official ids are **22 URL-safe-base64 chars encoding 16 bytes**; the final char is one of
  `{A, Q, g, w}` (only 2 meaningful bits remain).
- Third-party ids: `CIHM…` / `CIAB…` (newer short UGC) / `AF1Q…` (longer). streetlevel's
  `is_third_party_panoid` = `startswith("CIHM0og") or len > 22` — necessary but not exhaustive;
  `svcoverage.is_official_panoid` is the stricter positive whitelist (see [Methodology](methodology.md)).

## Coverage-tile layer is official-only [VERIFIED · 2026-07-13]

A 49-tile / 7,433-pano sweep of central Bucharest returned **0** third-party panos. Photospheres at
the same coordinates were reachable **only** via `find_panorama(search_third_party=True)`. See
[Verification](verification.md).

## Multi-source comparison [VERIFIED endpoints · PLAUSIBLE density]

| Source | Line geometry | Reliability | Bucharest density | Output license |
|--------|--------------|-------------|-------------------|----------------|
| **Google** (streetlevel) | reconstructed from `links` graph | undocumented, unstable ids, may break | **highest** — Romania re-driven Mar 2025 | none (ToS) |
| **Mapillary** | **native** `sequence` LineStrings | documented Graph API v4, stable ids, Meta-backed | good arterials, patchier side-streets *(PLAUSIBLE)* | CC-BY-SA 4.0 |
| **KartaView** | polylines from bbox API | open but historically flaky | Telenav/Romania heritage *(PLAUSIBLE)* | CC-BY-SA 4.0 |

- There is **no reliable + ToS-clean Google path to lines for an EEA account**: the official Map
  Tiles API Street-View path is **contractually EEA-blocked** (effective 8 Jul 2025), and the 2D
  raster blue-line tiles carry no metadata and are barred from storage. streetlevel (ToS-gray) is
  the only route to Google *lines*. [VERIFIED]
- Run `svcoverage probe --bbox … --sources google,mapillary` to measure density for **your** bbox
  before relying on any single source.

## References / prior art

- **streetlevel** by [sk-zk](https://github.com/sk-zk/streetlevel) — the MIT library this stands
  on; source of the coverage-tile walk, `source` taxonomy, and the id classifier this project
  hardens.
- **matdoes.dev** Street View / pano-id write-ups — id-format and endpoint-flag details.
- Mapillary [API v4 docs](https://www.mapillary.com/developer/api-documentation) · KartaView
  [terms](https://kartaview.org/terms).

**Novelty of svcoverage:** the 3-layer *positive-whitelist* filter (`is_official_panoid` +
`source == launch` allowlist + connectivity), the reproducible 0-leak verification harness, and the
multi-source fusion + GUI — built on top of the prior work above.
