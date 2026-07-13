# Changelog

All notable changes to this project are documented here. Format follows
[Keep a Changelog](https://keepachangelog.com/); versioning is [SemVer](https://semver.org/)
(pre-1.0 — the **GeoJSON output schema and CLI flags are the public API contract**).

Each release notes the **upstream compatibility** it was tested against, because the Google
provider depends on undocumented endpoints via `streetlevel`.

## [Unreleased]

## [0.1.0] — 2026-07-13

Initial public release.

### Added
- Multi-source coverage extraction: Google (`streetlevel`), Mapillary (sequence vector tiles),
  KartaView (bbox polylines), fused to GeoJSON.
- **HARD RULE** — official car Street View only, never a photosphere — enforced in three
  defense-in-depth layers (coverage-tile-only source · `is_official_panoid` whitelist ·
  `source=='launch'` allowlist).
- CLI: `svcoverage nearest | extract | probe`.
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

[Unreleased]: https://github.com/Prekzursil/svcoverage/compare/v0.1.0...HEAD
[0.1.0]: https://github.com/Prekzursil/svcoverage/releases/tag/v0.1.0
