# tracelines (CLI)

A tiny, **zero-dependency** command-line client for
[tracelines](https://github.com/Prekzursil/tracelines) — find the nearest **official** Street View
car coverage (never a photosphere), list historical captures, and extract coverage to GeoJSON, all
through the hosted proxy. No Python needed.

```bash
npx tracelines nearest 44.435072 26.050430
# → Ui8V1HlfwJBw8pnmoShJfw  launch  2024-07  65.1m  (third-party: false)
#   https://www.google.com/maps/@?api=1&map_action=pano&pano=Ui8V1HlfwJBw8pnmoShJfw
```

## Commands

```
tracelines nearest <lat> <lon> [--trekker]
tracelines historical <lat> <lon>
tracelines extract (--bbox W,S,E,N | --area NAME) [--sources google,mapillary] [--precision] [--out file.geojson]
tracelines probe --bbox W,S,E,N [--sources google]
tracelines health
```

Options: `--proxy <url>` (or env `TRACELINES_PROXY`; defaults to the hosted demo) · `--json` ·
`-h/--help` · `-v/--version`. Requires **Node ≥ 18** (uses the built-in `fetch`).

## The default proxy is a shared demo

The default endpoint is the hosted demo proxy — **hardened and rate-limited**, it may sleep or cap
the bbox size, and it extracts Google from a shared IP (a ToS gray area). For real work, run your
own and point at it:

```bash
TRACELINES_PROXY=https://your-proxy npx tracelines extract --bbox 26.09,44.45,26.11,44.46 --out out.geojson
```

See **[Deploy your own proxy (free)](https://github.com/Prekzursil/tracelines#deploy-your-own-proxy-free)**.

The **HARD RULE** holds everywhere: output is only genuine official car coverage — never a
photosphere/photopet. Prefer pure, reproducible extraction? Use the
[Python package](https://pypi.org/project/tracelines/) (`pip install tracelines`), which runs the
engine locally instead of via a proxy.

## License

AGPL-3.0-or-later.
