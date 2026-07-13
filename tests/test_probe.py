from tracelines import probe as probe_mod
from tracelines.config import BBox, Settings
from tracelines.models import Pano, Source
from tracelines.providers.base import Provider, ProviderResult


class FakeGoogle(Provider):
    source = Source.GOOGLE

    async def fetch(self, bbox, settings, cache):
        return ProviderResult(
            source=Source.GOOGLE,
            panos=[
                Pano(id="a", lon=26.0, lat=44.0, source=Source.GOOGLE, neighbors=["b"]),
                Pano(id="b", lon=26.001, lat=44.0, source=Source.GOOGLE, neighbors=["a"]),
            ],
            stats={"x": 1},
        )


class Unavailable(Provider):
    source = Source.MAPILLARY

    def available(self):
        return False, "no MAPILLARY_TOKEN"

    async def fetch(self, bbox, settings, cache):  # pragma: no cover - not reached
        return ProviderResult(source=Source.MAPILLARY)


def test_probe_reports_km_and_unavailable(monkeypatch):
    monkeypatch.setattr(
        probe_mod, "get_provider", lambda n: {"google": FakeGoogle(), "mapillary": Unavailable()}[n]
    )
    out = probe_mod.density_probe(
        BBox(26.0, 44.0, 26.01, 44.01), ["google", "mapillary"], Settings(cache_enabled=False)
    )
    assert out["google"]["available"] is True
    assert out["google"]["total_km"] > 0
    assert out["google"]["segments"] == 1
    assert out["mapillary"]["available"] is False
    assert "no MAPILLARY_TOKEN" in out["mapillary"]["reason"]
