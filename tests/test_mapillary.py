import pytest

from svcoverage.providers.mapillary import decode_sequence_tile, georef_layer, group_and_merge
from svcoverage.tiles import tile_bounds


def test_georef_layer_transforms_to_lonlat():
    x, y, z = 9410, 5967, 14
    w, s, e, n = tile_bounds(x, y, z)
    layer = {
        "extent": 4096,
        "features": [
            {
                "geometry": {"type": "LineString", "coordinates": [[0, 0], [4096, 4096]]},
                "properties": {"id": "seq1", "is_pano": False, "captured_at": 1600000000000},
            }
        ],
    }
    pieces = georef_layer(layer, x, y, z)
    assert len(pieces) == 1
    (lon0, lat0), (lon1, lat1) = pieces[0]["coords"]
    # (0,0) -> SW corner; (extent,extent) -> NE corner (y increases up)
    assert abs(lon0 - w) < 1e-6 and abs(lat0 - s) < 1e-6
    assert abs(lon1 - e) < 1e-6 and abs(lat1 - n) < 1e-6
    assert pieces[0]["seq"] == "seq1"


def test_group_and_merge_joins_pieces_and_drops_short():
    pieces = [
        {
            "seq": "A",
            "is_pano": False,
            "captured_at": None,
            "coords": [(26.0, 44.0), (26.001, 44.0)],
        },
        {
            "seq": "A",
            "is_pano": False,
            "captured_at": None,
            "coords": [(26.001, 44.0), (26.002, 44.0)],
        },
        {
            "seq": "B",
            "is_pano": True,
            "captured_at": None,
            "coords": [(27.0, 44.0)],
        },  # 1 pt -> dropped
    ]
    segs = group_and_merge(pieces, min_run=2)
    a = [s for s in segs if s.id.startswith("A")]
    assert a, "sequence A should be present"
    assert a[0].n_points >= 3  # two pieces merged into one line
    assert a[0].source.value == "mapillary"
    assert all(not s.id.startswith("B") for s in segs)


def test_group_and_merge_is_pano_flag_preserved():
    pieces = [
        {"seq": "P", "is_pano": True, "captured_at": None, "coords": [(26.0, 44.0), (26.001, 44.0)]}
    ]
    segs = group_and_merge(pieces, min_run=2)
    assert len(segs) == 1
    assert segs[0].is_pano is True


def test_decode_sequence_tile_roundtrip():
    """Encode a real MVT sequence layer, decode it back through the provider."""
    mvt = pytest.importorskip("mapbox_vector_tile")
    shapely_geom = pytest.importorskip("shapely.geometry")
    x, y, z = 9410, 5967, 14
    w, s, e, n = tile_bounds(x, y, z)
    line = shapely_geom.LineString([(0, 0), (2048, 2048), (4096, 4096)])
    data = mvt.encode(
        {
            "name": "sequence",
            "features": [{"geometry": line, "properties": {"id": "seqX", "is_pano": False}}],
        }
    )
    pieces = decode_sequence_tile(data, x, y, z)
    assert len(pieces) == 1
    assert pieces[0]["seq"] == "seqX"
    for lon, lat in pieces[0]["coords"]:
        assert w - 1e-6 <= lon <= e + 1e-6
        assert s - 1e-6 <= lat <= n + 1e-6
    assert len(pieces[0]["coords"]) >= 2
