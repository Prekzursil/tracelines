"""Command-line interface for svcoverage.

svcoverage extract --area bucharest-city --sources google,mapillary,kartaview --out out.geojson
svcoverage probe   --area bucharest-city --sources google,mapillary
svcoverage nearest 44.435072 26.050430
"""

from __future__ import annotations

import argparse
import json
import sys

from .config import AREAS, BBox, Settings


def _parse_bbox(s: str) -> BBox:
    parts = [float(x) for x in s.split(",")]
    if len(parts) != 4:
        raise argparse.ArgumentTypeError("bbox must be 'west,south,east,north'")
    return BBox(*parts)


def _settings_from_args(a) -> Settings:
    s = Settings()
    for attr in (
        "concurrency",
        "min_run",
        "precision",
        "include_trekker",
        "dedupe",
        "snap",
        "cache_dir",
    ):
        if getattr(a, attr, None) is not None:
            setattr(s, attr, getattr(a, attr))
    return s


def _resolve(a) -> BBox:
    if getattr(a, "bbox", None):
        return a.bbox
    if getattr(a, "area", None):
        key = a.area.lower()
        if key not in AREAS:
            print(f"unknown area '{a.area}'. known: {sorted(AREAS)}", file=sys.stderr)
            raise SystemExit(2)
        return AREAS[key]
    print("must pass --area or --bbox", file=sys.stderr)
    raise SystemExit(2)


def _add_common(p):
    p.add_argument("--area", help=f"named area ({', '.join(sorted(AREAS))})")
    p.add_argument("--bbox", type=_parse_bbox, help="west,south,east,north (EPSG:4326)")
    p.add_argument("--sources", default="google", help="comma list: google,mapillary,kartaview")
    p.add_argument("--concurrency", type=int)
    p.add_argument("--min-run", dest="min_run", type=int, help="min points per kept segment")
    p.add_argument(
        "--precision",
        action="store_true",
        default=None,
        help="google: per-pano source/date (launch-only); slower but pure car",
    )
    p.add_argument(
        "--include-trekker",
        dest="include_trekker",
        action="store_true",
        default=None,
        help="keep scout/trekker in addition to launch (car)",
    )
    p.add_argument("--dedupe", action="store_true", default=None, help="cross-source spatial dedup")
    p.add_argument("--snap", action="store_true", default=None, help="snap to OSM (needs osmnx)")
    p.add_argument("--cache-dir", dest="cache_dir")


def cmd_extract(a) -> int:
    from .export import summary_stats, write_geojson
    from .pipeline import extract

    bbox = _resolve(a)
    settings = _settings_from_args(a)
    sources = [x.strip() for x in a.sources.split(",") if x.strip()]
    segs, meta = extract(bbox, sources, settings)
    if a.out:
        write_geojson(segs, a.out)
    print(
        json.dumps(
            {"stats": summary_stats(segs), "meta": meta, "out": a.out}, indent=2, default=str
        )
    )
    return 0


def cmd_probe(a) -> int:
    from .probe import density_probe

    bbox = _resolve(a)
    settings = _settings_from_args(a)
    sources = [x.strip() for x in a.sources.split(",") if x.strip()]
    print(json.dumps(density_probe(bbox, sources, settings), indent=2, default=str))
    return 0


def cmd_nearest(a) -> int:
    from .nearest import find_nearest_coverage

    res = find_nearest_coverage(
        a.lat, a.lon, verify_source=True, include_trekker=bool(a.include_trekker)
    )
    if res is None:
        print(json.dumps({"result": None, "reason": "no official coverage found"}))
        return 1
    p = res.pano
    print(
        json.dumps(
            {
                "id": p.id,
                "lat": p.lat,
                "lon": p.lon,
                "is_third_party": p.is_third_party,
                "sv_source": p.sv_source,
                "date": p.date,
                "degree": p.degree,
                "distance_m": round(res.distance_m, 1),
            },
            indent=2,
            default=str,
        )
    )
    return 0


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog="svcoverage", description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    sub = p.add_subparsers(dest="cmd", required=True)

    pe = sub.add_parser("extract", help="extract coverage polylines -> GeoJSON")
    _add_common(pe)
    pe.add_argument("--out", help="output GeoJSON path")
    pe.set_defaults(func=cmd_extract)

    pp = sub.add_parser("probe", help="density probe per source over a bbox")
    _add_common(pp)
    pp.set_defaults(func=cmd_probe)

    pn = sub.add_parser("nearest", help="nearest official car coverage to a point")
    pn.add_argument("lat", type=float)
    pn.add_argument("lon", type=float)
    pn.add_argument("--include-trekker", dest="include_trekker", action="store_true", default=None)
    pn.set_defaults(func=cmd_nearest)
    return p


def main(argv=None) -> int:
    args = build_parser().parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    raise SystemExit(main())
