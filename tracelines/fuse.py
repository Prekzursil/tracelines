"""Fuse multi-source coverage into one set of segments.

Default = union with provenance (each segment keeps its `source`). Honest: robust
cross-source conflation is hard, so dedup is OPT-IN (settings.dedupe). The dedup is
a transparent buffer-overlap rule: a lower-priority segment is dropped when >=
`dedupe_min_overlap` of its length lies within `dedupe_buffer_m` of an already-kept
higher-or-equal-priority segment.
"""

from __future__ import annotations

import math
from typing import TYPE_CHECKING

from .models import CoverageSegment, Source

if TYPE_CHECKING:
    from .config import Settings

try:
    from shapely.geometry import LineString
    from shapely.strtree import STRtree

    _HAS_SHAPELY = True
except Exception:  # pragma: no cover
    _HAS_SHAPELY = False


def _src_name(s: CoverageSegment) -> str:
    return s.source.value if isinstance(s.source, Source) else str(s.source)


def _deg_buffer(meters: float, lat: float) -> float:
    """Approximate a metric buffer as degrees at a given latitude (Bucharest ~44.4)."""
    lat_m_per_deg = 111_320.0
    lon_m_per_deg = 111_320.0 * max(0.05, math.cos(math.radians(lat)))
    return meters / min(lat_m_per_deg, lon_m_per_deg)


def fuse(
    results_by_source: dict[str, list[CoverageSegment]], settings: Settings
) -> list[CoverageSegment]:
    order = {name: i for i, name in enumerate(settings.source_priority)}

    def prio(seg: CoverageSegment) -> int:
        return order.get(_src_name(seg), len(order))

    all_segs: list[CoverageSegment] = []
    for segs in results_by_source.values():
        all_segs.extend(segs)

    if not settings.dedupe or not _HAS_SHAPELY or len(all_segs) < 2:
        return all_segs

    # Keep higher-priority (lower index) first; drop later segments mostly covered by a kept one.
    ordered = sorted(all_segs, key=prio)
    lat0 = ordered[0].coords[0][1] if ordered and ordered[0].coords else 44.4
    buf_deg = _deg_buffer(settings.dedupe_buffer_m, lat0)

    kept: list[CoverageSegment] = []
    kept_lines: list = []
    for seg in ordered:
        if seg.n_points < 2:
            continue
        line = LineString(seg.coords)
        drop = False
        if kept_lines:
            tree = STRtree(kept_lines)
            for idx in tree.query(line.buffer(buf_deg)):
                i = int(idx)
                # cross-source dedupe only: a source never evicts its own segments (B4)
                if _src_name(kept[i]) == _src_name(seg):
                    continue
                inter = line.intersection(kept_lines[i].buffer(buf_deg))
                if not inter.is_empty and inter.length >= settings.dedupe_min_overlap * line.length:
                    drop = True
                    break
        if not drop:
            kept.append(seg)
            kept_lines.append(line)
    return kept
