"""Self-hostable proxy backend for svcoverage.

Exposes extraction over HTTP so the static GitHub Pages GUI can request LIVE coverage —
including Google, which cannot run in a browser. **You** host this; it is opt-in and carries
the same ToS responsibility as running the CLI (see the repo DATA_LICENSES / disclaimer).

    pip install "svcoverage[server]"
    uvicorn server.app:app --host 0.0.0.0 --port 8000
    # then set the GUI's "proxy URL" to http://your-host:8000

Env:
  SVCOVERAGE_CORS_ORIGINS   comma-separated allowed origins (default "*")
  SVCOVERAGE_MAX_BBOX_DEG2  bbox area cap in deg^2 (default 0.02 ~ a city district)
  MAPILLARY_TOKEN           enables the Mapillary source server-side
"""

from __future__ import annotations

import os

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

from svcoverage.config import AREAS, BBox, Settings
from svcoverage.export import summary_stats, to_feature_collection
from svcoverage.nearest import find_nearest_coverage
from svcoverage.pipeline import extract_async
from svcoverage.probe import density_probe_async

app = FastAPI(
    title="svcoverage proxy",
    version="0.1.0",
    description="Live street-level coverage extraction behind the svcoverage GUI.",
)

_origins = [
    o.strip() for o in os.environ.get("SVCOVERAGE_CORS_ORIGINS", "*").split(",") if o.strip()
]
app.add_middleware(
    CORSMiddleware,
    allow_origins=_origins or ["*"],
    allow_methods=["GET", "POST"],
    allow_headers=["*"],
)

MAX_BBOX_DEG2 = float(os.environ.get("SVCOVERAGE_MAX_BBOX_DEG2", "0.02"))


def _area_deg2(b: BBox) -> float:
    return abs((b.east - b.west) * (b.north - b.south))


def _parse_bbox(s: str) -> BBox:
    try:
        parts = [float(x) for x in s.split(",")]
    except ValueError:
        raise HTTPException(400, "bbox must be four numbers: west,south,east,north") from None
    if len(parts) != 4:
        raise HTTPException(400, "bbox must be west,south,east,north")
    b = BBox(*parts)
    if _area_deg2(b) > MAX_BBOX_DEG2:
        raise HTTPException(
            413,
            f"bbox area {_area_deg2(b):.4f} deg^2 exceeds the proxy cap {MAX_BBOX_DEG2}; "
            "extract large areas locally with the CLI.",
        )
    return b


@app.get("/health")
def health() -> dict:
    return {
        "status": "ok",
        "service": "svcoverage-proxy",
        "version": "0.1.0",
        "max_bbox_deg2": MAX_BBOX_DEG2,
        "mapillary": bool(os.environ.get("MAPILLARY_TOKEN")),
    }


@app.get("/nearest")
def nearest(lat: float, lon: float, include_trekker: bool = False) -> dict:
    res = find_nearest_coverage(lat, lon, verify_source=True, include_trekker=include_trekker)
    if res is None:
        return {"result": None, "reason": "no official coverage found"}
    p = res.pano
    return {
        "id": p.id,
        "lat": p.lat,
        "lon": p.lon,
        "is_third_party": p.is_third_party,
        "sv_source": p.sv_source,
        "date": p.date,
        "degree": p.degree,
        "distance_m": round(res.distance_m, 1),
    }


class ExtractReq(BaseModel):
    bbox: str | None = None
    area: str | None = None
    sources: list[str] = ["google"]
    precision: bool = False
    min_run: int = 2
    include_trekker: bool = False


@app.post("/extract")
async def extract_ep(req: ExtractReq) -> dict:
    if req.area and req.area.lower() in AREAS:
        b = AREAS[req.area.lower()]
        if _area_deg2(b) > MAX_BBOX_DEG2:
            raise HTTPException(413, "named area is too large for the proxy; use the CLI.")
    elif req.bbox:
        b = _parse_bbox(req.bbox)
    else:
        raise HTTPException(400, "pass 'bbox' or 'area'")
    s = Settings(
        precision=req.precision,
        min_run=req.min_run,
        include_trekker=req.include_trekker,
        cache_enabled=True,
    )
    segs, meta = await extract_async(b, req.sources, s)
    fc = to_feature_collection(segs)
    fc["properties"] = {"stats": summary_stats(segs), "counts": meta["counts"]}
    return fc


@app.get("/probe")
async def probe_ep(bbox: str, sources: str = "google") -> dict:
    b = _parse_bbox(bbox)
    s = Settings(cache_enabled=True)
    return await density_probe_async(b, [x.strip() for x in sources.split(",") if x.strip()], s)
