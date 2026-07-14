# Security Policy

## Supported Versions

Security fixes are applied to the `main` branch and released to PyPI/npm. This project is
pre-1.0 (the GeoJSON output schema and CLI flags are the public API contract), so only the
latest published `0.x` release and `main` are supported.

| Version | Supported |
| --- | --- |
| Latest `0.x` release + `main` | :white_check_mark: |
| Older releases / other branches/tags | :x: |

## Reporting a Vulnerability

Please do **not** open public GitHub issues for undisclosed security findings.

Use GitHub Private Vulnerability Reporting for this repository:
<https://github.com/Prekzursil/tracelines/security/advisories/new>

If private advisory reporting is unavailable, contact the maintainer privately on GitHub
(`@Prekzursil`).

When reporting, include:

- the affected component, file, proxy endpoint, CLI command, or dependency
- the exact commit, branch, or release if known
- clear reproduction or proof-of-concept steps
- impact details covering confidentiality, integrity, or availability
- any suggested mitigation if known

## Scope

In scope:

- first-party code in `tracelines/` (extraction engine and the FastAPI proxy `proxy.py`),
  `npm/` (the Node CLI), and `web/` (the static GUI)
- the self-hostable proxy and its hardening controls
- the CI/release workflows under `.github/workflows/`
- the packaging metadata (`pyproject.toml`, `npm/package.json`)

Out of scope (report upstream instead):

- vendored/third-party dependencies (e.g. `streetlevel`, `shapely`, `aiohttp`, FastAPI,
  MapLibre) — report to the upstream project
- the use of Google's undocumented coverage endpoints — this is the tool's documented
  research nature, not a vulnerability (see the README disclaimer)
- findings that require already-compromised local credentials or an already-root host
- abuse of a **self-hosted** proxy deployed without the shipped hardening
  (`TRACELINES_MAX_BBOX_DEG2`, `TRACELINES_RATE_PER_MIN`, `TRACELINES_DISABLED` kill switch)

## Disclosure Expectations

- Initial acknowledgment: best effort within 3 business days.
- Triage update: best effort within 7 business days.
- Coordinated disclosure is expected; please allow time to investigate and patch before
  public disclosure.

## Security Gates

Every change to `main` passes CI: lint + format (`ruff`), a cross-platform test matrix
(Python 3.10–3.13 on Linux/Windows/macOS), and a `mypy` type gate. Secrets must never be
hardcoded — the proxy reads all tokens (`MAPILLARY_TOKEN`, `MAPS_API_TOKEN`, …) from
environment variables, and the public demo proxy ships hardened (bbox cap, per-IP rate
limit, and a `TRACELINES_DISABLED` kill switch).
