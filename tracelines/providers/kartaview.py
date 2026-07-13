"""KartaView (formerly OpenStreetCam) coverage via the bbox sequence API.

HONEST STATUS: KartaView's public API host/schema has drifted across the
OpenStreetCam -> KartaView transition, and its uptime is less reliable than
Mapillary/Google. This provider therefore:
  * tries a small set of known host/endpoint shapes,
  * parses defensively (a tolerant parser that finds geometry under several key
    names),
  * degrades gracefully — on any failure it returns an empty result with an
    honest stats note, so the fusion pipeline still runs on Google + Mapillary.

The parser (`parse_sequences`) is a pure function and is unit-tested with
synthetic JSON so the shape-handling is verified even without a live endpoint.
"""

from __future__ import annotations

import asyncio
import random
from typing import TYPE_CHECKING

from ..models import CoverageSegment, Source
from .base import Provider, ProviderResult

if TYPE_CHECKING:
    from ..cache import Cache
    from ..config import BBox, Settings

try:
    import aiohttp

    _HAS_AIOHTTP = True
except Exception:  # pragma: no cover
    _HAS_AIOHTTP = False

# Known host candidates (first that answers wins).
HOSTS = ("https://api.openstreetcam.org", "https://api.kartaview.org")


def _backoff(settings: Settings, attempt: int) -> float:
    b = settings.retry_base * (2**attempt)
    j = settings.request_jitter
    return max(0.0, b * (1.0 + random.uniform(-j, j)))


def _coerce_coords(val) -> list[tuple[float, float]]:
    """Accept a variety of geometry encodings -> [(lon,lat), ...].

    Handles: GeoJSON LineString coordinates [[lon,lat],...]; lists of
    {"lat":..,"lng"/"lon":..} points; and "lat,lng;lat,lng" track strings.
    """
    coords: list[tuple[float, float]] = []
    if isinstance(val, str):
        for pair in val.replace("|", ";").split(";"):
            pair = pair.strip()
            if not pair:
                continue
            parts = pair.split(",")
            if len(parts) >= 2:
                try:
                    lat, lon = float(parts[0]), float(parts[1])
                    coords.append((lon, lat))
                except ValueError:
                    continue
        return coords
    if isinstance(val, list):
        for pt in val:
            if isinstance(pt, (list, tuple)) and len(pt) >= 2:
                # GeoJSON order is [lon, lat]
                coords.append((float(pt[0]), float(pt[1])))
            elif isinstance(pt, dict):
                plat = pt.get("lat") or pt.get("latitude")
                plon = pt.get("lon") or pt.get("lng") or pt.get("longitude")
                if plat is not None and plon is not None:
                    coords.append((float(plon), float(plat)))
    return coords


def _find_geometry(seq: dict) -> list[tuple[float, float]]:
    # GeoJSON-style
    geom = seq.get("geometry")
    if isinstance(geom, dict) and "coordinates" in geom:
        return _coerce_coords(geom["coordinates"])
    # common flat keys
    for key in ("track", "coordinates", "path", "points", "photos"):
        if key in seq and seq[key]:
            c = _coerce_coords(seq[key])
            if c:
                return c
    return []


def parse_sequences(payload, min_run: int = 2) -> list[CoverageSegment]:
    """Pure: KartaView JSON -> CoverageSegments. Tolerant to several shapes."""
    # locate the list of sequences under common envelope keys
    seqs = None
    if isinstance(payload, list):
        seqs = payload
    elif isinstance(payload, dict):
        for key in ("result", "results", "sequences", "data", "currentPageItems", "items"):
            v = payload.get(key)
            if isinstance(v, dict):
                v = v.get("data") or v.get("sequences") or v.get("items") or v
            if isinstance(v, list):
                seqs = v
                break
    if not seqs:
        return []
    floor = max(2, min_run)
    out: list[CoverageSegment] = []
    for i, seq in enumerate(seqs):
        if not isinstance(seq, dict):
            continue
        coords = _find_geometry(seq)
        if len(coords) < floor:
            continue
        sid = seq.get("id") or seq.get("sequenceId") or seq.get("sequence_id")
        date = seq.get("date_added") or seq.get("dateAdded") or seq.get("date")
        out.append(
            CoverageSegment(
                coords=coords,
                source=Source.KARTAVIEW,
                id=str(sid) if sid is not None else f"kartaview-seg-{i}",
                capture_date=str(date)[:7] if date else None,
                meta={"sequence_id": str(sid)} if sid is not None else {},
            )
        )
    return out


class KartaViewProvider(Provider):
    source = Source.KARTAVIEW

    def available(self) -> tuple[bool, str]:
        if not _HAS_AIOHTTP:
            return False, "aiohttp not importable"
        return True, ""

    async def fetch(self, bbox: BBox, settings: Settings, cache: Cache) -> ProviderResult:
        key = f"kartaview:{bbox.west:.4f},{bbox.south:.4f},{bbox.east:.4f},{bbox.north:.4f}"
        if key in cache:
            payload = cache.get(key)
            segs = parse_sequences(payload, settings.min_run)
            return ProviderResult(
                source=Source.KARTAVIEW,
                segments=segs,
                stats={"cached": True, "segments": len(segs)},
            )

        stats = {"segments": 0, "host_used": None, "note": ""}
        timeout = aiohttp.ClientTimeout(total=settings.timeout)
        # KartaView 2.0 bbox sequence listing. Param names per the documented API;
        # tolerant parser handles response drift.
        payload = None
        async with aiohttp.ClientSession(
            timeout=timeout, headers={"User-Agent": settings.user_agent}
        ) as session:
            for host in HOSTS:
                url = f"{host}/2.0/sequence/"
                params = {
                    "bbTopLeft": f"{bbox.north},{bbox.west}",
                    "bbBottomRight": f"{bbox.south},{bbox.east}",
                    "itemsPerPage": "1000",
                }
                for attempt in range(settings.max_retries):
                    try:
                        async with session.get(url, params=params) as resp:
                            if resp.status >= 500:
                                raise RuntimeError(f"HTTP {resp.status}")
                            if resp.status != 200:
                                break  # try next host
                            payload = await resp.json(content_type=None)
                        stats["host_used"] = host
                        break
                    except Exception as e:
                        stats["note"] = f"{type(e).__name__}: {e}"
                        if attempt < settings.max_retries - 1:
                            await asyncio.sleep(_backoff(settings, attempt))
                if payload is not None:
                    break

        if payload is None:
            stats["note"] = (
                stats["note"] or "no KartaView host responded; skipped (pipeline continues)"
            )
            return ProviderResult(source=Source.KARTAVIEW, stats=stats)

        cache.set(key, payload)
        segs = parse_sequences(payload, settings.min_run)
        stats["segments"] = len(segs)
        return ProviderResult(source=Source.KARTAVIEW, segments=segs, stats=stats)
