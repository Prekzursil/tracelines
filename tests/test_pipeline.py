from svcoverage import pipeline as pipe
from svcoverage.config import BBox, Settings
from svcoverage.models import CoverageSegment, Pano, Source
from svcoverage.providers.base import Provider, ProviderResult


class FakeGoogle(Provider):
    source = Source.GOOGLE

    async def fetch(self, bbox, settings, cache):
        panos = [
            Pano(id="a", lon=26.0, lat=44.0, source=Source.GOOGLE, neighbors=["b"]),
            Pano(id="b", lon=26.001, lat=44.0, source=Source.GOOGLE, neighbors=["a"]),
        ]
        return ProviderResult(source=Source.GOOGLE, panos=panos, stats={"ok": 1})


class FakeMap(Provider):
    source = Source.MAPILLARY

    async def fetch(self, bbox, settings, cache):
        seg = CoverageSegment(coords=[(26.0, 44.0), (26.0, 44.001)], source=Source.MAPILLARY)
        return ProviderResult(source=Source.MAPILLARY, segments=[seg], stats={"ok": 1})


class Boom(Provider):
    source = Source.KARTAVIEW

    async def fetch(self, bbox, settings, cache):
        raise RuntimeError("provider down")


BBOX = BBox(26.0, 44.0, 26.01, 44.01)


def test_pipeline_stitches_google_and_passes_through_mapillary(monkeypatch):
    monkeypatch.setattr(
        pipe, "get_provider", lambda n: {"google": FakeGoogle(), "mapillary": FakeMap()}[n]
    )
    segs, meta = pipe.extract(BBOX, ["google", "mapillary"], Settings(cache_enabled=False))
    assert len(segs) == 2
    assert meta["counts"]["google"] == 1  # a-b stitched into one line
    assert meta["counts"]["mapillary"] == 1


def test_pipeline_isolates_provider_failure(monkeypatch):
    monkeypatch.setattr(
        pipe, "get_provider", lambda n: {"google": FakeGoogle(), "kartaview": Boom()}[n]
    )
    segs, meta = pipe.extract(BBOX, ["google", "kartaview"], Settings(cache_enabled=False))
    assert len(segs) == 1  # google survived the kartaview failure
    assert "error" in meta["by_source_stats"]["kartaview"]
