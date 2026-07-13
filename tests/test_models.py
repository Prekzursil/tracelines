from tracelines.models import (
    CoverageSegment,
    Pano,
    Source,
    haversine_m,
    is_official_panoid,
    line_length_m,
)


def test_is_official_panoid_accepts_real_official_ids():
    # real 22-char official ids observed live (terminal char in {A,Q,g,w})
    for pid in (
        "Ui8V1HlfwJBw8pnmoShJfw",
        "7i74dqnFoqr0Tf6-F63dPg",
        "TMMA3gnNxaZAU6OvG8kXXA",
        "5KdWVs-fHDhofLYGzJ6IvQ",
    ):
        assert is_official_panoid(pid), pid


def test_is_official_panoid_rejects_third_party_and_malformed():
    assert not is_official_panoid("CIHM0ogKEICAgICfxxxxxx")  # photosphere prefix
    assert not is_official_panoid("CIAB0ogKEICAgICfxxxxxx")  # new UGC prefix
    assert not is_official_panoid("AF1QipMExampleUserPhotoSphereId")  # >22 / AF1Q
    assert not is_official_panoid("tooshort")  # wrong length
    assert not is_official_panoid("Ui8V1HlfwJBw8pnmoShJfz")  # terminal not in {A,Q,g,w}
    assert not is_official_panoid("")
    assert not is_official_panoid(None)  # type: ignore[arg-type]


def test_haversine_one_degree_latitude():
    d = haversine_m(26.0, 44.0, 26.0, 45.0)
    assert 110_000 < d < 112_000


def test_line_length_sums_and_handles_single_point():
    coords = [(26.0, 44.0), (26.0, 44.001), (26.0, 44.002)]
    seg_len = haversine_m(26.0, 44.0, 26.0, 44.001)
    assert abs(line_length_m(coords) - 2 * seg_len) < 1e-6
    assert line_length_m([(26.0, 44.0)]) == 0.0
    assert line_length_m([]) == 0.0


def test_segment_geojson_shape():
    seg = CoverageSegment(
        coords=[(26.0, 44.0), (26.001, 44.0)],
        source=Source.GOOGLE,
        id="g1",
        pano_ids=["a", "b"],
        capture_date="2024-07",
    )
    f = seg.to_geojson_feature()
    assert f["type"] == "Feature"
    assert f["geometry"]["type"] == "LineString"
    assert len(f["geometry"]["coordinates"]) == 2
    assert f["properties"]["source"] == "google"
    assert f["properties"]["capture_date"] == "2024-07"
    assert f["properties"]["length_m"] > 0
    assert f["properties"]["pano_ids"] == ["a", "b"]


def test_pano_degree():
    p = Pano(id="x", lon=26.0, lat=44.0, source=Source.GOOGLE, neighbors=["a", "b"])
    assert p.degree == 2
    assert Pano(id="y", lon=26.0, lat=44.0, source=Source.GOOGLE).degree == 0
