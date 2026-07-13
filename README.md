<div align="center">

# tracelines

**Extract the blue lines, never the circles.**

Turn an area into GeoJSON polylines of *continuous official street-level coverage* — the solid
blue Street View lines — while rigorously excluding user photospheres / photopets (the dots).
Multi-source: **Google** (via [streetlevel](https://github.com/sk-zk/streetlevel)),
**Mapillary**, and **KartaView**, fused onto one map.

[![CI](https://github.com/Prekzursil/tracelines/actions/workflows/ci.yml/badge.svg)](https://github.com/Prekzursil/tracelines/actions/workflows/ci.yml)
[![PyPI](https://img.shields.io/pypi/v/tracelines.svg)](https://pypi.org/project/tracelines/)
[![Python](https://img.shields.io/pypi/pyversions/tracelines.svg)](https://pypi.org/project/tracelines/)
[![License: AGPL v3](https://img.shields.io/badge/license-AGPL--3.0-blue.svg)](LICENSE)
[![Docs](https://img.shields.io/badge/docs-mkdocs-blue.svg)](https://prekzursil.github.io/tracelines/docs/)
[![GUI](https://img.shields.io/badge/GUI-GitHub%20Pages-brightgreen.svg)](https://prekzursil.github.io/tracelines/)

**[🗺️ Live GUI](https://prekzursil.github.io/tracelines/) · [📖 Documentation](https://prekzursil.github.io/tracelines/docs/) · [🔬 How the HARD RULE works](https://prekzursil.github.io/tracelines/docs/methodology/) · [✅ Reproduce the verification](https://prekzursil.github.io/tracelines/docs/verification/)**

</div>

---

> **Disclaimer.** Research / educational tool, provided **as-is, without warranty**. The Google
> provider relies on **undocumented internal endpoints (via streetlevel) that may break without
> notice**. **You** are responsible for complying with each data source's Terms of Service and
> your local law. **Respect rate limits** — don't hammer the endpoints. Not affiliated with or
> endorsed by Google, Meta/Mapillary, or KartaView.

## The HARD RULE

> Output contains **only genuine official Google car Street View coverage** — never a user
> photosphere / photopet / photo-path, **even a Google-hosted one.**

Enforced in **three defense-in-depth layers** (each verified — see
[the filter contract](https://prekzursil.github.io/tracelines/docs/methodology/) and
[verification](https://prekzursil.github.io/tracelines/docs/verification/)):

| Layer | Guard | Stops |
|------|-------|-------|
| **0 — Source** | Nodes come *only* from the z17 `get_coverage_tile` layer; never `search_third_party`. | Photospheres are structurally absent there. **Verified: 7,433 / 7,433 tile panos official (2026-07-13 snapshot; the count drifts as Google updates coverage, the 0-leak invariant does not — re-check with `scripts/verify_hardrule.py`).** |
| **1 — ID whitelist** | `is_official_panoid()`: 22 chars, 16-byte decode, terminal ∈ `{A,Q,g,w}`, not `CIHM/CIAB/AF1Q`. | Legacy 22-char photospheres + the new `CIAB` UGC scheme. **Verified: 753/753 official accepted, 3/3 photospheres rejected.** |
| **2 — Source allowlist** (`--precision`) | `source == 'launch'` (car), fetched per-pano. | Trekker (`scout`), indoor (`innerspace`), every `photos:*` upload. |

**Honest caveat:** `launch` is the road-snapped layer Google draws as solid blue lines; Google's own
metadata says `launch` is *"sometimes trekker"* and `scout` is *"sometimes car"* — so no field
perfectly separates car from trekker. That fuzz is **orthogonal** to the photosphere exclusion,
which is airtight.

## Install

```bash
pip install tracelines            # Google-capable out of the box (no API key)
pip install "tracelines[mapillary]"   # + Mapillary vector-tile source
pip install "tracelines[all]"     # + Mapillary + OSM road-snapping
```

Optional env vars: `MAPILLARY_TOKEN` (free, for the Mapillary source); `MAPS_API_TOKEN`
(optional Google metadata enrichment — not required).

## Quickstart

```bash
# Nearest official car coverage to a point (never a photosphere)
tracelines nearest 44.435072 26.050430

# Extract blue lines over an area -> GeoJSON
tracelines extract --area bucharest-city --sources google --out bucharest.geojson
tracelines extract --bbox 26.09,44.45,26.11,44.46 --sources google,mapillary --out out.geojson

# Pure car only (drops trekker/indoor; slower, one metadata call per pano)
tracelines extract --area bucharest-city --sources google --precision --out cars.geojson

# Density probe: covered km / segments / median year per source
tracelines probe --bbox 26.09,44.45,26.11,44.46 --sources google,mapillary
```

```python
from tracelines import Settings, AREAS
from tracelines.pipeline import extract
from tracelines.export import write_geojson, summary_stats

segments, meta = extract(AREAS["bucharest-city"], ["google"], Settings())
write_geojson(segments, "bucharest.geojson")
print(summary_stats(segments))
```

## The GUI

A static **[cockpit on GitHub Pages](https://prekzursil.github.io/tracelines/)** — because the
Google extraction can't run in a browser (undocumented, CORS-blocked, Python-only), the page is a
*control surface*, not the engine:

- **View** any GeoJSON the CLI produced (drag & drop) on an interactive map.
- **Build a command** — draw a bbox, copy the exact `tracelines extract …` command.
- **Live Mapillary** overlay (paste your own free token — stored only in your browser).
- **Live Google** *if* you run the optional [self-hostable proxy](server/) and point the GUI at it.
- **Diff** sources — where does Google have coverage Mapillary lacks, and vice-versa.

## Sources & what you may do with the output

| Source | Live in browser? | Output license |
|--------|------------------|----------------|
| Google (streetlevel) | ❌ (CLI or self-hosted proxy) | No redistribution license — generate for yourself ([details](DATA_LICENSES.md)) |
| Mapillary | ✅ (your token) | CC-BY-SA 4.0 (attribute + share-alike) |
| KartaView | ✅ best-effort | CC-BY-SA 4.0 (attribute + share-alike) |

See **[DATA_LICENSES.md](DATA_LICENSES.md)** — the AGPL license covers the *code*, not the *data you extract*.

## How it works

```
bbox → z17 tile enumerate → async fetch (cached, concurrent)
     → Layer-1 official-id whitelist → panoid graph (links = edges)
     → [--precision] source=='launch' allowlist
     → shapely line_merge (splits at junctions) → CoverageSegments
   Mapillary sequence tiles ─┐
   KartaView bbox polylines ─┴→ fuse (union + provenance) → GeoJSON
```

Full internals: **[Architecture](https://prekzursil.github.io/tracelines/docs/architecture/)**.

## Documentation

- **[Methodology / Filter contract](https://prekzursil.github.io/tracelines/docs/methodology/)** — the HARD RULE as a normative (RFC-2119) contract.
- **[Verification](https://prekzursil.github.io/tracelines/docs/verification/)** — reproduce the 7,438-pano sweep yourself.
- **[Data provenance & licensing](https://prekzursil.github.io/tracelines/docs/data-provenance/)**.
- **[Output schema](https://prekzursil.github.io/tracelines/docs/output-schema/)** — the GeoJSON contract.
- **[API reference](https://prekzursil.github.io/tracelines/docs/api/)**.

## Development

```bash
pip install -e ".[dev]"
pytest                 # hermetic tests (no network)
pytest -m network      # live tests (hit Google/Mapillary)
ruff check tracelines tests
python scripts/verify_hardrule.py    # re-run the HARD-RULE sweep
```

## Acknowledgements

- **[streetlevel](https://github.com/sk-zk/streetlevel)** by **sk-zk** — the MIT library this stands on; it does the actual Google coverage-tile walking.
- **[matdoes.dev](https://matdoes.dev/)** Street View / pano-id write-ups — invaluable for the id taxonomy.
- **Mapillary** and **KartaView** for open, documented street-level APIs.

## License

**AGPL-3.0-or-later** — see [LICENSE](LICENSE). If you run a modified version as a network service
(e.g. the proxy backend), the AGPL requires you to share your source. Third-party notices in
[THIRD_PARTY_LICENSES.md](THIRD_PARTY_LICENSES.md).
