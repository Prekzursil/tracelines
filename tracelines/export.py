"""Export coverage segments to GeoJSON + summary stats. Pure stdlib json.

geopandas is NOT required (GeoJSON is just JSON). If geopandas + a driver are
present, write_gpkg() offers a GeoPackage export as a bonus.
"""

from __future__ import annotations

import json
from collections import Counter
from collections.abc import Iterable

from .models import CoverageSegment, Source


def to_feature_collection(segments: Iterable[CoverageSegment]) -> dict:
    feats = [s.to_geojson_feature() for s in segments if s.n_points >= 2]
    return {"type": "FeatureCollection", "features": feats}


def write_geojson(segments: Iterable[CoverageSegment], path: str) -> dict:
    fc = to_feature_collection(segments)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(fc, f, ensure_ascii=False)
    return fc


def summary_stats(segments: Iterable[CoverageSegment]) -> dict:
    segments = list(segments)
    by_src = Counter()
    km_by_src: dict[str, float] = {}
    years: list[str] = []
    for s in segments:
        src = s.source.value if isinstance(s.source, Source) else str(s.source)
        by_src[src] += 1
        km_by_src[src] = km_by_src.get(src, 0.0) + s.length_m / 1000.0
        if s.capture_date:
            years.append(str(s.capture_date)[:4])
    total_km = sum(km_by_src.values())
    median_year = None
    if years:
        ys = sorted(years)
        median_year = ys[len(ys) // 2]
    return {
        "segments": len(segments),
        "total_km": round(total_km, 3),
        "median_capture_year": median_year,
        "by_source": {
            k: {"segments": by_src[k], "km": round(km_by_src[k], 3)} for k in sorted(by_src)
        },
    }


def write_gpkg(segments: Iterable[CoverageSegment], path: str, layer: str = "coverage") -> bool:
    """Optional GeoPackage export (needs geopandas). Returns True if written."""
    try:
        import geopandas as gpd  # type: ignore
        from shapely.geometry import LineString  # type: ignore
    except Exception:
        return False
    rows, geoms = [], []
    for s in segments:
        if s.n_points < 2:
            continue
        feat = s.to_geojson_feature()
        rows.append(feat["properties"])
        geoms.append(LineString(s.coords))
    if not geoms:
        return False
    gdf = gpd.GeoDataFrame(rows, geometry=geoms, crs="EPSG:4326")
    gdf.to_file(path, layer=layer, driver="GPKG")
    return True
