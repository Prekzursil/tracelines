# GUI

The **[cockpit on GitHub Pages](https://prekzursil.github.io/tracelines/)** is a static control
surface. Because Google extraction can't run in a browser (undocumented, CORS-blocked, Python-only),
the page is a *planner, viewer, and comparator* — not the engine.

## Source modes

The GUI has a **source-mode selector** — pick how each layer's data arrives:

| Mode | What it does | Needs |
|------|--------------|-------|
| **📂 Load file** | Drag & drop a `.geojson` the CLI produced; renders it on the map. | nothing (fully client-side; your file never leaves the browser) |
| **🛠️ Command builder** | Draw a bbox → get the exact `tracelines extract …` command with a Copy button. Run it locally, then drop the result back in. | the CLI, run locally |
| **🟢 Live Mapillary** | Draws Mapillary `sequence` coverage live on the map. | your own free [Mapillary token](https://www.mapillary.com/dashboard/developers) (stored only in your browser) |
| **🔵 Live Google (proxy)** | Live Google extraction via a backend **you** run. | the [self-hosted proxy](https://github.com/Prekzursil/tracelines/tree/main/server) + its URL |

## The cockpit loop

```
draw bbox  →  copy CLI command  →  run tracelines locally  →  drag the GeoJSON back in
          →  overlay live Mapillary / proxy Google  →  diff sources  →  export
```

That loop turns an inert viewer into the actual front-end of the tool, and delivers the one thing a
raw CLI can't: **visual multi-source comparison** — where does Google have coverage Mapillary lacks,
and vice-versa.

## Token & privacy

- Your **Mapillary token** is stored only in your browser's `localStorage`; it rides in Mapillary's
  own tile URLs (that's how their SDK works). Tokens are free, read-only, public-scope — exposure is
  a quota concern, not a data breach. Use your own.
- **Uploaded GeoJSON is parsed entirely client-side** — it never leaves your browser.
- To use **Live Google**, run the proxy yourself and lock its CORS to your GUI origin (see the
  [proxy README](https://github.com/Prekzursil/tracelines/tree/main/server)).

## Why not "just run Google in the browser"?

Google's coverage endpoints are undocumented internal APIs with **no CORS headers**, and the
`streetlevel` stack is Python (aiohttp + protobuf) — neither works under browser `fetch` or Pyodide.
The only way to get live Google in a GUI is the self-hosted proxy. See [Architecture](architecture.md).
