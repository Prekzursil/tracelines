# Changelog

The canonical, always-current changelog is
[`CHANGELOG.md`](https://github.com/Prekzursil/svcoverage/blob/main/CHANGELOG.md) in the repo.
Versioning is [SemVer](https://semver.org/) (pre-1.0 — the **GeoJSON schema + CLI flags are the
public API contract**), and each release notes the **upstream compatibility** it was tested against
(the Google provider depends on undocumented endpoints via `streetlevel`).

## 0.1.0 — 2026-07-13

Initial public release: multi-source (Google/Mapillary/KartaView) blue-line coverage extraction to
GeoJSON, the 3-layer HARD-RULE filter, CLI, self-hostable proxy, GUI, docs, and a reproducible
verification harness (7,433/7,433 official, 0 leaks).

**Upstream compatibility:** streetlevel 0.12.x · Mapillary `mly1_public` vector tiles v2 ·
KartaView 2.0 API (best-effort).
