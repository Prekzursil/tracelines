"""Stitch coverage nodes (panos + graph edges) into continuous polylines.

Primary path uses shapely.ops.linemerge over every edge at once: it fuses runs
that share endpoints and splits at junctions (degree>=3) automatically. A pure
fallback (BFS chain-walk) is used when shapely is absent.

Isolated nodes (degree 0) never form an edge, so they are dropped for free — those
are the "circles". `min_run` (in points) drops short stubs too.
"""

from __future__ import annotations

from .models import CoverageSegment, Pano, Source

try:
    from shapely.geometry import LineString, MultiLineString
    from shapely.ops import linemerge
except Exception:  # pragma: no cover - environment dependent
    LineString = None  # type: ignore[assignment]
    MultiLineString = None  # type: ignore[assignment]
    linemerge = None  # type: ignore[assignment]


def _undirected_edges(panos: list[Pano], idx: dict[str, Pano]) -> set[tuple[str, str]]:
    edges: set[tuple[str, str]] = set()
    for p in panos:
        for nb in p.neighbors:
            if nb in idx and nb != p.id:
                edges.add((p.id, nb) if p.id < nb else (nb, p.id))
    return edges


def stitch_panos(panos: list[Pano], source: Source, min_run: int = 2) -> list[CoverageSegment]:
    idx = {p.id: p for p in panos}
    edges = _undirected_edges(panos, idx)
    if not edges:
        return []
    if LineString is not None and linemerge is not None:
        return _stitch_shapely(edges, idx, source, min_run)
    return _stitch_pure(edges, idx, source, min_run)


def _stitch_shapely(edges, idx, source, min_run) -> list[CoverageSegment]:
    # module-level Optional imports need local narrowing for the type checker;
    # the dispatch in stitch_panos guarantees all three are bound here
    assert LineString is not None and MultiLineString is not None
    assert linemerge is not None
    lines = []
    for a, b in edges:
        pa, pb = idx[a], idx[b]
        lines.append(LineString([(pa.lon, pa.lat), (pb.lon, pb.lat)]))
    merged = linemerge(lines)
    if isinstance(merged, LineString):
        geoms = [merged]
    elif isinstance(merged, MultiLineString):
        geoms = list(merged.geoms)
    else:  # pragma: no cover - defensive: shapely.ops.linemerge over >= 1
        # LineString never yields an empty geometry or a GeometryCollection
        # (shapely contract), and _stitch_shapely is only called with edges.
        geoms = [g for g in getattr(merged, "geoms", []) if g.geom_type == "LineString"]

    cmap = {(round(p.lon, 7), round(p.lat, 7)): p for p in idx.values()}
    segs: list[CoverageSegment] = []
    floor = max(2, min_run)
    for i, g in enumerate(geoms):
        coords = [(float(x), float(y)) for x, y in g.coords]
        if len(coords) < floor:
            continue
        pano_ids, dates = [], []
        for x, y in coords:
            p = cmap.get((round(x, 7), round(y, 7)))
            # pragma: no cover - a cmap miss is not constructible: every
            # linemerge vertex IS an input edge endpoint, i.e. a pano
            # coordinate, and both the map key and this lookup round the
            # identical float to 7 decimals, so the hit is exact.
            if p is not None:  # pragma: no cover - see the reason above
                pano_ids.append(p.id)
                if p.date:
                    dates.append(p.date)
        segs.append(
            CoverageSegment(
                coords=coords,
                source=source,
                id=f"{source.value}-seg-{i}",
                pano_ids=pano_ids,
                capture_date=(min(dates) if dates else None),
            )
        )
    return segs


def _stitch_pure(edges, idx, source, min_run) -> list[CoverageSegment]:
    adj: dict[str, set[str]] = {}
    for a, b in edges:
        adj.setdefault(a, set()).add(b)
        adj.setdefault(b, set()).add(a)
    visited: set[tuple[str, str]] = set()
    segs: list[CoverageSegment] = []
    floor = max(2, min_run)

    def ekey(u, v):
        return (u, v) if u < v else (v, u)

    def emit(path):
        if len(path) < floor:
            return
        coords = [(idx[i].lon, idx[i].lat) for i in path]
        dates = [idx[i].date for i in path if idx[i].date]
        segs.append(
            CoverageSegment(
                coords=coords,
                source=source,
                id=f"{source.value}-seg-{len(segs)}",
                pano_ids=list(path),
                capture_date=(min(dates) if dates else None),
            )
        )

    starts = [n for n in adj if len(adj[n]) != 2] or list(adj)
    for s in starts:
        for nb in list(adj[s]):
            if ekey(s, nb) in visited:
                continue
            visited.add(ekey(s, nb))
            path, prev, cur = [s, nb], s, nb
            while len(adj[cur]) == 2 and cur not in starts:
                nxts = [x for x in adj[cur] if x != prev]
                # pragma: no cover - invariant guard, not constructible:
                # `not nxts` needs a degree-2 node whose two distinct
                # neighbors are both `prev` (impossible in a set-based adj),
                # and an already-visited continuation edge would mean an
                # earlier walk consumed one edge of this degree-2 node but
                # not the other — but every walk that touches a degree-2
                # node passes through it, consuming BOTH edges at once.
                if not nxts or ekey(cur, nxts[0]) in visited:  # pragma: no cover
                    break
                visited.add(ekey(cur, nxts[0]))
                path.append(nxts[0])
                prev, cur = cur, nxts[0]
            emit(path)
    return segs
