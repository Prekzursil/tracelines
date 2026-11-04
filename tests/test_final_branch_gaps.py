"""Final branch-gap closures across modules (all hermetic, all deterministic)."""

import asyncio
import json
from pathlib import Path
from types import SimpleNamespace

from tracelines import pipeline as pipe
from tracelines import probe as probe_mod
from tracelines.cache import Cache
from tracelines.config import BBox, Settings
from tracelines.fuse import fuse
from tracelines.models import CoverageSegment, Pano, Source
from tracelines.providers.mapillary import _as_lines
from tracelines.stitch import _undirected_edges, stitch_panos

BBOX = BBox(26.0, 44.0, 26.01, 44.01)


# ---- mapillary._as_lines: empty merged geometry -------------------------------


def test_as_lines_empty_geometry_returns_empty():
    from shapely.geometry import MultiLineString

    assert _as_lines(MultiLineString([])) == []


# ---- fuse: near-miss overlap (query hit, below the drop threshold) --------------


def test_dedupe_keeps_partial_overlap_below_threshold():
    s = Settings(dedupe=True, dedupe_buffer_m=12.0, dedupe_min_overlap=0.6)
    # ~76 m google line; ~167 m mapillary line crossing perpendicular at its
    # middle: only ~24 m of the mapillary line lies inside the 12 m buffer
    # (0.14 of its length) -> below the 0.6 drop threshold, both survive.
    a = CoverageSegment(coords=[(26.0, 44.0), (26.001, 44.0)], source=Source.GOOGLE)
    b = CoverageSegment(coords=[(26.0005, 44.0), (26.0005, 44.0015)], source=Source.MAPILLARY)
    out = fuse({"google": [a], "mapillary": [b]}, s)
    assert len(out) == 2


# ---- stitch: edge-free panos, ghost neighbors, dates on kept segments ----------


def test_stitch_panos_with_no_edges_returns_empty():
    panos = [Pano(id="lone", lon=26.0, lat=44.0, source=Source.GOOGLE)]
    assert stitch_panos(panos, Source.GOOGLE) == []


def test_stitch_ignores_neighbors_to_dropped_nodes():
    panos = [
        Pano(id="a", lon=26.0, lat=44.0, source=Source.GOOGLE, neighbors=["b"]),
        Pano(id="b", lon=26.001, lat=44.0, source=Source.GOOGLE, neighbors=["a"]),
        Pano(
            id="c", lon=26.002, lat=44.0, source=Source.GOOGLE, neighbors=["ghost", "c"]
        ),  # ghost absent; c is a self-loop
    ]
    idx = {p.id: p for p in panos}
    assert _undirected_edges(panos, idx) == {("a", "b")}


def test_stitch_shapely_keeps_capture_dates():
    panos = [
        Pano(id="a", lon=26.0, lat=44.0, source=Source.GOOGLE, neighbors=["b"], date="2024-07"),
        Pano(id="b", lon=26.001, lat=44.0, source=Source.GOOGLE, neighbors=["a"], date="2022-03"),
    ]
    segs = stitch_panos(panos, Source.GOOGLE, min_run=2)
    assert segs and segs[0].capture_date == "2022-03", "earliest capture date on the line"


# ---- google precision: by-id link already present is not duplicated ------------


def test_precision_does_not_duplicate_existing_neighbor(monkeypatch, tmp_path):
    from tracelines.providers import google_sl
    from tracelines.providers.google_sl import GoogleStreetlevelProvider

    recs = json.loads(
        (
            Path(__file__).parent / "fixtures" / "google" / "coverage_tile_z17_75020_47439.json"
        ).read_text(encoding="utf-8")
    )
    car = recs["panos"][1]  # a pano WITH recorded intra-tile links
    assert car["links"]
    targets = [r for r in recs["panos"] if r["id"] in car["links"]]

    def as_tile_pano(rec):
        return SimpleNamespace(
            id=rec["id"],
            lat=rec["lat"],
            lon=rec["lon"],
            is_third_party=False,
            links=[SimpleNamespace(pano=SimpleNamespace(id=n)) for n in rec.get("links", [])],
        )

    async def tile(tx, ty, session):
        return [as_tile_pano(car)] + [as_tile_pano(r) for r in targets]

    async def byid(panoid, session):
        # resolves with the SAME neighbor set the coverage tile already gave
        return SimpleNamespace(
            id=panoid,
            source="launch",
            date=None,
            links=[SimpleNamespace(pano=SimpleNamespace(id=n)) for n in car["links"]],
        )

    import aiohttp as real_aiohttp

    # re-bind aiohttp too: a failed streetlevel import nulls both bindings
    monkeypatch.setattr(google_sl, "aiohttp", real_aiohttp)
    monkeypatch.setattr(
        google_sl,
        "_sv",
        SimpleNamespace(get_coverage_tile_async=tile, find_panorama_by_id_async=byid),
    )
    bbox = BBox(car["lon"] - 1e-4, car["lat"] - 1e-4, car["lon"] + 1e-4, car["lat"] + 1e-4)
    res = asyncio.run(
        GoogleStreetlevelProvider().fetch(
            bbox,
            Settings(concurrency=2, timeout=5, max_retries=2, retry_base=0.001, precision=True),
            Cache(str(tmp_path)),
        )
    )
    p = next(pp for pp in res.panos if pp.id == car["id"])
    assert sorted(p.neighbors) == sorted(set(car["links"])), "no duplicate neighbors"


# ---- nearest: historical_stack when by-id metadata is absent --------------------


def test_historical_stack_empty_when_byid_returns_none(monkeypatch):
    from tracelines import nearest as near

    official = SimpleNamespace(
        id="aaaaaaaaaaaaaaaaaaaaaA",
        lat=44.0,
        lon=26.0,
        is_third_party=False,
        # a neighbor keeps the node connected (require_connected)
        links=[SimpleNamespace(pano=SimpleNamespace(id="bbbbbbbbbbbbbbbbbbbbbB"))],
    )
    monkeypatch.setattr(
        near,
        "_sv",
        SimpleNamespace(
            wgs84_to_tile_coord=lambda lat, lon, z: (75020, 47439),
            get_coverage_tile=lambda tx, ty: [official],
            find_panorama_by_id=lambda pid, *a, **k: None,
        ),
    )
    assert near.historical_stack(44.0, 26.0) == []


# ---- probe / pipeline: explicit cache + empty source list ----------------------


def test_probe_with_explicit_cache_and_no_sources(tmp_path):
    async def go():
        cache = Cache(str(tmp_path))
        out = await probe_mod.density_probe_async(BBOX, [], Settings(), cache=cache)
        cache.close()
        return out

    assert asyncio.run(go()) == {}


def test_pipeline_with_explicit_cache(monkeypatch, tmp_path):
    from tracelines.providers.base import Provider

    class Unavailable(Provider):
        source = Source.MAPILLARY

        def available(self):
            return False, "needs a token"

        async def fetch(self, bbox, settings, cache):  # pragma: no cover - unreachable
            raise AssertionError("never called")

    monkeypatch.setattr(pipe, "get_provider", lambda n: Unavailable())

    async def go():
        cache = Cache(str(tmp_path))
        segs, meta = await pipe.extract_async(BBOX, ["mapillary"], Settings(), cache=cache)
        cache.close()
        return segs, meta

    segs, meta = asyncio.run(go())
    assert segs == []
    assert meta["by_source_stats"]["mapillary"] == {"unavailable": "needs a token"}


def test_probe_with_segments_only_provider(monkeypatch):
    from tracelines.providers.base import Provider, ProviderResult

    class SegmentsOnly(Provider):
        source = Source.KARTAVIEW

        async def fetch(self, bbox, settings, cache):
            seg = CoverageSegment(coords=[(26.0, 44.0), (26.001, 44.0)], source=Source.KARTAVIEW)
            return ProviderResult(source=Source.KARTAVIEW, segments=[seg], stats={"n": 1})

    monkeypatch.setattr(probe_mod, "get_provider", lambda n: SegmentsOnly())
    out = probe_mod.density_probe(BBOX, ["kartaview"], Settings(cache_enabled=False))
    assert out["kartaview"]["available"] is True
    assert out["kartaview"]["segments"] == 1
    assert out["kartaview"]["provider_stats"] == {"n": 1}
