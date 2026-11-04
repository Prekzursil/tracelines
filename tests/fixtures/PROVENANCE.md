# Fixture provenance

Every fixture below is consumed by the hermetic (offline) test suite; no test in
this directory reaches the network. Provenance is recorded per fixture so a
future change in an upstream payload shape can be re-verified against reality.

Re-recording: `python tests/fixtures/record_fixtures.py` (manual, network-bound;
it is NOT run by the suite).

| fixture | provenance |
| --- | --- |
| `google/coverage_tile_z17_75020_47439.json` | **Recorded live** 2026-11-03: z17 coverage tile (75020, 47439) over central Bucharest (the module's documented verification area), fetched keyless from the `maps/photometa` coverage-tile endpoint that `streetlevel.get_coverage_tile` wraps, then parsed with `streetlevel`'s own `parse_coverage_tile_response`. Stored as the minimal records the provider consumes: `id` / `lat` / `lon` / `is_third_party` / intra-tile `links` (first 60 panos of 70 returned; 100% official ids, 0 third-party — matching the module's 2026-07-13 verification note). |
| `google/pano_by_id_launch_2024-07.json` | **Recorded live** 2026-11-03: by-id photometa for the first pano of the tile above (`hAEaX_IkDkSHntm9ydu--Q`) — source `launch`, date `2024-07`, 2 links, 10 historical entries. Stored as the minimal record `find_panorama_by_id` consumers read: `id`/`lat`/`lon`/`source`/`date`/`links`/`historical`. |
| `mapillary/sequence_z14_9410_5967.pbf` | **Constructed** to the documented `tiles.mapillary.com/maps/vtp/mly1_public/2` `sequence`-layer schema (layer name `sequence`, extent 4096, y-up, properties `id`/`is_pano`/`captured_at`, LineString geometry). The live endpoint requires a private access token, so raw capture was not possible; the tile is encoded with `mapbox_vector_tile` — the same library the provider decodes with — and round-trips through `decode_sequence_tile` (asserted by the test that consumes it). |
| `mapillary/sequence_z14_9410_5967_mls.pbf` | Same construction as above, with one MultiLineString feature carrying a `sequence_id` property (no `is_pano`) — covers the MultiLineString georeferencing branch and the sequence-id fallback key. |
| `kartaview/sequence_2.0_live_restricted_200.json` | **Recorded live** 2026-11-03: `GET https://api.kartaview.org/2.0/sequence/` (Bucharest bbox). The host answers HTTP 200 with a body carrying the API's own restriction envelope (`status.apiCode 400`, "Restricted access!") — real evidence of the host/schema drift the provider documents. The tolerant parser must yield zero segments for it (asserted by the test that consumes it). The legacy host `api.openstreetcam.org` failed TLS (certificate not valid for that hostname) at recording time. |
| `kartaview/sequence_2.0_constructed_data.json` | **Constructed** success envelope exercising every response shape the tolerant parser documents: nested `result.data` list, GeoJSON `geometry`, `track` string (`lat,lon` pairs, `\|`-separated too), `photos` dicts (`lat`/`lng` and `latitude`/`longitude`), `coordinates` string, `sequenceId`/`sequence_id`/`id` keys, plus short/garbage/non-dict items that must be dropped. Follows the module's own stated discipline ("parse_sequences is a pure function and is unit-tested with synthetic JSON"). |
