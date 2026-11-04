"""Hermetic Google-provider tests: recorded payload shapes drive every parse path.

The z17 coverage-tile records and the by-id metadata record come from
``tests/fixtures/google`` (see fixtures/PROVENANCE.md — recorded live 2026-11-03
over central Bucharest). The streetlevel calls themselves are replaced with
in-memory stand-ins built from those records, so the provider's full fetch /
precision / stitching-input path runs offline.
"""

import asyncio
import datetime as dt
import json
from pathlib import Path
from types import SimpleNamespace

import pytest

from tracelines.cache import Cache
from tracelines.config import BBox, Settings
from tracelines.models import Source, is_official_panoid
from tracelines.providers import google_sl
from tracelines.providers.google_sl import GoogleStreetlevelProvider, _backoff, _fmt_date

FIXTURES = Path(__file__).parent / "fixtures" / "google"


# ---- recorded-payload helpers ------------------------------------------------


def recorded_tile_records():
    return json.loads((FIXTURES / "coverage_tile_z17_75020_47439.json").read_text(encoding="utf-8"))


def recorded_byid():
    return json.loads((FIXTURES / "pano_by_id_launch_2024-07.json").read_text(encoding="utf-8"))


def sl_pano(rec):
    """A stand-in streetlevel coverage pano built from a recorded record."""
    links = [SimpleNamespace(pano=SimpleNamespace(id=nb)) for nb in rec.get("links", [])]
    return SimpleNamespace(
        id=rec["id"],
        lat=rec["lat"],
        lon=rec["lon"],
        is_third_party=rec.get("is_third_party", False),
        links=links,
    )


def fake_tile_fn(recs_by_tile):
    """Stand-in for streetlevel's get_coverage_tile_async over recorded records.

    ``recs_by_tile`` maps (tx, ty) -> records; the special key ``"default"``
    supplies records for every tile the crawl reaches that is not listed.
    """
    calls = []

    async def get_coverage_tile_async(tx, ty, session):
        calls.append((tx, ty))
        recs = recs_by_tile.get((tx, ty), recs_by_tile.get("default", []))
        return [sl_pano(r) for r in recs]

    return get_coverage_tile_async, calls


def patch_sv(monkeypatch, tile_async=None, byid_async=None):
    """Point google_sl._sv at a stand-in namespace (no streetlevel needed:
    its pyexiv2 dependency cannot even load on macOS, which is exactly why
    the provider degrades gracefully via available()).

    aiohttp is re-bound too: google_sl's try-block imports BOTH libraries, so
    a failed streetlevel import leaves `aiohttp = None` as well even though
    aiohttp itself imports fine everywhere.
    """
    import aiohttp as real_aiohttp

    monkeypatch.setattr(google_sl, "aiohttp", real_aiohttp)
    monkeypatch.setattr(
        google_sl,
        "_sv",
        SimpleNamespace(get_coverage_tile_async=tile_async, find_panorama_by_id_async=byid_async),
    )


def expected_tiles(bbox, z=17):
    from tracelines.tiles import tiles_in_bbox

    return list(tiles_in_bbox(bbox.west, bbox.south, bbox.east, bbox.north, z))


def fast_settings(**kw):
    kw.setdefault("concurrency", 2)
    kw.setdefault("timeout", 5.0)
    kw.setdefault("max_retries", 2)
    kw.setdefault("retry_base", 0.001)
    return Settings(**kw)


def tile_bbox(recs):
    """A bbox inside the recorded tile (single-tile crawl)."""
    lat = recs["panos"][0]["lat"]
    lon = recs["panos"][0]["lon"]
    return BBox(lon - 1e-4, lat - 1e-4, lon + 1e-4, lat + 1e-4)


# ---- pure helpers ------------------------------------------------------------


def test_backoff_is_exponential_with_jitter():
    s = fast_settings(retry_base=0.5, request_jitter=0.0)
    assert _backoff(s, 0) == 0.5
    assert _backoff(s, 3) == 4.0
    j = fast_settings(retry_base=0.5, request_jitter=0.25)
    for attempt in (0, 1, 2):
        v = _backoff(j, attempt)
        expected = 0.5 * (2**attempt)
        assert expected * 0.75 <= v <= expected * 1.25
    assert _backoff(fast_settings(retry_base=0.0), 5) >= 0.0


def test_fmt_date_branches():
    assert _fmt_date(None) is None
    assert _fmt_date("2024-07") == "2024-07"  # already a string passes through
    assert _fmt_date(dt.date(2024, 7, 2)) == "2024-07"
    year_only = SimpleNamespace(year=2021, month=None)
    assert _fmt_date(year_only) == "2021"
    assert _fmt_date(42) == "42"  # no year/month attrs -> str() fallback
    marker = object()
    assert _fmt_date(marker) == str(marker)


# ---- availability ------------------------------------------------------------


def test_available_true_when_imports_bound(monkeypatch):
    patch_sv(monkeypatch)  # streetlevel-shaped stand-in bound
    monkeypatch.setattr(google_sl, "aiohttp", object())  # non-None placeholder
    assert GoogleStreetlevelProvider().available() == (True, "")


def test_available_false_when_streetlevel_missing(monkeypatch):
    monkeypatch.setattr(google_sl, "_sv", None)
    ok, why = GoogleStreetlevelProvider().available()
    assert ok is False
    assert "not importable" in why


# ---- fetch: recorded payload through the whole parse path ---------------------


def test_fetch_keeps_every_official_recorded_pano(monkeypatch, tmp_path):
    recs = recorded_tile_records()
    fake, calls = fake_tile_fn({"default": recs["panos"]})
    patch_sv(monkeypatch, tile_async=fake)

    bbox = tile_bbox(recs)
    n_tiles = len(expected_tiles(bbox))
    res = asyncio.run(
        GoogleStreetlevelProvider().fetch(bbox, fast_settings(), Cache(str(tmp_path)))
    )
    assert calls, "the provider must consult the coverage-tile endpoint"
    assert res.source == Source.GOOGLE
    assert res.panos and len(res.panos) == len(recs["panos"])
    assert all(p.is_third_party is False for p in res.panos)
    assert all(is_official_panoid(p.id) for p in res.panos), "HARD RULE: official ids only"
    st = res.stats
    assert st["tiles_total"] == n_tiles and st["tiles_fetched"] == n_tiles
    assert st["tiles_failed"] == 0 and st["tiles_cached"] == 0
    assert st["panos_raw"] == len(recs["panos"]) * n_tiles
    assert st["non_official_id"] == 0 and st["third_party"] == 0
    assert st["panos_kept"] == len(res.panos)


def test_fetch_hard_rule_drops_third_party_and_non_official_ids(monkeypatch, tmp_path):
    recs = recorded_tile_records()
    _tx, _ty = recs["tile"][0], recs["tile"][1]
    tp_id = "SyntheticTP0123456789A"  # official SHAPE, absent from the recorded set
    assert tp_id not in {r["id"] for r in recs["panos"]}
    third_party = {**recs["panos"][0], "id": tp_id, "is_third_party": True}
    non_official = {**recs["panos"][1], "id": "CIHM0ogKEICAgICfxxxxxA"}  # UGC prefix, terminal ok
    augmented = recs["panos"] + [third_party, non_official]
    fake, _ = fake_tile_fn({"default": augmented})
    patch_sv(monkeypatch, tile_async=fake)

    res = asyncio.run(
        GoogleStreetlevelProvider().fetch(tile_bbox(recs), fast_settings(), Cache(str(tmp_path)))
    )
    ids = {p.id for p in res.panos}
    assert third_party["id"] not in ids, "HARD RULE: third-party must never survive"
    assert non_official["id"] not in ids, "HARD RULE: non-official id shape must never survive"
    assert res.stats["third_party"] == res.stats["tiles_total"]  # once per covering tile
    assert res.stats["non_official_id"] == res.stats["tiles_total"]


def test_fetch_include_third_party_is_the_debug_escape_hatch(monkeypatch, tmp_path):
    recs = recorded_tile_records()
    _tx, _ty = recs["tile"][0], recs["tile"][1]
    third_party = {**recs["panos"][0], "id": "SyntheticTP0123456789A", "is_third_party": True}
    fake, _ = fake_tile_fn({"default": [third_party]})
    patch_sv(monkeypatch, tile_async=fake)

    res = asyncio.run(
        GoogleStreetlevelProvider().fetch(
            tile_bbox(recs), fast_settings(include_third_party=True), Cache(str(tmp_path))
        )
    )
    assert [p.id for p in res.panos] == [third_party["id"]]
    assert res.stats["third_party"] == 0 and res.stats["non_official_id"] == 0


def test_fetch_merges_duplicate_pano_across_tiles_and_dedupes_neighbors(monkeypatch, tmp_path):
    recs = recorded_tile_records()
    a = recs["panos"][0]
    b = recs["panos"][1]
    # the same pano comes back from every tile the bbox covers, each time also
    # re-announcing an existing neighbor -> id dedupe + neighbor-set dedupe
    again = {**b, "links": (b["links"] or ["x"]) + [b["links"][0] if b["links"] else "x"]}
    fake, _ = fake_tile_fn({"default": [a, b, again]})
    patch_sv(monkeypatch, tile_async=fake)

    res = asyncio.run(
        GoogleStreetlevelProvider().fetch(tile_bbox(recs), fast_settings(), Cache(str(tmp_path)))
    )
    by_id = {p.id: p for p in res.panos}
    assert len(by_id) == len(res.panos), "ids are unique across tiles"
    assert set(by_id) == {a["id"], b["id"]}
    merged = by_id[b["id"]]
    assert len(merged.neighbors) == len(set(merged.neighbors)), "no duplicate neighbor"


def test_fetch_prunes_self_loop_and_unknown_neighbor_edges(monkeypatch, tmp_path):
    recs = recorded_tile_records()
    p0 = recs["panos"][0]
    self_loop = {**p0, "links": [p0["id"], "ZZZZZZZZZZZZZZZZZZZZZA"]}
    fake, _ = fake_tile_fn({"default": [self_loop]})
    patch_sv(monkeypatch, tile_async=fake)

    res = asyncio.run(
        GoogleStreetlevelProvider().fetch(tile_bbox(recs), fast_settings(), Cache(str(tmp_path)))
    )
    p = res.panos[0]
    assert p.id not in p.neighbors, "self-loops are pruned"
    assert p.neighbors == [], "neighbors pointing at dropped nodes are pruned"
    assert res.stats["isolates"] == 1  # degree collapsed to 0


def test_fetch_serves_tiles_from_cache_without_endpoint_calls(monkeypatch, tmp_path):
    recs = recorded_tile_records()
    cache = Cache(str(tmp_path))
    cached_recs = [
        {"id": r["id"], "lat": r["lat"], "lon": r["lon"], "tp": False, "nb": []}
        for r in recs["panos"]
    ]
    for tx, ty in expected_tiles(tile_bbox(recs)):
        cache.set(f"google:z17:{tx}:{ty}", cached_recs)
    fake, calls = fake_tile_fn({"default": recs["panos"]})
    patch_sv(monkeypatch, tile_async=fake)

    res = asyncio.run(GoogleStreetlevelProvider().fetch(tile_bbox(recs), fast_settings(), cache))
    assert calls == [], "a cached tile must not hit the endpoint"
    assert res.stats["tiles_cached"] == res.stats["tiles_total"]
    assert res.stats["tiles_fetched"] == 0
    assert res.stats["panos_kept"] == len(recs["panos"])
    cache.close()


def test_fetch_reports_failed_tile_after_retries(monkeypatch, tmp_path):
    recs = recorded_tile_records()

    async def always_failing(tx, ty, session):
        raise RuntimeError("photometa down")

    patch_sv(monkeypatch, tile_async=always_failing)
    res = asyncio.run(
        GoogleStreetlevelProvider().fetch(
            tile_bbox(recs), fast_settings(max_retries=2), Cache(str(tmp_path))
        )
    )
    assert res.panos == []
    assert res.stats["tiles_failed"] == res.stats["tiles_total"]
    assert res.stats["tiles_fetched"] == 0


def test_fetch_recovers_within_the_retry_budget(monkeypatch, tmp_path):
    recs = recorded_tile_records()
    attempts = []

    async def flaky(tx, ty, session):
        attempts.append((tx, ty))
        if attempts.count((tx, ty)) < 2:  # every tile fails its FIRST attempt
            raise RuntimeError("transient")
        return [sl_pano(r) for r in recorded_tile_records()["panos"][:3]]

    patch_sv(monkeypatch, tile_async=flaky)
    res = asyncio.run(
        GoogleStreetlevelProvider().fetch(
            tile_bbox(recs), fast_settings(max_retries=3), Cache(str(tmp_path))
        )
    )
    assert res.stats["tiles_fetched"] == res.stats["tiles_total"]
    assert res.stats["tiles_failed"] == 0
    assert len(attempts) == 2 * res.stats["tiles_total"]
    assert res.stats["panos_kept"] == 3


# ---- precision pass (find_panorama_by_id per kept node) -----------------------


def byid_fake(mapping, failures=()):
    calls = []

    async def find_panorama_by_id_async(panoid, session):
        calls.append(panoid)
        if panoid in failures:
            raise RuntimeError("photometa by-id down")
        rec = mapping.get(panoid)
        if rec is None:
            return None
        links = [SimpleNamespace(pano=SimpleNamespace(id=nb)) for nb in rec.get("links", [])]
        date = rec.get("date")
        if isinstance(date, str) and len(date) == 7:  # 'YYYY-MM' -> date-like object
            y, m = int(date[:4]), int(date[5:7])
            date = dt.date(y, m, 1)
        return SimpleNamespace(id=rec["id"], source=rec.get("source"), date=date, links=links)

    return find_panorama_by_id_async, calls


def two_official():
    recs = recorded_tile_records()
    return {**recs["panos"][0], "links": []}, {**recs["panos"][1], "links": []}


def test_precision_keeps_car_drops_confirmed_non_car(monkeypatch, tmp_path):
    car, trekker = two_official()
    mapping = {
        car["id"]: {"id": car["id"], "source": "launch", "date": "2024-07", "links": []},
        trekker["id"]: {"id": trekker["id"], "source": "scout", "date": "2022-03", "links": []},
    }
    fake_tile, _ = fake_tile_fn({"default": [car, trekker]})
    fake_byid, byid_calls = byid_fake(mapping)
    patch_sv(monkeypatch, tile_async=fake_tile, byid_async=fake_byid)

    recorded_tile_records()
    bbox = BBox(car["lon"] - 1e-4, car["lat"] - 1e-4, car["lon"] + 1e-4, car["lat"] + 1e-4)
    res = asyncio.run(
        GoogleStreetlevelProvider().fetch(
            bbox, fast_settings(precision=True), Cache(str(tmp_path / "c1"))
        )
    )
    kept = {p.id for p in res.panos}
    assert car["id"] in kept and trekker["id"] not in kept, "only CONFIRMED non-car is dropped"
    assert res.stats["precision_dropped"] == 1
    assert res.stats["precision_byid_failed"] == 0
    assert res.stats["precision_source_none"] == 0
    assert res.stats["precision_source_all_none"] is False
    kept_pano = next(p for p in res.panos if p.id == car["id"])
    assert kept_pano.sv_source == "launch" and kept_pano.date == "2024-07"


def test_precision_keeps_trekker_when_include_trekker(monkeypatch, tmp_path):
    car, trekker = two_official()
    mapping = {
        car["id"]: {"id": car["id"], "source": "launch", "date": None, "links": []},
        trekker["id"]: {"id": trekker["id"], "source": "scout", "date": None, "links": []},
    }
    fake_tile, _ = fake_tile_fn({"default": [car, trekker]})
    fake_byid, _ = byid_fake(mapping)
    patch_sv(monkeypatch, tile_async=fake_tile, byid_async=fake_byid)

    bbox = BBox(car["lon"] - 1e-4, car["lat"] - 1e-4, car["lon"] + 1e-4, car["lat"] + 1e-4)
    res = asyncio.run(
        GoogleStreetlevelProvider().fetch(
            bbox, fast_settings(precision=True, include_trekker=True), Cache(str(tmp_path / "c2"))
        )
    )
    assert {p.id for p in res.panos} == {car["id"], trekker["id"]}


def test_precision_keeps_nodes_whose_byid_fails(monkeypatch, tmp_path):
    car, _ = two_official()
    other, _ = two_official()
    fake_tile, _ = fake_tile_fn({"default": [car]})
    fake_byid, calls = byid_fake({}, failures=(car["id"],))
    patch_sv(monkeypatch, tile_async=fake_tile, byid_async=fake_byid)

    bbox = BBox(car["lon"] - 1e-4, car["lat"] - 1e-4, car["lon"] + 1e-4, car["lat"] + 1e-4)
    res = asyncio.run(
        GoogleStreetlevelProvider().fetch(
            bbox, fast_settings(precision=True, max_retries=2), Cache(str(tmp_path / "c3"))
        )
    )
    assert [p.id for p in res.panos] == [car["id"]], "FETCH_FAILED never silently drops a node"
    assert res.stats["precision_byid_failed"] == 1
    assert res.panos[0].sv_source is None
    assert len(calls) == 2, "one call per retry attempt"


def test_precision_uses_cached_byid_record(monkeypatch, tmp_path):
    car, other = two_official()
    fake_tile, _ = fake_tile_fn({"default": [car, other]})
    fake_byid, calls = byid_fake({})
    patch_sv(monkeypatch, tile_async=fake_tile, byid_async=fake_byid)

    cache = Cache(str(tmp_path / "c4"))
    cache.set(
        f"google:byid:{car['id']}",
        {"src": "launch", "date": "2019-12", "nb": [other["id"]]},
    )
    bbox = BBox(car["lon"] - 1e-4, car["lat"] - 1e-4, car["lon"] + 1e-4, car["lat"] + 1e-4)
    res = asyncio.run(GoogleStreetlevelProvider().fetch(bbox, fast_settings(precision=True), cache))
    assert car["id"] not in calls, "a cached by-id record must not hit the endpoint"
    assert calls == [other["id"]], "only the uncached node still resolves by id"
    p = next(pp for pp in res.panos if pp.id == car["id"])
    assert p.sv_source == "launch" and p.date == "2019-12"
    assert p.neighbors == [other["id"]], "resolved cross-links are added, never duplicated"
    cache.close()


def test_precision_all_none_trips_the_canary(monkeypatch, tmp_path):
    car, other = two_official()
    fake_tile, _ = fake_tile_fn({"default": [car, other]})
    patch_sv(monkeypatch, tile_async=fake_tile)
    mapping = {
        p["id"]: {"id": p["id"], "source": None, "date": None, "links": []} for p in (car, other)
    }
    fake_byid, _ = byid_fake(mapping)

    bbox = BBox(car["lon"] - 1e-4, car["lat"] - 1e-4, car["lon"] + 1e-4, car["lat"] + 1e-4)
    res = asyncio.run(
        GoogleStreetlevelProvider().fetch(
            bbox, fast_settings(precision=True), Cache(str(tmp_path / "c5"))
        )
    )
    assert res.stats["precision_source_all_none"] is True
    assert res.stats["precision_source_none"] == 2
    assert len(res.panos) == 2, "source-None unknowns are KEPT (never silent data loss)"


def test_precision_skipped_when_no_panos(monkeypatch, tmp_path):
    async def failing(tx, ty, session):
        raise RuntimeError("down")

    patch_sv(monkeypatch, tile_async=failing)
    fake_byid, calls = byid_fake({})

    recs = recorded_tile_records()

    res = asyncio.run(
        GoogleStreetlevelProvider().fetch(
            tile_bbox(recs),
            fast_settings(precision=True, max_retries=2),
            Cache(str(tmp_path / "c6")),
        )
    )
    assert res.panos == [] and calls == [], "precision never runs without kept nodes"


def test_precision_adds_cross_links_from_recorded_byid(monkeypatch, tmp_path):
    """The REAL recorded by-id record flows through the precision pass."""
    recs = recorded_tile_records()
    car = {**recs["panos"][0], "links": []}  # the pano the by-id record was captured for
    byid = recorded_byid()
    assert byid["id"] == car["id"]
    link_targets = [r for r in recs["panos"] if r["id"] in byid["links"]]
    fake_tile, _ = fake_tile_fn({"default": [car] + link_targets})
    fake_byid, _ = byid_fake({car["id"]: byid})
    patch_sv(monkeypatch, tile_async=fake_tile, byid_async=fake_byid)

    bbox = BBox(car["lon"] - 1e-4, car["lat"] - 1e-4, car["lon"] + 1e-4, car["lat"] + 1e-4)
    res = asyncio.run(
        GoogleStreetlevelProvider().fetch(
            bbox, fast_settings(precision=True), Cache(str(tmp_path / "c7"))
        )
    )
    by_id = {p.id: p for p in res.panos}
    p = by_id[car["id"]]
    assert p.sv_source == "launch" and p.date == "2024-07"
    for link in byid["links"]:
        if link in by_id:  # a cross-link survives pruning only if its target is kept
            assert link in p.neighbors, "cross-tile links from by-id are merged in"


def test_fetch_returns_no_segments_directly(monkeypatch, tmp_path):
    recs = recorded_tile_records()
    tx, ty = recs["tile"][0], recs["tile"][1]
    fake, _ = fake_tile_fn({(tx, ty): recs["panos"]})
    patch_sv(monkeypatch, tile_async=fake)
    res = asyncio.run(
        GoogleStreetlevelProvider().fetch(tile_bbox(recs), fast_settings(), Cache(str(tmp_path)))
    )
    assert res.segments == [], "Google is a point source; stitching happens in the pipeline"


@pytest.mark.parametrize("attr", ["_sv", "aiohttp"])
def test_optional_imports_are_never_unbound(monkeypatch, attr):
    """The None-binding contract: available() flips, fetch() is guarded by it."""
    monkeypatch.setattr(google_sl, attr, None)
    ok, why = GoogleStreetlevelProvider().available()
    assert ok is False and "not importable" in why
