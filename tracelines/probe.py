"""Density probe: run each source over a (small) bbox and report covered km,
segment count, and median capture year — the research's mandatory verification,
baked into the tool so the FIT/coverage question is answered empirically.
"""

from __future__ import annotations

import asyncio

from .cache import Cache
from .export import summary_stats
from .providers import get_provider
from .stitch import stitch_panos


async def density_probe_async(bbox, source_names, settings, cache: Cache | None = None):
    own = cache is None
    if own:
        cache = Cache(settings.cache_dir, settings.cache_enabled)
    out: dict[str, dict] = {}
    try:
        for name in source_names:
            prov = get_provider(name)
            ok, why = prov.available()
            if not ok:
                out[name] = {"available": False, "reason": why}
                continue
            try:
                res = await prov.fetch(bbox, settings, cache)
            except Exception as e:
                out[name] = {"available": True, "error": f"{type(e).__name__}: {e}"}
                continue
            segs = list(res.segments)
            if res.panos:
                segs.extend(stitch_panos(res.panos, prov.source, settings.min_run))
            st = summary_stats(segs)
            st["available"] = True
            st["provider_stats"] = res.stats
            out[name] = st
    finally:
        if own and cache is not None:
            cache.close()
    return out


def density_probe(bbox, source_names, settings):
    return asyncio.run(density_probe_async(bbox, source_names, settings))
