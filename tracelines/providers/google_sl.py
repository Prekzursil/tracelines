"""Google Street View coverage via streetlevel (internal photometa + z17 tiles).

Cheap tier  : get_coverage_tile_async over z17 tiles -> nodes with id/lat/lon/
              is_third_party/links (intra-tile adjacency). No API key needed.
Precision   : find_panorama_by_id_async per kept node -> sv_source ('launch'=car,
 (opt-in)     'scout'=trekker...), capture date, and cross-tile links.

Keep predicate: (not is_third_party) AND degree>=1 [AND, with --precision,
sv_source in the car/trekker set]. Isolated nodes and photospheres = the "circles".
"""

from __future__ import annotations

import asyncio
import random
from typing import TYPE_CHECKING

from ..models import Pano, Source, is_official_panoid
from ..tiles import tiles_in_bbox
from .base import Provider, ProviderResult

if TYPE_CHECKING:
    from ..cache import Cache
    from ..config import BBox, Settings

try:
    import aiohttp
    from streetlevel import streetview as _sv

    _AVAILABLE = True
    _IMPORT_ERR = ""
except Exception as e:  # pragma: no cover - environment dependent
    _AVAILABLE = False
    _IMPORT_ERR = f"{type(e).__name__}: {e}"

KEEP_SOURCES_CAR = {"launch"}
KEEP_SOURCES_TREKKER = {"launch", "scout"}


def _backoff(settings: Settings, attempt: int) -> float:
    b = settings.retry_base * (2**attempt)
    j = settings.request_jitter
    return max(0.0, b * (1.0 + random.uniform(-j, j)))


def _fmt_date(d) -> str | None:
    if d is None:
        return None
    if isinstance(d, str):
        return d
    y = getattr(d, "year", None)
    m = getattr(d, "month", None)
    if y and m:
        return f"{int(y):04d}-{int(m):02d}"
    if y:
        return f"{int(y):04d}"
    return str(d)


class GoogleStreetlevelProvider(Provider):
    source = Source.GOOGLE

    def available(self) -> tuple[bool, str]:
        if not _AVAILABLE:
            return False, f"streetlevel/aiohttp not importable ({_IMPORT_ERR})"
        return True, ""

    async def fetch(self, bbox: BBox, settings: Settings, cache: Cache) -> ProviderResult:
        z = settings.zoom_google
        tiles = list(tiles_in_bbox(bbox.west, bbox.south, bbox.east, bbox.north, z))
        sem = asyncio.Semaphore(settings.concurrency)
        stats = {
            "tiles_total": len(tiles),
            "tiles_cached": 0,
            "tiles_fetched": 0,
            "tiles_failed": 0,
            "panos_raw": 0,
            "third_party": 0,
            "non_official_id": 0,
        }

        timeout = aiohttp.ClientTimeout(total=settings.timeout)
        connector = aiohttp.TCPConnector(limit=max(4, settings.concurrency * 2))
        async with aiohttp.ClientSession(
            timeout=timeout,
            connector=connector,
            headers={"User-Agent": settings.user_agent},
        ) as session:

            async def do_tile(tx: int, ty: int):
                key = f"google:z{z}:{tx}:{ty}"
                if key in cache:
                    stats["tiles_cached"] += 1
                    return cache.get(key)
                async with sem:
                    for attempt in range(settings.max_retries):
                        try:
                            raw = await _sv.get_coverage_tile_async(tx, ty, session)
                            recs = [
                                {
                                    "id": p.id,
                                    "lat": p.lat,
                                    "lon": p.lon,
                                    "tp": bool(p.is_third_party),
                                    "nb": [lk.pano.id for lk in (p.links or []) if lk.pano],
                                }
                                for p in raw
                            ]
                            cache.set(key, recs)
                            stats["tiles_fetched"] += 1
                            return recs
                        except Exception:
                            if attempt < settings.max_retries - 1:
                                await asyncio.sleep(_backoff(settings, attempt))
                    stats["tiles_failed"] += 1
                    return []

            tile_results = await asyncio.gather(*(do_tile(tx, ty) for tx, ty in tiles))

            panos: dict[str, Pano] = {}
            for recs in tile_results:
                for r in recs:
                    stats["panos_raw"] += 1
                    if not settings.include_third_party:
                        # HARD RULE Layer 1: positive official-id whitelist (never a photosphere/photopet)
                        if not is_official_panoid(r["id"]):
                            stats["non_official_id"] += 1
                            continue
                        if r["tp"]:
                            stats["third_party"] += 1
                            continue
                    p = panos.get(r["id"])
                    if p is None:
                        p = Pano(
                            id=r["id"],
                            lon=r["lon"],
                            lat=r["lat"],
                            source=Source.GOOGLE,
                            is_third_party=r["tp"],
                        )
                        panos[r["id"]] = p
                    for nb in r["nb"]:
                        if nb not in p.neighbors:
                            p.neighbors.append(nb)

            if settings.precision and panos:
                await self._precision(session, list(panos.values()), panos, settings, cache, stats)

        # prune edges to nodes we did not retain; drop self-loops
        ids = set(panos)
        for p in panos.values():
            p.neighbors = [nb for nb in p.neighbors if nb in ids and nb != p.id]

        result_panos = list(panos.values())
        stats["panos_kept"] = len(result_panos)
        stats["isolates"] = sum(1 for p in result_panos if p.degree == 0)
        return ProviderResult(source=Source.GOOGLE, panos=result_panos, stats=stats)

    async def _precision(self, session, kept, node_map, settings, cache, stats):
        sem = asyncio.Semaphore(settings.concurrency)
        keep = KEEP_SOURCES_TREKKER if settings.include_trekker else KEEP_SOURCES_CAR
        failed: set[str] = set()

        async def do(p: Pano):
            key = f"google:byid:{p.id}"
            rec = cache.get(key)
            if rec is None:
                async with sem:
                    resolved = None
                    for attempt in range(settings.max_retries):
                        try:
                            q = await _sv.find_panorama_by_id_async(p.id, session)
                            resolved = {
                                "src": getattr(q, "source", None) if q else None,
                                "date": _fmt_date(getattr(q, "date", None)) if q else None,
                                "nb": [lk.pano.id for lk in (q.links or []) if lk.pano]
                                if q
                                else [],
                            }
                            break
                        except Exception:
                            if attempt < settings.max_retries - 1:
                                await asyncio.sleep(_backoff(settings, attempt))
                    if resolved is None:
                        # FETCH_FAILED: never cache, keep the node (avoid B1 silent data loss)
                        failed.add(p.id)
                        rec = {"src": None, "date": None, "nb": []}
                    else:
                        rec = resolved
                        cache.set(key, rec)  # cache only definitively-resolved results
            p.sv_source = rec.get("src")
            p.date = rec.get("date")
            for nb in rec.get("nb", []):
                if nb not in p.neighbors:
                    p.neighbors.append(nb)

        await asyncio.gather(*(do(p) for p in kept))
        # HARD RULE Layer 2: drop only CONFIRMED non-car sources (resolved source not in keep).
        # Unknowns — fetch failed, or resolved with no source — are KEPT: they are official per
        # Layers 0+1 (never a photosphere), so dropping them would be silent data loss (B1).
        drop = [
            pid
            for pid, p in node_map.items()
            if pid not in failed and p.sv_source is not None and p.sv_source not in keep
        ]
        for pid in drop:
            del node_map[pid]
        n_none = sum(1 for p in node_map.values() if p.sv_source is None)
        stats["precision_dropped"] = len(drop)
        stats["precision_byid_failed"] = len(failed)  # kept despite failure
        stats["precision_source_none"] = n_none
        # Canary: EVERY source None => find_panorama_by_id likely broken (would otherwise decimate).
        stats["precision_source_all_none"] = bool(kept) and n_none == len(kept)
