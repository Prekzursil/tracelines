"""Hermetic Mapillary tests: recorded/constructed MVT tiles over a local server.

The vector tiles under ``tests/fixtures/mapillary`` (see PROVENANCE.md) are
served by an in-process aiohttp server bound to 127.0.0.1, so the provider's
full HTTP path — retries, 404 empties, error statuses, caching — runs offline
against real MVT bytes.
"""

import asyncio
from pathlib import Path

from aiohttp import web

from tracelines.cache import Cache
from tracelines.config import BBox, Settings
from tracelines.providers import mapillary as mly
from tracelines.providers.mapillary import (
    MapillaryProvider,
    _as_lines,
    _backoff,
    _epoch_ms_to_ym,
    decode_sequence_tile,
    georef_layer,
    group_and_merge,
)
from tracelines.tiles import tile_bounds

FIXTURES = Path(__file__).parent / "fixtures" / "mapillary"
X, Y, Z = 9410, 5967, 14


def tile_pbf():
    return (FIXTURES / "sequence_z14_9410_5967.pbf").read_bytes()


def tile_pbf_mls():
    return (FIXTURES / "sequence_z14_9410_5967_mls.pbf").read_bytes()


# ---- pure helpers ------------------------------------------------------------


def test_backoff_bounds():
    s = Settings(retry_base=0.5, request_jitter=0.0)
    assert _backoff(s, 2) == 2.0
    j = Settings(retry_base=0.5, request_jitter=0.5)
    assert 0.25 <= _backoff(j, 0) <= 0.75
    assert _backoff(Settings(retry_base=0.0), 4) >= 0.0


def test_epoch_ms_to_ym_and_garbage():
    assert _epoch_ms_to_ym(1600000000000) == "2020-09"
    assert _epoch_ms_to_ym("not-a-number") is None
    assert _epoch_ms_to_ym(None) is None


# ---- georeferencing / grouping over fixture-shaped layers ---------------------


def test_georef_layer_multilinestring_and_skipped_types():
    w, s, e, n = tile_bounds(X, Y, Z)
    layer = {
        "extent": 4096,
        "features": [
            {
                "geometry": {
                    "type": "MultiLineString",
                    "coordinates": [[[0, 0], [0, 4096]], [[4096, 0], [4096, 4096]]],
                },
                "properties": {"sequence_id": "MLS", "captured_at": 1600000000000},
            },
            {
                "geometry": {"type": "Point", "coordinates": [10, 10]},
                "properties": {"id": "PT"},
            },  # non-line geometry -> skipped
            {
                "geometry": {"type": "LineString", "coordinates": [[0, 0]]},
                "properties": {"id": "SHORT"},
            },  # <2 pts -> skipped
            {
                "geometry": {"type": "LineString", "coordinates": [[0], [4096]]},
                "properties": {"id": "FLAT"},
            },  # malformed pts -> skipped
        ],
    }
    pieces = georef_layer(layer, X, Y, Z)
    assert len(pieces) == 2
    assert all(p["seq"] == "MLS" for p in pieces)
    assert pieces[0]["is_pano"] is None  # property absent -> None
    (lon0, lat0), (lon1, lat1) = pieces[0]["coords"]
    assert abs(lon0 - w) < 1e-9 and abs(lat0 - s) < 1e-9
    assert abs(lon1 - w) < 1e-9 and abs(lat1 - n) < 1e-9


def test_georef_layer_sequence_key_fallback():
    layer = {
        "extent": 4096,
        "features": [
            {
                "geometry": {"type": "LineString", "coordinates": [[0, 0], [4096, 4096]]},
                "properties": {"sequence": "FALLBACK-SEQ"},
            },
        ],
    }
    (piece,) = georef_layer(layer, X, Y, Z)
    assert piece["seq"] == "FALLBACK-SEQ"


def test_group_and_merge_captured_date_is_earliest_of_pieces():
    pieces = [
        {
            "seq": "D",
            "is_pano": False,
            "captured_at": 1600000000000,
            "coords": [(26.0, 44.0), (26.001, 44.0)],
        },
        {
            "seq": "D",
            "is_pano": False,
            "captured_at": 1500000000000,
            "coords": [(26.001, 44.0), (26.002, 44.0)],
        },
    ]
    segs = group_and_merge(pieces, min_run=2)
    assert len(segs) == 1
    assert segs[0].capture_date == "2017-07"  # min captured_at wins


def test_group_and_merge_loose_pieces_get_ids_and_dates():
    pieces = [
        {
            "seq": None,
            "is_pano": True,
            "captured_at": 1600000000000,
            "coords": [(26.0, 44.0), (26.001, 44.0)],
        },
        {
            "seq": None,
            "is_pano": False,
            "captured_at": None,
            "coords": [(27.0, 45.0), (27.001, 45.0)],
        },
    ]
    segs = group_and_merge(pieces, min_run=2)
    assert len(segs) == 2
    first = next(s for s in segs if s.is_pano is True)
    assert first.id.startswith("mapillary-loose-")
    assert first.meta == {}
    assert first.capture_date == "2020-09"
    undated = next(s for s in segs if s.is_pano is False)
    assert undated.capture_date is None


def test_group_and_merge_without_shapely_emits_each_piece(monkeypatch):
    monkeypatch.setattr(mly, "LineString", None)
    monkeypatch.setattr(mly, "linemerge", None)
    pieces = [
        {
            "seq": "S",
            "is_pano": False,
            "captured_at": None,
            "coords": [(26.0, 44.0), (26.001, 44.0)],
        },
        {
            "seq": "S",
            "is_pano": False,
            "captured_at": None,
            "coords": [(26.001, 44.0), (26.002, 44.0)],
        },
    ]
    segs = group_and_merge(pieces, min_run=2)
    assert len(segs) == 2  # no merge without shapely: pieces emitted as-is
    assert all(s.n_points == 2 for s in segs)


def test_as_lines_branches():
    from shapely.geometry import GeometryCollection, LineString, MultiLineString, Point

    assert _as_lines(LineString([(0, 0), (1, 1)])) != []
    assert len(_as_lines(MultiLineString([[(0, 0), (1, 1)], [(2, 2), (3, 3)]]))) == 2
    # GeometryCollection fallback: only the LineString children survive
    coll = GeometryCollection([LineString([(0, 0), (1, 1)]), Point(2, 2)])
    lines = _as_lines(coll)
    assert len(lines) == 1


# ---- decode over real fixture bytes ------------------------------------------


def test_decode_fixture_tile_roundtrip():
    pieces = decode_sequence_tile(tile_pbf(), X, Y, Z)
    seqs = {p["seq"] for p in pieces}
    assert seqs == {"SEQ-A", "SEQ-STUB"}
    assert sum(1 for p in pieces if p["seq"] == "SEQ-A") == 2
    w, s, e, n = tile_bounds(X, Y, Z)
    for lon, lat in (c for p in pieces for c in p["coords"]):
        assert w - 1e-9 <= lon <= e + 1e-9
        assert s - 1e-9 <= lat <= n + 1e-9


def test_decode_fixture_mls_tile_and_grouping():
    pieces = decode_sequence_tile(tile_pbf_mls(), X, Y, Z)
    assert len(pieces) == 2
    segs = group_and_merge(pieces, min_run=2)
    # the MLS sublines are disjoint -> both emitted, both tagged with the seq id
    assert len(segs) == 2
    assert {s.meta["sequence_id"] for s in segs} == {"SEQ-MLS"}
    assert {s.capture_date for s in segs} == {"2021-05"}


def test_decode_returns_empty_without_library_or_data(monkeypatch):
    monkeypatch.setattr(mly, "_mvt", None)
    assert decode_sequence_tile(b"", X, Y, Z) == []
    assert decode_sequence_tile(tile_pbf(), X, Y, Z) == []  # lib "missing"


def test_decode_supports_older_mvt_signature(monkeypatch):
    """mapbox_vector_tile<2 accepted y_coord_down as a plain kwarg."""
    captured = {}

    class OldMVT:
        @staticmethod
        def decode(data, y_coord_down=False):
            captured["kwargs"] = dict(y_coord_down=y_coord_down)
            return {
                "sequence": {
                    "extent": 4096,
                    "features": [
                        {
                            "geometry": {
                                "type": "LineString",
                                "coordinates": [[0, 0], [4096, 4096]],
                            },
                            "properties": {"id": "OLD"},
                        }
                    ],
                }
            }

    monkeypatch.setattr(mly, "_mvt", OldMVT)
    pieces = decode_sequence_tile(b"ignored", X, Y, Z)
    assert captured["kwargs"] == {"y_coord_down": False}
    assert [p["seq"] for p in pieces] == ["OLD"]


def test_decode_ignores_tiles_without_sequence_layer():
    import mapbox_vector_tile
    from shapely.geometry import LineString

    other = mapbox_vector_tile.encode(
        {
            "name": "overview",
            "features": [
                {"geometry": LineString([(0, 0), (4096, 4096)]), "properties": {"id": "x"}}
            ],
        }
    )
    assert decode_sequence_tile(other, X, Y, Z) == []


# ---- availability ------------------------------------------------------------


def test_available_in_this_env():
    assert MapillaryProvider().available() == (True, "")


def test_available_reports_missing_optionals(monkeypatch):
    monkeypatch.setattr(mly, "aiohttp", None)
    ok, why = MapillaryProvider().available()
    assert ok is False and "aiohttp" in why
    monkeypatch.undo()
    monkeypatch.setattr(mly, "aiohttp", __import__("aiohttp"))
    monkeypatch.setattr(mly, "_mvt", None)
    ok, why = MapillaryProvider().available()
    assert ok is False and "mapbox_vector_tile" in why
    assert "pip install mapbox-vector-tile" in why


# ---- fetch over a local HTTP server ------------------------------------------


class LocalTiles:
    """In-process tiles.mapillary.com stand-in serving fixture bytes."""

    def __init__(self, routes):
        # routes: {"z/x/y-pattern": (status, bytes|None)}
        self.routes = routes
        self.hits = []
        self._runner = None

    async def _handle(self, request):
        key = f"{request.match_info['z']}/{request.match_info['x']}/{request.match_info['y']}"
        self.hits.append(key)
        status, body = self.routes.get(key, self.routes.get("default"))
        if status == 404:
            return web.Response(status=404)
        return web.Response(status=status, body=body)

    async def start(self):
        app = web.Application()
        app.router.add_get("/{z}/{x}/{y}", self._handle)
        self._runner = web.AppRunner(app)
        await self._runner.setup()
        site = web.TCPSite(self._runner, "127.0.0.1", 0)
        await site.start()
        host, port = list(self._runner.addresses)[0]
        return f"http://{host}:{port}"

    async def stop(self):
        if self._runner:
            await self._runner.cleanup()


def run_fetch(monkeypatch, tmp_path, routes, bbox=None, **settings_over):
    async def scenario():
        server = LocalTiles(routes)
        base = await server.start()
        try:
            monkeypatch.setattr(mly, "TILE_URL", base + "/{z}/{x}/{y}")
            base = dict(
                mapillary_token="MLY|TEST",
                concurrency=2,
                timeout=5.0,
                max_retries=2,
                retry_base=0.001,
                zoom_mapillary=Z,
            )
            base.update(settings_over)
            settings = Settings(**base)
            cache = Cache(str(tmp_path))
            res = await MapillaryProvider().fetch(
                bbox or BBox(*tile_bounds(X, Y, Z)), settings, cache
            )
            cache.close()
            return res, server.hits
        finally:
            await server.stop()

    return asyncio.run(scenario())


def bbox_in_recorded_tile():
    w, s, e, n = tile_bounds(X, Y, Z)
    return BBox(w + 1e-4, s + 1e-4, e - 1e-4, n - 1e-4)


def test_fetch_no_token_skips_before_any_io(tmp_path):
    async def go():
        return await MapillaryProvider().fetch(
            BBox(26.0, 44.0, 26.01, 44.01),
            Settings(mapillary_token=None, cache_enabled=False),
            Cache(str(tmp_path), enabled=False),
        )

    res = asyncio.run(go())
    assert res.segments == [] and res.stats == {"skipped": "no MAPILLARY_TOKEN in env"}


def test_fetch_decodes_fixture_tile_into_merged_segments(monkeypatch, tmp_path):
    res, hits = run_fetch(
        monkeypatch,
        tmp_path,
        {"default": (200, tile_pbf())},
        bbox=bbox_in_recorded_tile(),
        min_run=3,
    )
    assert hits, "the tile endpoint was reached over real HTTP"
    segs = res.segments
    a = [s for s in segs if s.meta.get("sequence_id") == "SEQ-A"]
    assert a, "SEQ-A present"
    assert a[0].n_points >= 3, "the two SEQ-A pieces merge into one continuous line"
    stub = [s for s in segs if s.meta.get("sequence_id") == "SEQ-STUB"]
    assert stub == [], "the degenerate 2-pt stub is dropped by min_run=3"
    assert res.stats["tiles_fetched"] == res.stats["tiles_total"]
    assert res.stats["tiles_failed"] == 0
    assert res.stats["segments"] == len(segs)
    assert res.stats["pieces"] > 0


def test_fetch_maps_404_to_empty_and_caches_it(monkeypatch, tmp_path):
    res, _ = run_fetch(
        monkeypatch, tmp_path, {"default": (404, None)}, bbox=bbox_in_recorded_tile()
    )
    assert res.segments == []
    assert res.stats["tiles_empty"] == res.stats["tiles_total"]
    assert res.stats["tiles_failed"] == 0


def test_fetch_reports_failed_tile_after_retries(monkeypatch, tmp_path):
    res, hits = run_fetch(
        monkeypatch,
        tmp_path,
        {"default": (500, b"boom")},
        bbox=bbox_in_recorded_tile(),
        max_retries=2,
    )
    assert res.segments == []
    assert res.stats["tiles_failed"] == res.stats["tiles_total"]
    assert res.stats["tiles_fetched"] == 0
    assert len(hits) == 2 * res.stats["tiles_total"]  # retried once per tile


def test_fetch_counts_200_with_no_sequence_layer_as_empty(monkeypatch, tmp_path):
    import mapbox_vector_tile
    from shapely.geometry import LineString

    other = mapbox_vector_tile.encode(
        {
            "name": "overview",
            "features": [
                {"geometry": LineString([(0, 0), (4096, 4096)]), "properties": {"id": "x"}}
            ],
        }
    )
    res, _ = run_fetch(
        monkeypatch, tmp_path, {"default": (200, other)}, bbox=bbox_in_recorded_tile()
    )
    assert res.segments == []
    assert res.stats["tiles_empty"] == res.stats["tiles_total"]
    assert res.stats["tiles_fetched"] == res.stats["tiles_total"]  # fetched, just empty


def test_fetch_serves_cached_tiles_without_http(monkeypatch, tmp_path):
    async def scenario():
        from tracelines.tiles import tiles_in_bbox

        cache = Cache(str(tmp_path))
        w, s, e, n = tile_bounds(X, Y, Z)
        bbox = BBox(w + 1e-4, s + 1e-4, e - 1e-4, n - 1e-4)
        pieces = decode_sequence_tile(tile_pbf(), X, Y, Z)
        tiles = list(tiles_in_bbox(bbox.west, bbox.south, bbox.east, bbox.north, Z))
        for tx, ty in tiles:
            cache.set(f"mapillary:z{Z}:{tx}:{ty}", pieces)
        server = LocalTiles({"default": (200, tile_pbf())})
        base = await server.start()
        try:
            monkeypatch.setattr(mly, "TILE_URL", base + "/{z}/{x}/{y}")
            settings = Settings(mapillary_token="MLY|TEST", zoom_mapillary=Z, timeout=5.0)
            res = await MapillaryProvider().fetch(bbox, settings, cache)
            cache.close()
            return res, server.hits
        finally:
            await server.stop()

    res, hits = asyncio.run(scenario())
    assert hits == [], "cached tiles must not hit the endpoint"
    assert res.stats["tiles_cached"] == res.stats["tiles_total"]
    assert res.stats["segments"] >= 1


def test_fetch_include_third_party_flag_is_orthogonal(monkeypatch, tmp_path):
    """is_pano is a 360 flag, not a third-party filter: nothing is dropped."""
    res, _ = run_fetch(
        monkeypatch,
        tmp_path,
        {"default": (200, tile_pbf())},
        bbox=bbox_in_recorded_tile(),
        include_third_party=True,
    )
    a = [s for s in res.segments if s.meta.get("sequence_id") == "SEQ-A"]
    assert a, "include_third_party changes nothing for mapillary segments"
