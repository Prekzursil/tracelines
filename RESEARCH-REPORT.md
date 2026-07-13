# Research Report — Bucharest-Metro Google Street View Continuous-Coverage Extractor

**Decision in one line:** Build a **Python asyncio CLI** that **walks Google's panorama-adjacency graph via `streetlevel`'s zoom-17 coverage tiles** (not blind metadata sampling), filters to official road coverage using the `is_third_party` + `source` fields, stitches link-connected runs into LineStrings, and exports GeoJSON — with OSMnx roads for seeding/labeling and `diskcache` for tile-level checkpoint/resume. **No MCP is the engine; a thin FastMCP wrapper is optional at the edges.** The core relies on Google's undocumented internal endpoints (ToS-gray) — this is unavoidable because the sanctioned API structurally cannot separate a blue line from a blue dot.

Confidence on the core mechanics is **high** (the `streetlevel` field/tile semantics are VERIFIED independently by 3 of the 4 research lenses against source code + docs); confidence on the metro-scale **call/runtime numbers is medium** (order-of-magnitude estimates, flagged below).

---

## 1. The Recommended Approach

### 1a. Crux resolved: WALK the pano graph, do not blind-sample

**Pick: (B) graph-walk, seeded by (A) road geometry.** The four lenses converge unanimously.

| Axis | (A) Blind road-sampling via official metadata API | (B) Walk the pano graph via `streetlevel` tiles |
|---|---|---|
| **Accuracy** | Returns boolean presence per point. **Structurally cannot** tell a continuous line from an isolated dot — no adjacency in the response. | The `links` array **is** the continuity graph: linked chain = blue line; degree-0 = blue dot. Official links graph excludes user content *by construction*. **Wins.** |
| **Call volume @ metro scale** | ~2,000–5,000 km drivable roads ÷ ~10–20 m spacing = **100k–500k** metadata calls, each yielding *no* links. | `get_coverage_tile` returns *many* panos + intra-tile links in **one** request; ~5k–45k z17 tiles (clipped to the road buffer). **~10–50× fewer calls AND strictly more information.** |
| **ToS/reliability** | Sanctioned, keyed, zero-quota, stable. But cannot produce the deliverable. | Undocumented internal endpoint (`photometa`/`GetMetadata`), no key, "may break unexpectedly," pano IDs not stable. **The real cost of the accuracy.** |

Approach A is not a genuine competitor — it can't distinguish line from dot at all (Google explicitly **declined** to add an official "filter unofficial coverage" option, [issuetracker 141726330](https://issuetracker.google.com/issues/141726330)). It is demoted to a **ToS-clean validation layer** (§3, §4).

**The concrete walk primitive (VERIFIED):** `streetlevel.streetview.get_coverage_tile(x, y)` / `get_coverage_tile_by_latlon(lat, lon)` fetches every pano on a Slippy/XYZ **zoom-17** tile in one call — the exact request Google Maps makes on satellite/globe zoom — returning `StreetViewPanorama` objects with id, position, elevation, orientation, and **intra-tile `links`**, including hidden/removed panos ordinary search misses ([readthedocs](https://streetlevel.readthedocs.io/en/stable/streetlevel.streetview.html); DeepWiki `sk-zk/streetlevel` `parse_coverage_tile_response`). Reference proof it works at scale: matdoes.dev's [Internet Roadtrip Pathfinder](https://matdoes.dev/internet-roadtrip-pathfinder) A\*-walks this exact graph and confirms it "doesn't include user-submitted panoramas."

### 1b. The official-vs-photosphere filter — exact fields and how to read them

Use **`streetlevel`** (`sk-zk/streetlevel`, MIT, v0.12.10 / 2026-06-11) — the **only** library found that natively exposes *both* the adjacency graph *and* the official/user discriminator ([GitHub](https://github.com/sk-zk/streetlevel) · [PyPI](https://pypi.org/project/streetlevel/)).

**Primary discriminators (VERIFIED from source):**

- **`StreetViewPanorama.is_third_party`** → `True` for user photospheres. Backed by `is_third_party_panoid(panoid) = panoid.startswith('CIHM0og') or len(panoid) > 22`; official IDs are exactly **22 chars** (URL-safe Base64), user IDs are 44-char `AF1Q…` legacy or 22–28-char `CI…`/`CIHM…` ([util.py](https://github.com/sk-zk/streetlevel/blob/master/streetlevel/streetview/util.py)). **Works on `get_coverage_tile` output with zero extra API calls** (it's computed from the ID).
- **`StreetViewPanorama.source`** → the road/off-road discriminator ([panorama.py docstrings](https://github.com/sk-zk/streetlevel/blob/master/streetlevel/streetview/panorama.py)):
  - `launch` = "regular car coverage whose lines are **snapped to roads**" ← **exactly the blue road lines**
  - `scout` = trekker/tripod, **not** road-snapped (trails/footpaths)
  - `innerspace` = Business View tripods (indoor); `cultural_institute` = Arts & Culture
  - user = `photos:street_view_android` / `_ios` / `_street_view_publish_api`
  - ⚠️ **Only populated by `find_panorama` / `find_panorama_by_id`, NOT by `get_coverage_tile`** — see two-tier filter below.
- **`find_panorama(..., search_third_party=False)`** → official-only search by default (internal image-type constant 2 vs 10).

**Corroborating (free) tells:** `copyright_message` (`© <year> Google` vs a username), `uploader` (`Google`), `date` precision (official = month/year only; third-party = full timestamp), and `street_names`/`address` ("typically only set for official road coverage").

**The combined keep-predicate for "blue line on a road":**

```
KEEP pano  IF  is_third_party == False                       # not a user photosphere
           AND degree_in_link_graph >= 1                     # part of a linked run (not an isolated dot)
           AND source in {"launch"}                          # car/road coverage  (add "scout" only if you want trekker trails)
DROP       IF  is_third_party == True                        # photospheres  → the "blue circles"
           OR  degree == 0                                   # isolated official OR user singletons → the "blue dots"
           OR  source in {"innerspace","cultural_institute"} # indoor/museum tripods
```

**Two-tier filter (the efficiency move):** because tiles don't carry `source`, run it in two passes —
1. **Cheap pass (no extra calls):** drop `is_third_party == True`, build the graph from intra-tile `links`, keep connected components ≥ 2. This already removes photospheres *and* isolated dots — and most non-road official coverage (indoor tripods tend to be degree-0/tiny clusters).
2. **Precision pass (per kept pano):** `find_panorama_by_id` to read `source` and confirm `launch`, and to resolve cross-tile boundary links. Only needed for panos you keep, and primarily boundary panos — bounding the per-pano call count.

This is the exact fix for the reported bug: the metadata API's `status: OK` fires for any pano; `is_third_party` + `source` + `links` are three independent signals it never exposes.

---

## 2. The MCP Answer — script is the right tool; MCP only at the edges

**Honest verdict: do NOT build the engine as an MCP.** MCP is synchronous JSON-RPC request/response with per-call agent context and **no native long-running-job, progress-streaming, or checkpoint/resume semantics** — precisely the four things a multi-hour, tens-of-thousands-of-requests city crawl needs. Build a **Python CLI** (Typer/argparse + asyncio). ([FastMCP tool model](https://gofastmcp.com/getting-started/welcome).)

**No existing Maps/Street-View MCP solves this.** Anthropic's `google-maps` MCP, Google's Maps Grounding Lite, and community servers (`Garblesnarff/google-maps-mcp`, `cablate/mcp-google-map`) all wrap the **official** places/routes/pano-image APIs — none expose the `links` adjacency, the `source` flag, or coverage polylines. They inherit the official API's line-vs-dot blindness. Use one *at most* to geocode "Bucharest Metropolitan Area" to a bbox. ([pulsemcp google-maps](https://www.pulsemcp.com/servers/modelcontextprotocol-google-maps) · [Grounding Lite MCP](https://developers.google.com/maps/ai/grounding-lite/reference/mcp).)

**OSM/Overpass MCPs exist but are the wrong tool for the batch roads stage.** `cyanheads/openstreetmap-mcp-server` can run raw Overpass QL, but piping a whole-metro road graph (tens of MB) through an MCP tool-call into agent context is impractical and defeats caching. Use **OSMnx directly** (§3). ([NERVsystems/osmmcp](https://github.com/NERVsystems/osmmcp) · [cyanheads](https://github.com/cyanheads/openstreetmap-mcp-server).)

**Optional wrap-as-MCP-later (adds real value only after the CLI exists):** a thin **FastMCP** server ([PrefectHQ/fastmcp](https://github.com/PrefectHQ/fastmcp)) exposing two tools — (a) *enqueue a run, return a `job_id`* (poll a status tool), and (b) *serve already-computed GeoJSON for a bbox from the on-disk cache*. **Never** make an MCP tool block on a full crawl (it will time out). This is a convenience layer for agent-callability, not the architecture.

---

## 3. Concrete Build Plan

### Pipeline (ordered stages)

| # | Stage | Tool / Endpoint | What it does |
|---|---|---|---|
| 1 | **Roads** | **OSMnx** — `ox.geocode_to_gdf('Bucharest, Romania')` (tune `which_result`; **union Bucharest municipiu + Ilfov** for the true metro) → `ox.graph_from_polygon(poly, network_type='drive')`; `custom_filter='["highway"]["name"]'` for named roads only ([OSMnx ref](https://osmnx.readthedocs.io/en/stable/user-reference.html)) | Defines the AREA polygon, seeds the walk, and provides centerline geometry + road names for snapping/labeling. Cache the Overpass fetch. |
| 2 | **Enumerate (bulk)** | **`streetlevel.get_coverage_tile_by_latlon`** over the **z17 tile grid clipped to a ~25 m buffer of the road network** (skips empty rural Ilfov tiles) | One request per ~0.03–0.05 km² tile returns all official panos + intra-tile links. Deterministic `(z,x,y)` keys → trivial cache/checkpoint. |
| 3 | **Filter (2-tier)** | `is_third_party` (cheap, from ID) → drop photospheres + require component ≥2; then **`find_panorama_by_id`** on kept/boundary panos for `source == 'launch'` + cross-tile links | Removes the "blue dots" (user photospheres + isolated official tripods) and non-road official coverage. |
| 4 | **Stitch** | **networkx** (panoid nodes, `links` edges) → drop `degree==0` isolates → split components at junctions (degree>2) into simple chains → **shapely `line_merge`** the ordered per-edge segments ([shapely line_merge](https://shapely.readthedocs.io/en/stable/reference/shapely.line_merge.html)) | Turns adjacency directly into blue-line-vs-blue-dot; `line_merge` joins endpoint-sharing segments into maximal polylines. Prune long "teleport" edges (search-vs-actual coord divergence, per matdoes.dev). |
| 5 | **Snap (optional)** | **shapely** `project`/`interpolate` + **geopandas** `sjoin_nearest` to OSM drive edges; `segmentize()` to densify long ways first | Emits polylines *on* the road centerline (publication-quality) and enables "% of way X covered" metrics. Mis-snaps at interchanges → keep a snap tolerance ~10–25 m. |
| 6 | **Output** | **geopandas** `GeoDataFrame.to_file('bucharest_sv_lines.geojson', driver='GeoJSON')` in **EPSG:4326**; reproject to **EPSG:3844 (Stereo70)** for `length_m` ([geopandas to_file](https://geopandas.org/en/stable/docs/reference/api/geopandas.GeoDataFrame.to_file.html)) | One feature per continuous run with `pano_ids`, `source`, min/max `date`, `length_m`, OSM `way_id`. Keep excluded dots as a separate QA layer. |

### Concurrency / cache / resume machinery

- **Concurrency:** `streetlevel`'s `*_async` variants take an `aiohttp.ClientSession`; fan out under an `asyncio.Semaphore(8–16)` with **jittered exponential backoff**; realistic UA; **pin the streetlevel version**.
- **Cache:** **`diskcache`** (Grant Jenks — pure-Python SQLite+FS, survives restarts, `FanoutCache` for multi-process) keyed by `(z,x,y)` for tiles and `pano_id` for per-pano fetches ([diskcache docs](https://grantjenks.com/docs/diskcache/)). Collapses re-runs to near-zero network. **TTL/version the cache per campaign** — pano IDs are not stable across months.
- **Checkpoint/resume:** treat the **tile as the unit of work**. Persist a `done_tiles` set; on restart, skip done tiles. Spool raw panos incrementally (SQLite/JSONL/GeoParquet) so a crash never loses fetched work — graph-build + stitch + export are **pure functions** over that store, re-runnable cheaply. `tqdm` over the tile queue for a city-scale ETA. (Pattern proven by matdoes.dev's tile-snapped LMDB cache.)

### Fixing `check_street_view_availability(lat, lng, KEY)`

Two levels:

1. **Minimal ToS-clean patch (keep the official API):** add `&source=outdoor` to the request — Google: *"PhotoSpheres are not returned because it is unknown whether they are indoors or outdoors"* ([SV metadata docs](https://developers.google.com/maps/documentation/streetview/metadata)). One-line change; **kills the photosphere false-positives** that are the stated bug. But it still returns nearest-pano boolean presence — **no `links`, no line-vs-dot**.
2. **Real fix (the deliverable):** **retire the boolean check as the coverage detector.** Replace it with the §3 pipeline (tile-enumerate → `is_third_party`/`source`/`links` filter → stitch). The metadata API (with `source=outdoor`) survives only as an **optional ToS-clean cross-check** on a sample of kept panos (confirm `copyright == '© … Google'`, `date` present) — free, zero-quota, 30,000 QPM.

### Reuse disposition (don't reinvent)

- **Reuse:** `streetlevel` (harvest + filter + links), OSMnx (roads), networkx + shapely + geopandas (stitch/export), diskcache (cache/resume). Study **`stiles/streetview-dl`** as a working BFS-over-`links` + parallel-batch pattern (verify its license before copying) ([GitHub](https://github.com/stiles/streetview-dl)).
- **Avoid:** `robolyst/streetview` (no `links`, no official/user split — would reproduce your exact bug); **SUTD google-streetview-gis-stack** and **USE-SVI** (both embody the metadata-OK-counts-photospheres defect + point/CSV output). Useful only as OSM-sampling scaffolding, never for coverage logic ([SUTD](https://github.com/sutd-visual-computing-group/google-streetview-gis-stack) · [USE-SVI](https://github.com/iuriabetco/USE-SVI)).
- **The genuine gap (build it yourself):** no off-the-shelf tool produces official-coverage GeoJSON LineStrings end-to-end — the stitch stage is bespoke (small: networkx `connected_components` + `line_merge`).

---

## 4. Honest Caveats

- **This is a RECONSTRUCTION.** Google does **not** publish the blue-line vector data and won't add an official filter ([issuetracker 141726330](https://issuetracker.google.com/issues/141726330)). Your polylines are reconstructed from pano nodes + `links` — an approximation of what Google renders, not ground truth.
- **ToS / fragility (the core risk, medium-high):** `streetlevel` wraps Google's **undocumented internal** `photometa`/`GetMetadata` endpoints — no key, but the maintainer warns it "may break unexpectedly," pano IDs aren't stable, and bulk use is a **ToS gray area with non-zero block risk and no SLA** ([streetlevel README](https://github.com/sk-zk/streetlevel)). Mitigate: pin the version, cache aggressively, cap concurrency + jittered backoff, keep the official API as a ToS-clean fallback. There is a hard reliability ceiling here — accept it or restrict to the (insufficient) official API.
- **Rate limits:** official metadata API = **no charge, no quota consumed, 30,000 QPM** ([docs](https://developers.google.com/maps/documentation/streetview/metadata)) — safe for cross-checks. `streetlevel`'s internal endpoints have **no documented limit → self-police** (moderate concurrency, don't hammer). matdoes.dev notes cookie reuse for higher throughput — *more* ToS-risky; avoid unless necessary.
- **Realistic scale estimate (medium confidence — order-of-magnitude):** Bucharest core ~240 km² → **~6k z17 tiles**; full Bucharest+Ilfov metro ~1,821 km² → **~45k tiles**, reduced by road-buffer clipping to perhaps **~5k–30k effective tile fetches**, plus per-boundary-pano `find_panorama_by_id` (**tens of thousands** in the worst case). **Total order 10⁴–10⁵ requests.** At a polite ~5–10 req/s that's **~20 min to a few hours** for a cold run; cached re-runs are near-instant. (The undocumented **batch `GetMetadata` RPC, ~200 pano IDs/call** — PLAUSIBLE, single-source [matdoes.dev] — would collapse the cross-tile enrichment from N to N/200 but needs raw protobuf and adds ToS/brittleness. Treat as an optimization, not a dependency.)
- **Filter accuracy limits:** `source` is occasionally mistagged (`launch`↔`scout` — docstring hedges "and sometimes"), so strict `launch`-only can miss a few genuine road runs. The `is_third_party` ID-length heuristic is a strong convention, **not a documented Google guarantee**, and Google is mid-transition to the `CI…` ID scheme → treat as corroboration, spot-verify a sample. Snap-to-OSM mis-snaps at dense parallel roads/interchanges. `get_coverage_tile` returns **most-recent coverage only** (no historical).
- **Coordinate gotcha:** link coords are road-snapped "search" coords that can diverge from actual GPS → prune long teleport edges, or you'll draw spurious cross-town segments (matdoes.dev).

---

## 5. Open Decisions for the User (resolve before building)

1. **Metro boundary — biggest scale lever (~8×):** Bucharest **municipiu only** (~240 km², ~6k tiles) or the **true metropolitan area = Bucharest + Ilfov county** (~1,821 km², ~45k tiles)? (No single canonical OSM boundary — expect to tune `which_result` / union.)
2. **`launch`-only vs `launch`+`scout`:** roads only, or also include **trekker trails / pedestrian paths** that *also* render as blue lines on Google Maps?
3. **ToS posture (the fundamental tradeoff):** accept `streetlevel`'s ToS-gray internal endpoints (**required** for the line-vs-dot distinction), or restrict to the **sanctioned API** (which can only exclude photospheres via `source=outdoor` and **cannot** build continuous polylines)? A third option shifts the Google-ToS exposure off you entirely: **sv-map** ([sv-map.netlify.app](https://sv-map.netlify.app/dataset)) republishes Google's *actual rendered blue-line layer* as PMTiles rasters daily — zero Google API calls, photospheres excluded by construction — but it's **raster** (skeletonize → approximate centerline, no pano/date/direction metadata). Good as a **cross-check or quick first pass**, not the precise deliverable.
4. **Output geometry:** raw pano-coordinate LineStrings (faithful to captured GPS) or **snapped-to-OSM-centerline** polylines (cleaner, road-attributed, but adds mis-snap risk at interchanges)?
5. **Minimum-run policy:** what counts as a "line" — **≥2 linked panos**, or a higher threshold to suppress micro-runs?
6. **Temporal scope:** current most-recent coverage (default) sufficient, or is **multi-date/historical** needed (requires per-pano historical fetches, not tiles)?
7. **Agent-callability:** ship the **CLI only**, or add the optional **FastMCP** wrapper (job-trigger + cached-GeoJSON query) for later agent use?

---

### Source ledger (most load-bearing)

- **VERIFIED** — `streetlevel` `get_coverage_tile`, `links`, `source`, `is_third_party`: [readthedocs](https://streetlevel.readthedocs.io/en/stable/streetlevel.streetview.html) · [panorama.py](https://github.com/sk-zk/streetlevel/blob/master/streetlevel/streetview/panorama.py) · [util.py](https://github.com/sk-zk/streetlevel/blob/master/streetlevel/streetview/util.py) · DeepWiki `sk-zk/streetlevel`
- **VERIFIED** — official API `source=outdoor` excludes photospheres, zero-quota, no official filter: [SV metadata docs](https://developers.google.com/maps/documentation/streetview/metadata) · [issuetracker 141726330](https://issuetracker.google.com/issues/141726330)
- **VERIFIED** — working graph-walk at scale + cache/coordinate pitfalls: [matdoes.dev Internet Roadtrip Pathfinder](https://matdoes.dev/internet-roadtrip-pathfinder)
- **VERIFIED** — roads/stitch/output/cache libs: [OSMnx](https://osmnx.readthedocs.io/en/stable/user-reference.html) · [shapely line_merge](https://shapely.readthedocs.io/en/stable/reference/shapely.line_merge.html) · [geopandas to_file](https://geopandas.org/en/stable/docs/reference/api/geopandas.GeoDataFrame.to_file.html) · [diskcache](https://grantjenks.com/docs/diskcache/)
- **PLAUSIBLE** (single-source) — batch `GetMetadata` ~200 IDs/call: matdoes.dev, loosely corroborated by [tgrcode reverse-engineering writeup](https://tgrcode.com/posts/reverse_engineering_google_streetview)
- **Estimate (medium confidence)** — z17 tile counts & 10⁴–10⁵ request volume: my order-of-magnitude math over ~240 km² / ~1,821 km²; native ~10 m pano spacing from [StreetLearn (arXiv 1903.01292)](https://arxiv.org/pdf/1903.01292).