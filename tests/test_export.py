import importlib.util
import json

import pytest

from svcoverage.export import summary_stats, to_feature_collection, write_geojson, write_gpkg
from svcoverage.models import CoverageSegment, Source


def seg(src, coords, date=None):
    return CoverageSegment(coords=coords, source=src, capture_date=date)


def test_feature_collection_valid():
    segs = [
        seg(Source.GOOGLE, [(26.0, 44.0), (26.001, 44.0)]),
        seg(Source.MAPILLARY, [(26.0, 44.0), (26.0, 44.001)]),
    ]
    fc = to_feature_collection(segs)
    assert fc["type"] == "FeatureCollection"
    assert len(fc["features"]) == 2


def test_degenerate_segment_dropped():
    assert to_feature_collection([seg(Source.GOOGLE, [(26.0, 44.0)])])["features"] == []


def test_write_geojson_roundtrip(tmp_path):
    p = tmp_path / "out.geojson"
    write_geojson([seg(Source.GOOGLE, [(26.0, 44.0), (26.001, 44.0)])], str(p))
    data = json.loads(p.read_text(encoding="utf-8"))
    assert data["features"][0]["geometry"]["type"] == "LineString"


def test_summary_stats():
    segs = [
        seg(Source.GOOGLE, [(26.0, 44.0), (26.01, 44.0)], "2024-07"),
        seg(Source.MAPILLARY, [(26.0, 44.0), (26.0, 44.01)], "2021-03"),
    ]
    st = summary_stats(segs)
    assert st["segments"] == 2
    assert st["total_km"] > 0
    assert "google" in st["by_source"] and "mapillary" in st["by_source"]
    assert st["median_capture_year"] in ("2021", "2024")


def test_write_gpkg_graceful_without_geopandas(tmp_path):
    if importlib.util.find_spec("geopandas") is not None:
        pytest.skip("geopandas installed; the skip-path is not exercised here")
    ok = write_gpkg([seg(Source.GOOGLE, [(26.0, 44.0), (26.001, 44.0)])], str(tmp_path / "x.gpkg"))
    assert ok is False
