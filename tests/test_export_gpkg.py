"""write_gpkg branch tests: the optional-geopandas export, faked deterministically.

The happy path needs a GeoDataFrame; the skip path needs geopandas absent; both
are forced here so the suite passes identically whether or not the host has
geopandas installed (it is an optional extra, not a dev dependency).
"""

import sys
import types

import pytest

from tracelines.export import write_gpkg
from tracelines.models import CoverageSegment, Source


def seg(coords, date=None):
    return CoverageSegment(coords=coords, source=Source.GOOGLE, capture_date=date)


class _FakeGeoDataFrame:
    instances = []

    def __init__(self, rows, geometry=None, crs=None):
        self.rows, self.geometry, self.crs = rows, geometry, crs
        self.written = None
        _FakeGeoDataFrame.instances.append(self)

    def to_file(self, path, layer=None, driver=None):
        self.written = (path, layer, driver)


@pytest.fixture
def fake_geopandas(monkeypatch):
    gpd = types.ModuleType("geopandas")
    gpd.GeoDataFrame = _FakeGeoDataFrame
    monkeypatch.setitem(sys.modules, "geopandas", gpd)
    return gpd


def test_write_gpkg_happy_path_with_fake_geopandas(fake_geopandas, tmp_path):
    out = str(tmp_path / "x.gpkg")
    ok = write_gpkg([seg([(26.0, 44.0), (26.001, 44.0)], "2024-07")], out)
    assert ok is True
    gdf = _FakeGeoDataFrame.instances[-1]
    assert gdf.written == (out, "coverage", "GPKG")
    assert gdf.crs == "EPSG:4326"
    assert len(gdf.geometry) == 1
    assert gdf.rows[0]["source"] == "google"


def test_write_gpkg_custom_layer(fake_geopandas, tmp_path):
    out = str(tmp_path / "layered.gpkg")
    assert write_gpkg([seg([(26.0, 44.0), (26.001, 44.0)])], out, layer="mine")
    assert _FakeGeoDataFrame.instances[-1].written == (out, "mine", "GPKG")


def test_write_gpkg_skips_degenerate_and_false_when_no_geoms(fake_geopandas, tmp_path):
    ok = write_gpkg(
        [seg([(26.0, 44.0)])],  # 1 point -> skipped -> no geometries remain
        str(tmp_path / "y.gpkg"),
    )
    assert ok is False


def test_write_gpkg_false_when_geopandas_import_fails(monkeypatch, tmp_path):
    # None in sys.modules makes `import geopandas` raise ImportError
    monkeypatch.setitem(sys.modules, "geopandas", None)
    ok = write_gpkg([seg([(26.0, 44.0), (26.001, 44.0)])], str(tmp_path / "z.gpkg"))
    assert ok is False
