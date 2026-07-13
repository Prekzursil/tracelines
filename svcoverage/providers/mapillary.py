"""Mapillary coverage via the `sequence` vector-tile layer (native LineStrings).

Endpoint: https://tiles.mapillary.com/maps/vtp/mly1_public/2/{z}/{x}/{y}?access_token=MLY|...
The `sequence` layer (z6-14) ships continuous driven paths as LineStrings by
construction, so there is no graph to reconstruct. Isolated one-off uploads show up
as singleton/degenerate sequences -> dropped by `min_run` (the "circles"). `is_pano`
is an orthogonal 360-vs-flat flag, not the circle filter.
"""

from __future__ import annotations

import asyncio
import datetime as _dt
import random
from collections import defaultdict
from typing import TYPE_CHECKING

from ..models import CoverageSegment, Source
from ..tiles import tile_bounds, tiles_in_bbox
from .base import Provider, ProviderResult

if TYPE_CHECKING:
    from ..cache import Cache
    from ..config import BBox, Settings

TILE_URL = "https://tiles.mapillary.com/maps/vtp/mly1_public/2/{z}/{x}/{y}"
SEQUENCE_LAYER = "sequence"

try:
    import aiohttp

    _HAS_AIOHTTP = True
except Exception:  # pragma: no cover
    _HAS_AIOHTTP = False
try:
    import mapbox_vector_tile as _mvt

    _HAS_MVT = True
except Exception:  # pragma: no cover
    _HAS_MVT = False
try:
    from shapely.geometry import LineString
    from shapely.ops import linemerge

    _HAS_SHAPELY = True
except Exception:  # pragma: no cover
    _HAS_SHAPELY = False


def _backoff(settings: Settings, attempt: int) -> float:
    b = settings.retry_base * (2**attempt)
    j = settings.request_jitter
    return max(0.0, b * (1.0 + random.uniform(-j, j)))


def _epoch_ms_to_ym(v) -> str | None:
    try:
        d = _dt.datetime.fromtimestamp(int(v) / 1000.0, _dt.timezone.utc)
        return f"{d.year:04d}-{d.month:02d}"
    except Exception:
        return None


# ---- pure, unit-testable transforms (no network) ----------------------------


def georef_layer(layer: dict, x: int, y: int, z: int) -> list[dict]:
    """Georeference a decoded MVT `sequence` layer dict -> line pieces in lon/lat.

    MVT coords are tile-local [0..extent] with y increasing UP (y_coord_down=False),
    so lat = south + (py/extent)*(north-south).
    """
    extent = layer.get("extent", 4096) or 4096
    west, south, east, north = tile_bounds(x, y, z)
    dx, dy = (east - west), (north - south)
    pieces: list[dict] = []
    for feat in layer.get("features", []):
        geom = feat.get("geometry", {})
        props = feat.get("properties", {})
        gtype = geom.get("type")
        if gtype == "LineString":
            coord_lists = [geom.get("coordinates", [])]
        elif gtype == "MultiLineString":
            coord_lists = geom.get("coordinates", [])
        else:
            continue
        seq = props.get("id") or props.get("sequence_id") or props.get("sequence")
        is_pano = bool(props["is_pano"]) if "is_pano" in props else None
        captured = props.get("captured_at")
        for cl in coord_lists:
            pts = [
                (west + (pt[0] / extent) * dx, south + (pt[1] / extent) * dy)
                for pt in cl
                if len(pt) >= 2
            ]
            if len(pts) >= 2:
                pieces.append(
                    {"seq": seq, "is_pano": is_pano, "captured_at": captured, "coords": pts}
                )
    return pieces


def _as_lines(merged):
    if merged.is_empty:
        return []
    if merged.geom_type == "LineString":
        return [merged]
    if merged.geom_type == "MultiLineString":
        return list(merged.geoms)
    return [g for g in getattr(merged, "geoms", []) if g.geom_type == "LineString"]


def group_and_merge(pieces: list[dict], min_run: int = 2) -> list[CoverageSegment]:
    """Group tile-clipped pieces by sequence id and merge into full lines."""
    by_seq: dict = defaultdict(list)
    loose: list[dict] = []
    for pc in pieces:
        if pc.get("seq"):
            by_seq[pc["seq"]].append(pc)
        else:
            loose.append(pc)

    floor = max(2, min_run)
    segs: list[CoverageSegment] = []

    def emit(coords, seq, is_pano, captured):
        if len(coords) < floor:
            return
        segs.append(
            CoverageSegment(
                coords=[(float(a), float(b)) for a, b in coords],
                source=Source.MAPILLARY,
                id=str(seq) if seq is not None else f"mapillary-loose-{len(segs)}",
                capture_date=captured,
                is_pano=is_pano,
                meta={"sequence_id": str(seq)} if seq is not None else {},
            )
        )

    for seq, group in by_seq.items():
        is_pano = next((g["is_pano"] for g in group if g["is_pano"] is not None), None)
        captured = None
        cvals = [g["captured_at"] for g in group if g.get("captured_at")]
        if cvals:
            captured = _epoch_ms_to_ym(min(cvals))
        if _HAS_SHAPELY and len(group) > 1:
            lines = [LineString(g["coords"]) for g in group if len(g["coords"]) >= 2]
            for g in _as_lines(linemerge(lines)) if lines else []:
                emit(list(g.coords), seq, is_pano, captured)
        else:
            for g in group:
                emit(g["coords"], seq, is_pano, captured)

    for pc in loose:
        emit(
            pc["coords"],
            None,
            pc["is_pano"],
            _epoch_ms_to_ym(pc["captured_at"]) if pc.get("captured_at") else None,
        )
    return segs


def decode_sequence_tile(data: bytes, x: int, y: int, z: int) -> list[dict]:
    """MVT bytes -> georeferenced line pieces (decode + georef)."""
    if not _HAS_MVT or not data:
        return []
    try:
        layers = _mvt.decode(data, default_options={"y_coord_down": False})
    except TypeError:  # older mapbox_vector_tile signature
        layers = _mvt.decode(data, y_coord_down=False)
    layer = layers.get(SEQUENCE_LAYER)
    return georef_layer(layer, x, y, z) if layer else []


# ---- provider ---------------------------------------------------------------


class MapillaryProvider(Provider):
    source = Source.MAPILLARY

    def available(self) -> tuple[bool, str]:
        if not _HAS_AIOHTTP:
            return False, "aiohttp not importable"
        if not _HAS_MVT:
            return False, "mapbox_vector_tile not importable (pip install mapbox-vector-tile)"
        return True, ""

    async def fetch(self, bbox: BBox, settings: Settings, cache: Cache) -> ProviderResult:
        if not settings.mapillary_token:
            return ProviderResult(
                source=Source.MAPILLARY, stats={"skipped": "no MAPILLARY_TOKEN in env"}
            )
        z = settings.zoom_mapillary
        tiles = list(tiles_in_bbox(bbox.west, bbox.south, bbox.east, bbox.north, z))
        sem = asyncio.Semaphore(settings.concurrency)
        stats = {
            "tiles_total": len(tiles),
            "tiles_cached": 0,
            "tiles_fetched": 0,
            "tiles_empty": 0,
            "tiles_failed": 0,
            "pieces": 0,
        }
        all_pieces: list[dict] = []

        timeout = aiohttp.ClientTimeout(total=settings.timeout)
        connector = aiohttp.TCPConnector(limit=max(4, settings.concurrency * 2))
        params = {"access_token": settings.mapillary_token}
        async with aiohttp.ClientSession(
            timeout=timeout,
            connector=connector,
            headers={"User-Agent": settings.user_agent},
        ) as session:

            async def do_tile(tx: int, ty: int):
                key = f"mapillary:z{z}:{tx}:{ty}"
                if key in cache:
                    stats["tiles_cached"] += 1
                    return cache.get(key)
                url = TILE_URL.format(z=z, x=tx, y=ty)
                async with sem:
                    for attempt in range(settings.max_retries):
                        try:
                            async with session.get(url, params=params) as resp:
                                if resp.status == 404:
                                    cache.set(key, [])
                                    stats["tiles_empty"] += 1
                                    return []
                                resp.raise_for_status()
                                data = await resp.read()
                            pieces = decode_sequence_tile(data, tx, ty, z)
                            cache.set(key, pieces)
                            stats["tiles_fetched"] += 1
                            if not pieces:
                                stats["tiles_empty"] += 1
                            return pieces
                        except Exception:
                            if attempt < settings.max_retries - 1:
                                await asyncio.sleep(_backoff(settings, attempt))
                    stats["tiles_failed"] += 1
                    return []

            results = await asyncio.gather(*(do_tile(tx, ty) for tx, ty in tiles))

        for pieces in results:
            all_pieces.extend(pieces)
        stats["pieces"] = len(all_pieces)
        segs = group_and_merge(all_pieces, settings.min_run)
        if not settings.include_third_party:
            pass  # is_pano is orthogonal to third-party; nothing to drop here
        stats["segments"] = len(segs)
        return ProviderResult(source=Source.MAPILLARY, segments=segs, stats=stats)
