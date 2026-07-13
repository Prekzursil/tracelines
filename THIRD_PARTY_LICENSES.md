# Third-party licenses

`svcoverage` is licensed under **AGPL-3.0-or-later** (see `LICENSE`). It builds on the
following third-party libraries, whose licenses are reproduced or referenced below. All
are permissive and compatible with AGPL-3.0.

The single most load-bearing dependency is **streetlevel** — it performs the actual Google
Street View coverage-tile walking that this project's Google provider is built on. Full
credit and thanks to its author.

---

## streetlevel — MIT License

- Project: <https://github.com/sk-zk/streetlevel>
- Author: **sk-zk**
- Used for: Google Street View coverage tiles, panorama metadata, and the pano-id classifier
  that `svcoverage`'s Google provider and `is_official_panoid` whitelist build upon.

```
MIT License

Copyright (c) sk-zk

Permission is hereby granted, free of charge, to any person obtaining a copy
of this software and associated documentation files (the "Software"), to deal
in the Software without restriction, including without limitation the rights
to use, copy, modify, merge, publish, distribute, sublicense, and/or sell
copies of the Software, and to permit persons to whom the Software is
furnished to do so, subject to the following conditions:

The above copyright notice and this permission notice shall be included in all
copies or substantial portions of the Software.

THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE
AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER
LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM,
OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN THE
SOFTWARE.
```

*(The above is the standard MIT text; the authoritative copy ships with the streetlevel
package and repository.)*

---

## Other runtime dependencies

| Library | License | Author | Used for |
|---------|---------|--------|----------|
| [shapely](https://github.com/shapely/shapely) | BSD-3-Clause | Sean Gillies et al. | geometry, `line_merge` stitching |
| [networkx](https://github.com/networkx/networkx) | BSD-3-Clause | Aric Hagberg et al. | pano adjacency graph |
| [aiohttp](https://github.com/aio-libs/aiohttp) | Apache-2.0 AND MIT | aio-libs | async HTTP for tile fetching |
| [diskcache](https://github.com/grantjenks/python-diskcache) | Apache-2.0 | Grant Jenks | resumable tile cache |
| [mapbox-vector-tile](https://github.com/tilezen/mapbox-vector-tile) | MIT | Rob Marianski et al. | Mapillary MVT decode (`[mapillary]` extra) |

Optional extras (`[snap]`, `[server]`) pull in osmnx (MIT), geopandas (BSD-3), pyproj
(MIT), FastAPI (MIT), and uvicorn (BSD-3) — all permissive.

The browser GUI bundles **MapLibre GL JS** (BSD-3-Clause) and **Protomaps / PMTiles**
(BSD-3-Clause); their notices are retained in the GUI source.
