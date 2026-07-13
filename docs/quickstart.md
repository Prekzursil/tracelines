# Quickstart — your first extraction

From zero to a map of coverage in about two minutes. No API key needed for Google.

## 1. Install

```bash
pip install tracelines
```

## 2. Find the nearest blue line to a point

```bash
tracelines nearest 44.435072 26.050430
```

You'll get the nearest **official car** panorama — its id, capture date, distance, and a link that
opens it in Street View. It is **never** a photosphere.

## 3. Extract an area to GeoJSON

```bash
tracelines extract --bbox 26.09,44.45,26.11,44.46 --sources google --out coverage.geojson
```

`--bbox` is `west,south,east,north`. Or use a named area:

```bash
tracelines extract --area bucharest-city --sources google --out bucharest.geojson
```

Add `--precision` for pure car coverage (drops trekker/indoor; slower).

## 4. Look at it

Open the **[live GUI](https://prekzursil.github.io/tracelines/)** and **drag your `coverage.geojson`
onto the map**. Toggle sources, color by capture year, click a line to inspect it, or click the map
in **Nearest** mode to find the closest pano.

Prefer no install? The GUI's **"Full Bucharest"** button shows a whole city with zero setup.

## What next

- **[How the blue-line filter works (methodology)](methodology.md)** — the exact, testable rules.
- **[Reproduce the proof](verification.md)** — re-run the coverage sweep yourself.
- **[Live Google in the GUI](gui.md)** — deploy a tiny free proxy so the browser can extract Google too.
- **[What you may do with the output](data-provenance.md)** — per-source licensing.
