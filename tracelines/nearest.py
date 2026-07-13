"""Nearest CONTINUOUS-coverage (official car) panorama to a point.

HARD RULE (never violated): this never returns a third-party panorama — no user
photosphere, no "photopet"/photo upload. Only official Google coverage, and by
default only nodes that belong to a continuous line (link-degree >= 1), i.e. a
"blue line" node, never an isolated official dot.

The selection logic (`nearest_official`) is a pure function so the HARD RULE is
unit-tested without any network. `find_nearest_coverage` is the live wrapper.

VERIFIED (2026-07-13, 7438 panos across 49 z17 tiles over central Bucharest):
get_coverage_tile returns ONLY official coverage — 0 third-party, all 22-char
ids. Photospheres/photopets live in a SEPARATE layer reachable only via
find_panorama(search_third_party=True) (ids 'CIHM...', source 'photos:*'). This
module and the Google provider read ONLY coverage tiles and never that path, so a
photosphere cannot enter the candidate set. The is_third_party check below is
therefore defense-in-depth; the real "circle" to exclude is the isolated official
dot (degree 0).
"""

from __future__ import annotations

from dataclasses import dataclass

from .models import Pano, Source, haversine_m, is_official_panoid

try:
    from streetlevel import streetview as _sv

    _AVAILABLE = True
    _IMPORT_ERR = ""
except Exception as e:  # pragma: no cover
    _AVAILABLE = False
    _IMPORT_ERR = f"{type(e).__name__}: {e}"

Z = 17
KEEP_SOURCES_CAR = ("launch",)
KEEP_SOURCES_TREKKER = ("launch", "scout")


@dataclass
class Nearest:
    pano: Pano
    distance_m: float


def _fmt_date(d) -> str | None:
    if d is None:
        return None
    if isinstance(d, str):
        return d
    y, m = getattr(d, "year", None), getattr(d, "month", None)
    if y and m:
        return f"{int(y):04d}-{int(m):02d}"
    return f"{int(y):04d}" if y else str(d)


def build_streetview_url(
    pano_id: str | None, lat: float | None = None, lon: float | None = None
) -> str:
    """Keyless Google Maps URL that opens a specific Street View panorama.

    Uses the documented Maps URL API (``map_action=pano``), which needs no API key.
    Falls back to a viewpoint when only coordinates are known.
    """
    if pano_id:
        return f"https://www.google.com/maps/@?api=1&map_action=pano&pano={pano_id}"
    if lat is not None and lon is not None:
        return f"https://www.google.com/maps/@?api=1&map_action=pano&viewpoint={lat},{lon}"
    return "https://www.google.com/maps"


def nearest_official(
    cands: list[Pano], lon: float, lat: float, require_connected: bool = True
) -> list[Pano]:
    """Pure: apply the HARD RULE and return official candidates, nearest first.

    Drops every third-party pano (photosphere/photopet) via BOTH the streetlevel
    denylist (is_third_party) AND the positive is_official_panoid whitelist. With
    require_connected, also drops isolated official dots (degree 0).
    """
    official = [p for p in cands if not p.is_third_party and is_official_panoid(p.id)]
    if require_connected:
        official = [p for p in official if p.degree >= 1]
    official.sort(key=lambda p: haversine_m(lon, lat, p.lon, p.lat))
    return official


def _pano_from_sl(p) -> Pano:
    return Pano(
        id=p.id,
        lon=p.lon,
        lat=p.lat,
        source=Source.GOOGLE,
        heading=getattr(p, "heading", None),
        is_third_party=bool(p.is_third_party),
        neighbors=[lk.pano.id for lk in (getattr(p, "links", None) or []) if lk.pano],
    )


def find_nearest_coverage(
    lat: float,
    lon: float,
    *,
    radius_tiles: int = 1,
    require_connected: bool = True,
    verify_source: bool = True,
    include_trekker: bool = False,
) -> Nearest | None:
    """Live: nearest official continuous-coverage pano to (lat, lon).

    Never returns a third-party pano. Searches the z17 tile containing the point
    plus a (2*radius_tiles+1)^2 neighborhood so border cases are covered.
    """
    if not _AVAILABLE:
        raise RuntimeError(f"streetlevel not importable: {_IMPORT_ERR}")

    tx, ty = _sv.wgs84_to_tile_coord(lat, lon, Z)
    seen: dict[str, Pano] = {}
    for dx in range(-radius_tiles, radius_tiles + 1):
        for dy in range(-radius_tiles, radius_tiles + 1):
            for p in _sv.get_coverage_tile(tx + dx, ty + dy):
                if p.id not in seen:
                    seen[p.id] = _pano_from_sl(p)

    ranked = nearest_official(list(seen.values()), lon, lat, require_connected)
    if not ranked:
        return None

    keep = KEEP_SOURCES_TREKKER if include_trekker else KEEP_SOURCES_CAR
    for cand in ranked:
        # HARD RULE belt-and-suspenders: never a third-party pano
        if cand.is_third_party:
            continue
        if verify_source:
            q = _sv.find_panorama_by_id(cand.id)
            src = getattr(q, "source", None) if q else None
            cand.sv_source = src
            cand.date = _fmt_date(getattr(q, "date", None)) if q else None
            if src is not None and src not in keep:
                continue  # trekker/indoor/etc. — want car lines
        return Nearest(pano=cand, distance_m=haversine_m(lon, lat, cand.lon, cand.lat))

    # Every candidate failed the (optional) source filter but all were official +
    # connected — return the nearest official connected node (still never third-party).
    best = ranked[0]
    return Nearest(pano=best, distance_m=haversine_m(lon, lat, best.lon, best.lat))


def historical_stack(lat: float, lon: float) -> list[dict]:
    """Historical official coverage at a point: the stack of past panoramas, newest first.

    Finds the nearest official pano, fetches its metadata, and returns its ``historical``
    list (Google keeps prior captures of the same location). Each entry is JSON-able with a
    keyless Street View URL. Never includes third-party panos.
    """
    if not _AVAILABLE:
        raise RuntimeError(f"streetlevel not importable: {_IMPORT_ERR}")
    res = find_nearest_coverage(lat, lon, verify_source=False)
    if res is None:
        return []
    q = _sv.find_panorama_by_id(res.pano.id)
    stack: list[dict] = []
    seen: set[str] = set()

    def add(pp) -> None:
        if pp is None or getattr(pp, "id", None) in seen:
            return
        if not is_official_panoid(pp.id):
            return  # HARD RULE: never a third-party pano in the stack
        seen.add(pp.id)
        stack.append(
            {
                "id": pp.id,
                "date": _fmt_date(getattr(pp, "date", None)),
                "lat": pp.lat,
                "lon": pp.lon,
                "sv_source": getattr(pp, "source", None),
                "sv_url": build_streetview_url(pp.id, pp.lat, pp.lon),
            }
        )

    if q is not None:
        add(q)
        for h in getattr(q, "historical", None) or []:
            add(h)
    stack.sort(key=lambda d: d["date"] or "", reverse=True)
    return stack
