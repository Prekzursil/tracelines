"""Orchestrate providers -> stitch point sources -> fuse -> segments.

Runs providers concurrently. Point sources (Google) return panos and are stitched
into polylines here; native-line sources (Mapillary/KartaView) pass through. A
shared Cache makes the whole run resumable.
"""

from __future__ import annotations

import asyncio

from .cache import Cache
from .fuse import fuse
from .providers import get_provider
from .stitch import stitch_panos


async def _run_provider(name, bbox, settings, cache):
    prov = get_provider(name)
    ok, why = prov.available()
    if not ok:
        return name, [], {"unavailable": why}
    try:
        res = await prov.fetch(bbox, settings, cache)
    except Exception as e:  # a single source failing must not kill the run
        return name, [], {"error": f"{type(e).__name__}: {e}"}
    segs = list(res.segments)
    if res.panos:
        segs.extend(stitch_panos(res.panos, prov.source, settings.min_run))
    return name, segs, res.stats


async def extract_async(bbox, source_names, settings, cache: Cache | None = None):
    own = cache is None
    if own:
        cache = Cache(settings.cache_dir, settings.cache_enabled)
    try:
        results = await asyncio.gather(
            *[_run_provider(n, bbox, settings, cache) for n in source_names]
        )
        by_source = {n: segs for (n, segs, _st) in results}
        stats = {n: st for (n, _s, st) in results}
        fused = fuse(by_source, settings)
        meta = {
            "counts": {n: len(s) for n, s in by_source.items()},
            "fused": len(fused),
            "by_source_stats": stats,
        }
        return fused, meta
    finally:
        if own and cache is not None:
            cache.close()


def extract(bbox, source_names, settings):
    return asyncio.run(extract_async(bbox, source_names, settings))
