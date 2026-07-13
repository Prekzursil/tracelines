"""HARD RULE tests: nearest coverage is always official car coverage, never a
photosphere/photopet, even when a photosphere is strictly closer."""

import base64

import pytest

from svcoverage.models import Pano, Source, is_official_panoid
from svcoverage.nearest import nearest_official


def official_id(seed: int) -> str:
    """A structurally-valid official pano id: 22 url-safe-b64 chars, 16 bytes."""
    return base64.urlsafe_b64encode(seed.to_bytes(16, "big")).decode().rstrip("=")


def photosphere_id(seed: int) -> str:
    """A third-party id shape (CIHM0og prefix), rejected by is_official_panoid."""
    return ("CIHM0ogKEICAg" + str(seed).rjust(9, "0"))[:22]


def mk(seed, lon, lat, tp=False, deg=2):
    pid = photosphere_id(seed) if tp else official_id(seed)
    return Pano(
        id=pid,
        lon=lon,
        lat=lat,
        source=Source.GOOGLE,
        is_third_party=tp,
        neighbors=[f"nb{seed}_{i}" for i in range(deg)],
    )


Q_LON, Q_LAT = 26.050430, 44.435072


def test_hard_rule_skips_closer_photosphere():
    # Photosphere sits exactly on the query point; official is ~48 m away.
    photosphere = mk(1, Q_LON, Q_LAT, tp=True)  # 0 m
    official = mk(2, Q_LON + 0.0006, Q_LAT, tp=False)  # ~48 m
    ranked = nearest_official([photosphere, official], Q_LON, Q_LAT)
    assert ranked, "must find an official pano"
    assert ranked[0].id == official.id
    assert all(not p.is_third_party for p in ranked), "no third-party may survive"
    assert all(is_official_panoid(p.id) for p in ranked)
    assert photosphere not in ranked


def test_only_photospheres_returns_empty():
    only_tp = [mk(1, Q_LON, Q_LAT, tp=True), mk(2, Q_LON + 0.001, Q_LAT, tp=True)]
    assert nearest_official(only_tp, Q_LON, Q_LAT) == []


def test_isolated_official_dot_excluded_when_connected_required():
    dot = mk(10, Q_LON, Q_LAT, tp=False, deg=0)  # degree 0 => a "circle"
    line = mk(11, Q_LON + 0.0006, Q_LAT, tp=False, deg=2)
    ranked = nearest_official([dot, line], Q_LON, Q_LAT, require_connected=True)
    assert ranked[0].id == line.id
    ranked2 = nearest_official([dot, line], Q_LON, Q_LAT, require_connected=False)
    assert ranked2[0].id == dot.id


def test_ordering_is_by_distance():
    near = mk(20, Q_LON + 0.0003, Q_LAT, tp=False)
    far = mk(21, Q_LON + 0.0030, Q_LAT, tp=False)
    ranked = nearest_official([far, near], Q_LON, Q_LAT)
    assert [p.id for p in ranked] == [near.id, far.id]


@pytest.mark.network
def test_live_nearest_is_official_car_coverage():
    """Live: the user's coordinates return official car coverage, never a photosphere."""
    from svcoverage.nearest import find_nearest_coverage

    res = find_nearest_coverage(Q_LAT, Q_LON, verify_source=True)
    assert res is not None, "expected coverage near central Bucharest"
    p = res.pano
    assert p.is_third_party is False, "HARD RULE: must not be third-party"
    assert is_official_panoid(p.id), "HARD RULE: must be a whitelisted official id"
    assert p.sv_source in ("launch", "scout"), f"expected car/trekker, got {p.sv_source}"
    assert p.degree >= 1, "must be on a continuous line, not an isolated dot"
    assert res.distance_m < 200
