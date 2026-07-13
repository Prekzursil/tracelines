from tracelines.providers.kartaview import _coerce_coords, parse_sequences


def test_coerce_geojson_coords():
    assert _coerce_coords([[26.0, 44.0], [26.1, 44.1]]) == [(26.0, 44.0), (26.1, 44.1)]


def test_coerce_dict_points_lat_lng():
    c = _coerce_coords([{"lat": 44.0, "lng": 26.0}, {"lat": 44.1, "lon": 26.1}])
    assert c == [(26.0, 44.0), (26.1, 44.1)]


def test_coerce_track_string():
    assert _coerce_coords("44.0,26.0;44.1,26.1") == [(26.0, 44.0), (26.1, 44.1)]


def test_parse_sequences_geojson_geometry():
    payload = {
        "result": [
            {
                "id": 123,
                "geometry": {"type": "LineString", "coordinates": [[26.0, 44.0], [26.001, 44.0]]},
                "date_added": "2023-05-01",
            }
        ]
    }
    segs = parse_sequences(payload, min_run=2)
    assert len(segs) == 1
    assert segs[0].source.value == "kartaview"
    assert segs[0].id == "123"
    assert segs[0].capture_date == "2023-05"


def test_parse_sequences_drops_short():
    assert parse_sequences([{"id": 1, "track": [{"lat": 44.0, "lng": 26.0}]}], min_run=2) == []


def test_parse_sequences_empty_payload():
    assert parse_sequences({}, min_run=2) == []
    assert parse_sequences([], min_run=2) == []
