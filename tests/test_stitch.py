from svcoverage import stitch as stitch_mod
from svcoverage.models import Pano, Source
from svcoverage.stitch import stitch_panos


def chain(ids, lon0=26.0, lat0=44.0, step=0.0005):
    panos = []
    for i, pid in enumerate(ids):
        nb = []
        if i > 0:
            nb.append(ids[i - 1])
        if i < len(ids) - 1:
            nb.append(ids[i + 1])
        panos.append(
            Pano(id=pid, lon=lon0 + i * step, lat=lat0, source=Source.GOOGLE, neighbors=nb)
        )
    return panos


def test_linear_chain_one_segment():
    segs = stitch_panos(chain(["a", "b", "c", "d"]), Source.GOOGLE, min_run=2)
    assert len(segs) == 1
    assert segs[0].n_points == 4


def test_isolated_pano_dropped():
    panos = chain(["a", "b", "c"]) + [
        Pano(id="iso", lon=27.0, lat=44.0, source=Source.GOOGLE, neighbors=[])
    ]
    segs = stitch_panos(panos, Source.GOOGLE, min_run=2)
    assert len(segs) == 1
    assert "iso" not in set(segs[0].pano_ids)


def test_min_run_drops_short_stub():
    panos = chain(["a", "b"])  # single 2-point edge
    assert stitch_panos(panos, Source.GOOGLE, min_run=3) == []
    assert len(stitch_panos(panos, Source.GOOGLE, min_run=2)) == 1


def test_junction_splits_into_multiple():
    panos = chain(["a", "b", "c"])
    for p in panos:
        if p.id == "b":
            p.neighbors.append("d")
    panos.append(Pano(id="d", lon=26.0005, lat=44.001, source=Source.GOOGLE, neighbors=["b"]))
    segs = stitch_panos(panos, Source.GOOGLE, min_run=2)
    assert len(segs) >= 2  # split at the degree-3 junction


def test_pure_fallback_no_shapely(monkeypatch):
    monkeypatch.setattr(stitch_mod, "_HAS_SHAPELY", False)
    segs = stitch_panos(chain(["a", "b", "c", "d"]), Source.GOOGLE, min_run=2)
    assert len(segs) == 1
    assert segs[0].n_points == 4
