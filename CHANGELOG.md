# Changelog

All notable changes to this project are documented here. Format follows
[Keep a Changelog](https://keepachangelog.com/); versioning is [SemVer](https://semver.org/)
(pre-1.0 — the **GeoJSON output schema and CLI flags are the public API contract**).

Each release notes the **upstream compatibility** it was tested against, because the Google
provider depends on undocumented endpoints via `streetlevel`.

## [Unreleased]

## [0.2.0] — 2026-07-14

### Changed
- **Renamed the project from `svcoverage` to `tracelines`** (package, CLI, PyPI, repo, Pages URL).
- The proxy moved into the package as `tracelines.proxy:app` (pip-installable).

### Added
- **GUI, greatly expanded** — click-map → nearest official pano (+ "open in Street View"), a
  historical time-slider, click-a-line inspector, color/filter by capture year, a place search
  (Nominatim), a satellite basemap + opacity, a "Probe view" readout, and a one-click
  **"Full Bucharest"** layer (52k committed lines, ~0.8 MB gzipped).
- **Proxy**: `/historical` endpoint (past captures for the time-slider), a `streetview_url` on
  `/nearest`, and hardening — per-IP rate limit + a kill switch (`TRACELINES_DISABLED`).
- **Free-host proxy**: a live hosted demo backend (Google Cloud Run) wired as the GUI default, plus
  a one-click **[Deploy to Render](render.yaml)** blueprint (no credit card) to run your own.
  (A Hugging Face Space is still in `spaces/`, but HF now requires PRO to host Docker Spaces.)
- **Beginner docs** — an "Explain like I'm 5" page, a Coverage 101, and a Quickstart, in a new
  "Start here" section (the rigorous pages moved under "Reference").
- `tracelines.nearest.build_streetview_url` (keyless Street View deep links).

### Upstream compatibility
- `streetlevel` 0.12.x · Mapillary `mly1_public` vector tiles v2 · KartaView 2.0 API (best-effort).

## [0.1.0] — 2026-07-13

Initial public release.

### Added
- Multi-source coverage extraction: Google (`streetlevel`), Mapillary (sequence vector tiles),
  KartaView (bbox polylines), fused to GeoJSON.
- **HARD RULE** — official car Street View only, never a photosphere — enforced in three
  defense-in-depth layers (coverage-tile-only source · `is_official_panoid` whitelist ·
  `source=='launch'` allowlist).
- CLI: `tracelines nearest | extract | probe`.
- Async pipeline with `diskcache` resume + concurrency; shapely `line_merge` stitching;
  cross-source fusion with optional spatial dedup.
- Self-hostable FastAPI proxy backend (`server/`) for live extraction behind the GUI.
- Static GitHub Pages GUI: viewer + command-builder + live Mapillary + proxy mode + coverage diff.
- MkDocs-Material documentation site; reproducible HARD-RULE verification (`scripts/verify_hardrule.py`).

### Verified
- 7,433 / 7,433 z17 coverage-tile panos over central Bucharest were official, 0 third-party
  (2026-07-13 snapshot; `scripts/verify_hardrule.py` re-asserts the 0-leak invariant on live data).
- `is_official_panoid`: 753/753 real official ids accepted, 3/3 real photospheres rejected.

### Upstream compatibility
- `streetlevel` 0.12.x · Mapillary `mly1_public` vector tiles v2 · KartaView 2.0 API (best-effort).

[Unreleased]: https://github.com/Prekzursil/tracelines/compare/v0.1.0...HEAD
[0.1.0]: https://github.com/Prekzursil/tracelines/releases/tag/v0.1.0
