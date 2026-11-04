"""Hermetic tests for nearest.py's live wrapper over recorded pano shapes.

The z17 tile records and by-id metadata come from ``tests/fixtures/google``
(see PROVENANCE.md — recorded live 2026-11-03 over central Bucharest). The
streetlevel calls are replaced with in-memory stand-ins built from those
records, so find_nearest_coverage / historical_stack run offline against the
exact payload shapes they parse in production.
"""

import base64
import datetime as dt
import json
from pathlib import Path
from types import SimpleNamespace

import pytest

from tracelines import nearest
from tracelines.models import Source, is_official_panoid
from tracelines.nearest import (
    _fmt_date,
    _pano_from_sl,
    build_streetview_url,
    find_nearest_coverage,
    historical_stack,
)

FIXTURES = Path(__file__).parent / "fixtures" / "google"
Q_LON, Q_LAT = 26.050430, 44.435072


def recorded_tile_records():
    return json.loads((FIXTURES / "coverage_tile_z17_75020_47439.json").read_text("utf-8"))


def recorded_byid():
    return json.loads((FIXTURES / "pano_by_id_launch_2024-07.json").read_text("utf-8"))


def official_id(seed: int) -> str:
    return base64.urlsafe_b64encode(seed.to_bytes(16, "big")).decode().rstrip("=")


def photosphere_id(seed: int) -> str:
    return ("CIHM0ogKEICAg" + str(seed).rjust(9, "0"))[:22]


def sl_pano(rec, heading=None):
    links = [SimpleNamespace(pano=SimpleNamespace(id=nb)) for nb in rec.get("links", [])]
    return SimpleNamespace(
        id=rec["id"],
        lat=rec["lat"],
        lon=rec["lon"],
        heading=heading,
        is_third_party=rec.get("is_third_party", False),
        links=links,
    )


# ---- _fmt_date ----------------------------------------------------------------


def test_fmt_date_branches():
    assert _fmt_date(None) is None
    assert _fmt_date("2024-07") == "2024-07"
    assert _fmt_date(dt.date(2023, 1, 9)) == "2023-01"
    assert _fmt_date(SimpleNamespace(year=2019, month=None)) == "2019"
    marker = object()
    assert _fmt_date(marker) == str(marker)


# ---- _pano_from_sl ------------------------------------------------------------


def test_pano_from_sl_maps_streetlevel_fields():
    rec = recorded_tile_records()["panos"][0]
    p = _pano_from_sl(sl_pano(rec, heading=123.5))
    assert p.id == rec["id"]
    assert (p.lon, p.lat) == (rec["lon"], rec["lat"])
    assert p.source == Source.GOOGLE
    assert p.heading == 123.5
    assert p.is_third_party is False
    assert p.neighbors == rec["links"]
    assert p.degree == len(rec["links"])


def test_pano_from_sl_without_links_or_heading():
    rec = {**recorded_tile_records()["panos"][0], "links": []}
    p = _pano_from_sl(sl_pano(rec))
    assert p.heading is None and p.neighbors == [] and p.degree == 0


# ---- find_nearest_coverage ----------------------------------------------------


def as_sl(record):
    """A stand-in streetlevel pano (with historical chain) from a record dict."""
    links = [SimpleNamespace(pano=SimpleNamespace(id=nb)) for nb in record.get("links", [])]
    date = record.get("date")
    if isinstance(date, str) and len(date) == 7:
        date = dt.date(int(date[:4]), int(date[5:7]), 1)
    return SimpleNamespace(
        id=record.get("id"),
        lat=record.get("lat", 0),
        lon=record.get("lon", 0),
        source=record.get("source"),
        date=date,
        links=links,
        historical=[as_sl(h) for h in record.get("historical", [])],
    )


def patch_streetview(monkeypatch, tiles, byid=None):
    """tiles: list returned for EVERY tile; byid: {panoid: record-or-None}."""
    monkeypatch.setattr(nearest._sv, "wgs84_to_tile_coord", lambda lat, lon, z: (75020, 47439))

    def get_coverage_tile(tx, ty):
        return tiles

    monkeypatch.setattr(nearest._sv, "get_coverage_tile", get_coverage_tile)

    if byid is not None:

        def find_panorama_by_id(panoid, *a, **k):
            rec = byid.get(panoid)
            return as_sl(rec) if rec is not None else None

        monkeypatch.setattr(nearest._sv, "find_panorama_by_id", find_panorama_by_id)


def connected(rec):
    """Keep a recorded pano on the continuous line (degree >= 1)."""
    return {**rec, "links": rec.get("links") or [rec["id"] + "x"]}


def test_raises_when_streetlevel_missing(monkeypatch):
    monkeypatch.setattr(nearest, "_sv", None)
    with pytest.raises(RuntimeError, match="streetlevel not importable"):
        find_nearest_coverage(Q_LAT, Q_LON)
    with pytest.raises(RuntimeError, match="streetlevel not importable"):
        historical_stack(Q_LAT, Q_LON)


def test_returns_none_when_no_official_coverage(monkeypatch):
    only_tp = [
        sl_pano(
            {**recorded_tile_records()["panos"][0], "id": photosphere_id(1), "is_third_party": True}
        )
    ]
    patch_streetview(monkeypatch, only_tp)
    assert find_nearest_coverage(Q_LAT, Q_LON) is None


def test_skips_closer_third_party_candidate(monkeypatch):
    recs = recorded_tile_records()
    # a third-party photosphere sitting EXACTLY on the query point...
    tp = sl_pano(
        {
            **recs["panos"][0],
            "id": photosphere_id(9),
            "lat": Q_LAT,
            "lon": Q_LON,
            "is_third_party": True,
        }
    )
    # ...and the real recorded official coverage ~48 m away
    official = [sl_pano(r) for r in recs["panos"]]
    byid = {r["id"]: None for r in recs["panos"]}  # by-id resolves to None -> src None
    patch_streetview(monkeypatch, [tp] + official, byid=byid)

    res = find_nearest_coverage(Q_LAT, Q_LON, verify_source=True)
    assert res is not None
    assert res.pano.is_third_party is False, "HARD RULE: never a third-party pano"
    assert is_official_panoid(res.pano.id)
    assert res.pano.sv_source is None  # resolved-but-no-source is KEPT
    assert res.distance_m > 0


def test_verified_car_source_wins(monkeypatch):
    recs = recorded_tile_records()
    car = recs["panos"][0]
    byid = {r["id"]: None for r in recs["panos"]}
    byid[car["id"]] = {**recorded_byid()}  # the REAL recorded launch/2024-07 record
    patch_streetview(monkeypatch, [sl_pano(r) for r in recs["panos"]], byid=byid)

    res = find_nearest_coverage(car["lat"], car["lon"], verify_source=True)
    assert res.pano.sv_source == "launch"
    assert res.pano.date == "2024-07"


def test_confirmed_non_car_is_skipped_for_a_car_candidate(monkeypatch):
    recs = recorded_tile_records()
    near_car = connected(recs["panos"][0])
    far_car = connected(recs["panos"][1])
    trekker = sl_pano({**near_car, "lat": near_car["lat"], "lon": near_car["lon"]})
    car = sl_pano({**far_car, "lat": far_car["lat"] + 0.001, "lon": far_car["lon"]})
    byid = {
        near_car["id"]: {"source": "scout", "date": "2020-01", "links": []},
        far_car["id"]: {"source": "launch", "date": "2021-02", "links": []},
    }
    patch_streetview(monkeypatch, [trekker, car], byid=byid)

    res = find_nearest_coverage(near_car["lat"], near_car["lon"], verify_source=True)
    assert res.pano.sv_source == "launch", "the scout node is skipped, car returned"


def test_trekker_accepted_when_include_trekker(monkeypatch):
    recs = recorded_tile_records()
    node = connected(recs["panos"][0])
    byid = {node["id"]: {"source": "scout", "date": "2020-01", "links": []}}
    patch_streetview(monkeypatch, [sl_pano(node)], byid=byid)

    res = find_nearest_coverage(node["lat"], node["lon"], verify_source=True, include_trekker=True)
    assert res.pano.sv_source == "scout"


def test_all_filtered_falls_back_to_nearest_official_connected(monkeypatch):
    recs = recorded_tile_records()
    node = connected(recs["panos"][0])
    byid = {node["id"]: {"source": "scout", "date": "2020-01", "links": []}}
    patch_streetview(monkeypatch, [sl_pano(node)], byid=byid)

    res = find_nearest_coverage(node["lat"], node["lon"], verify_source=True)
    assert res is not None, "official+connected nodes are never silently dropped"
    assert res.pano.id == node["id"]
    assert res.pano.sv_source == "scout"  # source known, just outside the car filter


def test_verify_source_false_returns_first_ranked(monkeypatch):
    recs = recorded_tile_records()
    node = connected(recs["panos"][0])
    called = []
    patch_streetview(monkeypatch, [sl_pano(node)])
    monkeypatch.setattr(
        nearest._sv,
        "find_panorama_by_id",
        lambda pid, *a, **k: called.append(pid) or None,
    )
    res = find_nearest_coverage(node["lat"], node["lon"], verify_source=False)
    assert res.pano.id == node["id"]
    assert called == [], "verify_source=False never calls find_panorama_by_id"


def test_radius_tiles_sweep_reads_neighborhood(monkeypatch):
    recs = recorded_tile_records()
    seen_tiles = []

    def get_coverage_tile(tx, ty):
        seen_tiles.append((tx, ty))
        return [sl_pano(r) for r in recs["panos"]]

    monkeypatch.setattr(nearest._sv, "wgs84_to_tile_coord", lambda lat, lon, z: (75020, 47439))
    monkeypatch.setattr(nearest._sv, "get_coverage_tile", get_coverage_tile)
    {r["id"]: None for r in recs["panos"]}
    monkeypatch.setattr(nearest._sv, "find_panorama_by_id", lambda pid, *a, **k: None)

    res = find_nearest_coverage(Q_LAT, Q_LON, radius_tiles=1)
    assert len(seen_tiles) == 9, "3x3 neighborhood swept"
    assert res is not None
    # duplicate panos across tiles collapse by id
    assert is_official_panoid(res.pano.id)


# ---- historical_stack ---------------------------------------------------------


def test_historical_stack_uses_the_recorded_byid_payload(monkeypatch):
    recs = recorded_tile_records()
    byid = recorded_byid()
    patch_streetview(monkeypatch, [sl_pano(r) for r in recs["panos"]])
    monkeypatch.setattr(
        nearest._sv,
        "find_panorama_by_id",
        lambda pid, *a, **k: as_sl(byid) if pid == byid["id"] else None,
    )

    stack = historical_stack(byid["lat"], byid["lon"])
    assert stack, "the recorded pano has 10 historical captures"
    ids = [entry["id"] for entry in stack]
    assert byid["id"] in ids
    assert all(is_official_panoid(i) for i in ids), "HARD RULE: official ids only in the stack"
    dates = [entry["date"] for entry in stack if entry["date"]]
    assert dates == sorted(dates, reverse=True), "newest first"
    for entry in stack:
        assert entry["sv_url"] == build_streetview_url(entry["id"], entry["lat"], entry["lon"])


def test_historical_stack_drops_third_party_and_dedupes(monkeypatch):
    recs = recorded_tile_records()
    good = connected(recs["panos"][0])
    meta = {
        "id": good["id"],
        "lat": good["lat"],
        "lon": good["lon"],
        "source": "launch",
        "date": "2024-07",
        "links": good["links"],
        "historical": [
            {"id": official_id(2), "date": "2023-05", "lat": 1, "lon": 2, "source": "launch"},
            {"id": official_id(2), "date": "2023-05", "lat": 1, "lon": 2, "source": "launch"},
            {"id": photosphere_id(3), "date": "2022-01", "lat": 1, "lon": 2, "source": "x"},
            {"id": None, "date": None, "lat": 1, "lon": 2, "source": None},
        ],
    }
    patch_streetview(monkeypatch, [sl_pano(good)])
    monkeypatch.setattr(nearest._sv, "find_panorama_by_id", lambda pid, *a, **k: as_sl(meta))

    stack = historical_stack(good["lat"], good["lon"])
    ids = [e["id"] for e in stack]
    assert ids.count(official_id(2)) == 1, "deduped by id"
    assert photosphere_id(3) not in ids, "HARD RULE: no third-party in the stack"
    assert all(i is not None for i in ids)


def test_historical_stack_empty_when_no_coverage(monkeypatch):
    patch_streetview(monkeypatch, [])
    assert historical_stack(Q_LAT, Q_LON) == []
