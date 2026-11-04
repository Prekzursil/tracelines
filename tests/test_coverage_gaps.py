"""Hermetic tests closing the remaining per-module gaps.

models.py (pano-id guard arcs), fuse.py (degenerate segment under dedupe),
probe.py (provider fetch error), pipeline.py (unavailable provider) and
stitch.py's pure BFS fallback branches — all offline, all deterministic.
"""

from tracelines import pipeline as pipe
from tracelines import probe as probe_mod
from tracelines.config import BBox, Settings
from tracelines.fuse import fuse
from tracelines.models import CoverageSegment, Pano, Source, is_official_panoid
from tracelines.providers.base import Provider
from tracelines.stitch import stitch_panos

BBOX = BBox(26.0, 44.0, 26.01, 44.01)


# ---- models.is_official_panoid: prefix + undecodable arcs ----------------------


def test_official_prefix_rejected_even_with_valid_shape():
    # 22 chars, valid terminal char, decodes to 16 bytes — but a UGC prefix
    for prefix in ("CIHM", "CIAB", "AF1Q"):
        pid = (prefix + "0ogKEICAgICfxxxxxA")[:22]
        assert len(pid) == 22 and pid[-1] == "A", pid
        assert not is_official_panoid(pid), f"{prefix}-prefixed id must be rejected"


def test_undecodable_base64_rejected():
    # '*' is outside both the url-safe and the standard base64 alphabets
    assert not is_official_panoid("*********************A")


# ---- models.CoverageSegment.to_geojson_feature: is_pano flag -------------------


def test_geojson_feature_carries_is_pano_when_set():
    seg = CoverageSegment(
        coords=[(26.0, 44.0), (26.001, 44.0)], source=Source.MAPILLARY, is_pano=True
    )
    assert seg.to_geojson_feature()["properties"]["is_pano"] is True
    seg2 = CoverageSegment(
        coords=[(26.0, 44.0), (26.001, 44.0)], source=Source.MAPILLARY, is_pano=False
    )
    assert seg2.to_geojson_feature()["properties"]["is_pano"] is False


# ---- fuse: degenerate segment inside the dedupe loop ---------------------------


def test_dedupe_skips_degenerate_segment_in_loop():
    s = Settings(dedupe=True, dedupe_buffer_m=20.0, dedupe_min_overlap=0.5)
    good = CoverageSegment(coords=[(26.0, 44.0), (26.001, 44.0)], source=Source.GOOGLE)
    stub = CoverageSegment(coords=[(26.0, 44.0)], source=Source.MAPILLARY)  # n_points == 1
    out = fuse({"google": [good], "mapillary": [stub]}, s)
    assert out == [good]


def test_dedupe_lat_fallback_for_empty_coords():
    s = Settings(dedupe=True, dedupe_buffer_m=20.0, dedupe_min_overlap=0.5)
    empty = CoverageSegment(coords=[], source=Source.GOOGLE)
    a = CoverageSegment(coords=[(26.0, 44.0), (26.001, 44.0)], source=Source.GOOGLE)
    # b is disjoint from a so both survive; only the lat0 fallback is under test
    b = CoverageSegment(coords=[(26.5, 44.5), (26.501, 44.5)], source=Source.MAPILLARY)
    # empty-coords segment sorts first -> lat0 falls back to the 44.4 default
    out = fuse({"google": [empty, a], "mapillary": [b]}, s)
    assert empty not in out and a in out and b in out


# ---- probe / pipeline: provider failure and unavailability ---------------------


class Failing(Provider):
    source = Source.GOOGLE

    async def fetch(self, bbox, settings, cache):
        raise RuntimeError("provider exploded")


class Unavailable(Provider):
    source = Source.MAPILLARY

    def available(self):
        return False, "needs a token"

    async def fetch(self, bbox, settings, cache):  # pragma: no cover - unreachable
        raise AssertionError("never called")


def test_probe_reports_provider_fetch_error(monkeypatch):
    monkeypatch.setattr(probe_mod, "get_provider", lambda n: Failing())
    out = probe_mod.density_probe(BBOX, ["google"], Settings(cache_enabled=False))
    assert out["google"]["available"] is True
    assert "RuntimeError: provider exploded" in out["google"]["error"]


def test_pipeline_reports_unavailable_provider(monkeypatch):
    monkeypatch.setattr(pipe, "get_provider", lambda n: Unavailable())
    segs, meta = pipe.extract(BBOX, ["mapillary"], Settings(cache_enabled=False))
    assert segs == []
    assert meta["by_source_stats"]["mapillary"] == {"unavailable": "needs a token"}


# ---- stitch: pure BFS fallback branches ----------------------------------------


def panos_with(edges):
    ids = sorted({n for e in edges for n in e})
    return [
        Pano(
            id=i,
            lon=26.0 + k * 0.0005,
            lat=44.0,
            source=Source.GOOGLE,
            neighbors=[v for (a, b) in edges if a == i for v in [b]]
            + [u for (a, b) in edges if b == i for u in [a]],
        )
        for k, i in enumerate(ids)
    ]


def pure(monkeypatch, edges, min_run=2):
    from tracelines import stitch as stitch_mod

    monkeypatch.setattr(stitch_mod, "LineString", None)  # force the BFS fallback
    return stitch_panos(panos_with(edges), Source.GOOGLE, min_run)


def test_pure_fallback_line(monkeypatch):
    segs = pure(monkeypatch, [("a", "b"), ("b", "c"), ("c", "d")])
    assert len(segs) == 1
    # the walk may start from either endpoint (edge-set order is not fixed)
    assert sorted(segs[0].pano_ids) == ["a", "b", "c", "d"]


def test_pure_fallback_cycle_uses_every_node_as_start(monkeypatch):
    # a pure cycle: every node has degree 2 -> starts == list(adj); the walk
    # cannot extend past a start (cur not in starts is always False)
    segs = pure(monkeypatch, [("a", "b"), ("b", "c"), ("c", "a")])
    assert segs, "cycle edges are still emitted"
    assert all(s.n_points == 2 for s in segs)
    assert {i for s in segs for i in s.pano_ids} == {"a", "b", "c"}


def test_pure_fallback_junction_splits(monkeypatch):
    # star around 'hub' -> degree-3 junction splits the walk
    segs = pure(monkeypatch, [("hub", "a"), ("hub", "b"), ("hub", "c")])
    assert len(segs) == 3
    assert all(s.n_points == 2 for s in segs)


def test_pure_fallback_min_run_drops_short_chain(monkeypatch):
    segs = pure(monkeypatch, [("a", "b")], min_run=3)
    assert segs == []


def test_pure_fallback_two_disjoint_lines(monkeypatch):
    segs = pure(monkeypatch, [("a", "b"), ("b", "c"), ("x", "y"), ("y", "z")])
    assert len(segs) == 2
    covered = {tuple(sorted(s.pano_ids)) for s in segs}
    assert ("a", "b", "c") in covered and ("x", "y", "z") in covered
