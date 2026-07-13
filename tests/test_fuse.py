from tracelines.config import Settings
from tracelines.fuse import fuse
from tracelines.models import CoverageSegment, Source


def seg(src, coords):
    return CoverageSegment(coords=coords, source=src)


def test_union_default_keeps_all():
    s = Settings(dedupe=False)
    out = fuse(
        {
            "google": [seg(Source.GOOGLE, [(26.0, 44.0), (26.001, 44.0)])],
            "mapillary": [seg(Source.MAPILLARY, [(26.0, 44.0), (26.0, 44.001)])],
        },
        s,
    )
    assert len(out) == 2


def test_dedupe_drops_overlapping_lower_priority():
    s = Settings(dedupe=True, dedupe_buffer_m=20.0, dedupe_min_overlap=0.5)
    line = [(26.0, 44.0), (26.001, 44.0), (26.002, 44.0)]
    dup = [(26.0, 44.00001), (26.001, 44.00001), (26.002, 44.00001)]  # ~1 m offset
    out = fuse({"google": [seg(Source.GOOGLE, line)], "mapillary": [seg(Source.MAPILLARY, dup)]}, s)
    srcs = [o.source for o in out]
    assert Source.GOOGLE in srcs
    assert Source.MAPILLARY not in srcs  # dropped as duplicate of higher-priority google


def test_dedupe_keeps_disjoint_lines():
    s = Settings(dedupe=True, dedupe_buffer_m=20.0, dedupe_min_overlap=0.5)
    out = fuse(
        {
            "google": [seg(Source.GOOGLE, [(26.0, 44.0), (26.001, 44.0)])],
            "mapillary": [seg(Source.MAPILLARY, [(26.5, 44.5), (26.501, 44.5)])],
        },
        s,
    )
    assert len(out) == 2


def test_dedupe_never_evicts_same_source(monkeypatch):
    # Two overlapping GOOGLE segments must both survive — a source never evicts its own (B4).
    s = Settings(dedupe=True, dedupe_buffer_m=20.0, dedupe_min_overlap=0.5)
    line = [(26.0, 44.0), (26.001, 44.0), (26.002, 44.0)]
    dup = [(26.0, 44.00001), (26.001, 44.00001), (26.002, 44.00001)]
    out = fuse({"google": [seg(Source.GOOGLE, line), seg(Source.GOOGLE, dup)]}, s)
    assert len(out) == 2
