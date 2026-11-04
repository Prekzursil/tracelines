"""Hermetic KartaView tests: recorded + constructed envelopes over a local server.

``tests/fixtures/kartaview`` (see PROVENANCE.md) carries the REAL recorded live
response of api.kartaview.org (a 200 whose body is the API's own restriction
envelope) and a constructed data-bearing envelope covering every tolerant
shape. Both are served by an in-process aiohttp server bound to 127.0.0.1, so
the provider's whole host-fallback / retry / cache path runs offline.
"""

import asyncio
import json
from pathlib import Path

from aiohttp import web

from tracelines.cache import Cache
from tracelines.config import BBox, Settings
from tracelines.providers import kartaview as kv
from tracelines.providers.kartaview import (
    KartaViewProvider,
    _backoff,
    _coerce_coords,
    _find_geometry,
    parse_sequences,
)

FIXTURES = Path(__file__).parent / "fixtures" / "kartaview"
BBOX = BBox(26.0, 44.0, 26.05, 44.05)


def live_restricted_payload():
    return json.loads((FIXTURES / "sequence_2.0_live_restricted_200.json").read_text("utf-8"))


def constructed_payload():
    return json.loads((FIXTURES / "sequence_2.0_constructed_data.json").read_text("utf-8"))


# ---- pure helpers ------------------------------------------------------------


def test_backoff_bounds():
    s = Settings(retry_base=0.5, request_jitter=0.0)
    assert _backoff(s, 1) == 1.0
    assert _backoff(Settings(retry_base=0.0), 3) >= 0.0


def test_coerce_coords_edge_shapes():
    assert _coerce_coords(None) == []
    assert _coerce_coords("44.0,26.0;;44.1,26.1") == [(26.0, 44.0), (26.1, 44.1)]
    assert _coerce_coords("44.0,26.0|44.1,26.1") == [(26.0, 44.0), (26.1, 44.1)]
    assert _coerce_coords("44.0;44.1") == []  # pairs need two numbers
    assert _coerce_coords("not,a,number") == []  # unparseable pair skipped
    assert _coerce_coords([[26.0]]) == []  # too-short GeoJSON point skipped
    assert _coerce_coords([{"lat": 44.0}]) == []  # dict without lng skipped
    assert _coerce_coords([(26.0, 44.0)]) == [(26.0, 44.0)]  # tuple point accepted
    assert _coerce_coords([42]) == []  # scalar point skipped


def test_find_geometry_falls_through_flat_keys_and_misses():
    seq = {"photos": [{"lat": 44.0, "lng": 26.0}, {"lat": 44.001, "lng": 26.001}]}
    assert _find_geometry(seq) == [(26.0, 44.0), (26.001, 44.001)]
    assert _find_geometry(
        {"geometry": {"no-coordinates": True}, "track": "44.0,26.0;44.1,26.1"}
    ) == [(26.0, 44.0), (26.1, 44.1)]
    assert _find_geometry({"geometry": "not-a-dict"}) == []
    assert _find_geometry({"nothing": "here"}) == []


def test_parse_sequences_envelope_shapes():
    seq = {"id": 1, "track": "44.0,26.0;44.1,26.1"}
    for envelope in (
        [seq],  # bare list
        {"result": [seq]},  # result
        {"results": [seq]},  # results
        {"sequences": [seq]},  # sequences
        {"data": [seq]},  # data
        {"currentPageItems": [seq]},  # currentPageItems
        {"items": [seq]},  # items
        {"result": {"data": [seq]}},  # nested result.data
        {"result": {"sequences": [seq]}},  # nested result.sequences
        {"result": {"items": [seq]}},  # nested result.items
        {"result": {"other": "ignored", "data": [seq]}},  # first hit wins
    ):
        segs = parse_sequences(envelope, min_run=2)
        assert len(segs) == 1, f"envelope not recognized: {envelope}"
        assert segs[0].id == "1"
    for empty in ({}, {"result": {}}, {"result": {"data": {}}}, "string", 42):
        assert parse_sequences(empty, min_run=2) == []


def test_parse_sequences_key_and_date_aliases():
    payload = {
        "result": [
            {
                "sequenceId": "S1",
                "path": [{"lat": 44.0, "lng": 26.0}, {"lat": 44.1, "lng": 26.1}],
                "dateAdded": "2020-02-05",
            },
            {
                "sequence_id": "S2",
                "coordinates": [[26.0, 44.0], [26.1, 44.1]],
                "date": "2019-12-31",
            },
            {"no_id_at_all": 1, "track": "44.0,26.0;44.1,26.1"},
        ]
    }
    segs = parse_sequences(payload, min_run=2)
    assert [s.id for s in segs] == ["S1", "S2", "kartaview-seg-2"]
    assert segs[0].capture_date == "2020-02"
    assert segs[1].capture_date == "2019-12"
    assert segs[2].capture_date is None
    assert segs[2].meta == {}


def test_parse_sequences_min_run_floor_is_two():
    assert parse_sequences([{"id": 1, "track": "44.0,26.0"}], min_run=1) == []


# ---- constructed fixture parses exactly as recorded --------------------------


def test_constructed_fixture_yields_expected_segments():
    segs = parse_sequences(constructed_payload(), min_run=2)
    assert [s.id for s in segs] == ["900001", "900002", "900003", "900006"]
    assert segs[0].coords[0] == (26.04, 44.43)  # GeoJSON order preserved
    assert segs[1].coords[0] == (26.06, 44.44)  # "lat,lon" track string swapped


def test_live_restricted_envelope_parses_to_nothing():
    """The REAL recorded live body: 200 + restriction envelope -> graceful zero."""
    assert parse_sequences(live_restricted_payload(), min_run=2) == []


# ---- availability ------------------------------------------------------------


def test_available_in_this_env():
    assert KartaViewProvider().available() == (True, "")


def test_available_false_without_aiohttp(monkeypatch):
    monkeypatch.setattr(kv, "aiohttp", None)
    assert KartaViewProvider().available() == (False, "aiohttp not importable")


# ---- fetch over a local HTTP server ------------------------------------------


class LocalKartaView:
    """In-process api.kartaview.org stand-in; one route per host shape."""

    def __init__(self, host_routes):
        # host_routes: {host_index: {"status": int, "json": obj} or {"fail": True}}
        self.host_routes = host_routes
        self.hits = []
        self._runner = None

    async def _handle(self, request):
        host_index = int(request.match_info["host"])
        self.hits.append((host_index, request.rel_url.query.get("bbTopLeft")))
        route = self.host_routes.get(host_index, {})
        if route.get("fail"):
            return web.Response(status=route.get("status", 500), text="upstream exploded")
        if "json" in route:
            return web.json_response(route["json"], status=route.get("status", 200))
        return web.Response(status=route.get("status", 200), text="status-only route")

    async def start(self):
        app = web.Application()
        app.router.add_get("/{host}/2.0/sequence/", self._handle)
        self._runner = web.AppRunner(app)
        await self._runner.setup()
        site = web.TCPSite(self._runner, "127.0.0.1", 0)
        await site.start()
        host, port = list(self._runner.addresses)[0]
        base = f"http://{host}:{port}"
        return (f"{base}/0", f"{base}/1")  # stand-ins for the two HOSTS entries

    async def stop(self):
        if self._runner:
            await self._runner.cleanup()


def run_fetch(monkeypatch, tmp_path, host_routes, prime_cache=None, **settings_over):
    async def scenario():
        server = LocalKartaView(host_routes)
        hosts = await server.start()
        try:
            monkeypatch.setattr(kv, "HOSTS", hosts)
            base = dict(mapillary_token="x", timeout=5.0, max_retries=2, retry_base=0.001)
            base.update(settings_over)
            settings = Settings(**base)
            cache = Cache(str(tmp_path))
            if prime_cache is not None:
                cache.set(
                    f"kartaview:{BBOX.west:.4f},{BBOX.south:.4f},{BBOX.east:.4f},{BBOX.north:.4f}",
                    prime_cache,
                )
            res = await KartaViewProvider().fetch(BBOX, settings, cache)
            cache.close()
            return res, server.hits
        finally:
            await server.stop()

    return asyncio.run(scenario())


def test_fetch_parses_constructed_envelope_over_http(monkeypatch, tmp_path):
    res, hits = run_fetch(
        monkeypatch, tmp_path, {0: {"status": 200, "json": constructed_payload()}}
    )
    assert hits, "the sequence endpoint was reached over real HTTP"
    assert res.stats["host_used"].endswith("/0")
    assert res.stats["segments"] == 4
    assert len(res.segments) == 4
    assert res.segments[0].source.value == "kartaview"
    assert res.stats["note"] == ""


def test_fetch_serves_cached_payload_without_http(monkeypatch, tmp_path):
    res, hits = run_fetch(
        monkeypatch,
        tmp_path,
        {0: {"fail": True}},
        prime_cache=constructed_payload(),
    )
    assert hits == []
    assert res.stats["cached"] is True
    assert res.stats["segments"] == 4
    assert len(res.segments) == 4


def test_fetch_falls_back_to_second_host_on_server_errors(monkeypatch, tmp_path):
    res, hits = run_fetch(
        monkeypatch,
        tmp_path,
        {0: {"fail": True, "status": 503}, 1: {"status": 200, "json": constructed_payload()}},
    )
    hosts_hit = {h for h, _ in hits}
    assert hosts_hit == {0, 1}, "host 0 failed, host 1 answered"
    assert res.stats["host_used"].endswith("/1")
    assert res.stats["segments"] == 4


def test_fetch_tries_next_host_on_404(monkeypatch, tmp_path):
    res, hits = run_fetch(
        monkeypatch,
        tmp_path,
        {0: {"status": 404}, 1: {"status": 200, "json": constructed_payload()}},
    )
    assert res.stats["host_used"].endswith("/1")
    assert res.stats["segments"] == 4


def test_fetch_records_last_error_note_when_all_hosts_5xx(monkeypatch, tmp_path):
    res, hits = run_fetch(
        monkeypatch,
        tmp_path,
        {0: {"fail": True, "status": 500}, 1: {"fail": True, "status": 500}},
        max_retries=2,
    )
    assert res.segments == []
    assert res.stats["host_used"] is None
    assert res.stats["note"].startswith("RuntimeError: HTTP 500")
    # retried both hosts, then gave up per host
    assert len(hits) == 4  # 2 hosts x 2 attempts


def test_fetch_default_note_when_only_non_200_statuses(monkeypatch, tmp_path):
    """Non-200 statuses break to the next host WITHOUT an exception note."""
    res, hits = run_fetch(
        monkeypatch,
        tmp_path,
        {0: {"status": 404}, 1: {"status": 403}},
    )
    assert res.segments == []
    assert res.stats["host_used"] is None
    assert res.stats["note"] == "no KartaView host responded; skipped (pipeline continues)"
    assert len(hits) == 2  # one request per host, no retries on plain non-200


def test_fetch_live_restricted_envelope_yields_zero_segments(monkeypatch, tmp_path):
    """The REAL recorded live body flows through the whole HTTP path."""
    res, _ = run_fetch(
        monkeypatch, tmp_path, {0: {"status": 200, "json": live_restricted_payload()}}
    )
    assert res.segments == []
    assert res.stats["segments"] == 0
    assert res.stats["host_used"].endswith("/0")


def test_fetch_retries_then_succeeds_within_budget(monkeypatch, tmp_path):
    # a host route that fails the first request then succeeds
    async def scenario():
        app = web.Application()
        hits = []

        async def handle(request):
            hits.append(1)
            if len(hits) < 2:
                return web.Response(status=500, text="transient")
            return web.json_response(constructed_payload(), status=200)

        app.router.add_get("/2.0/sequence/", handle)
        runner = web.AppRunner(app)
        await runner.setup()
        site = web.TCPSite(runner, "127.0.0.1", 0)
        await site.start()
        host, port = list(runner.addresses)[0]
        try:
            monkeypatch.setattr(kv, "HOSTS", (f"http://{host}:{port}",))
            settings = Settings(timeout=5.0, max_retries=3, retry_base=0.001)
            cache = Cache(str(tmp_path))
            res = await KartaViewProvider().fetch(BBOX, settings, cache)
            cache.close()
            return res, hits
        finally:
            await runner.cleanup()

    res, hits = asyncio.run(scenario())
    assert res.stats["segments"] == 4
    assert len(hits) == 2
