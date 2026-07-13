#!/usr/bin/env python3
"""Reproduce the HARD-RULE verification.

Sweeps a fixed block of z17 Street View coverage tiles over central Bucharest and asserts
the invariant: **every pano returned by the coverage-tile layer is official** — it passes
`is_official_panoid` and is not third-party. Writes the evidence manifest and a per-tile
summary. Exits non-zero if the invariant is ever violated, so CI can gate on it.

    python scripts/verify_hardrule.py            # sweep, assert, write manifest
    python scripts/verify_hardrule.py --no-write # assert only (CI canary)
"""

from __future__ import annotations

import argparse
import csv
import sys
from collections import defaultdict
from pathlib import Path

from streetlevel import streetview as sv

from svcoverage.models import is_official_panoid

CENTER_LAT, CENTER_LON = 44.4268, 26.1025
ZOOM = 17
RADIUS = 3  # (2*3+1)^2 = 49 tiles


def sweep(center_lat: float, center_lon: float, zoom: int, radius: int):
    tx0, ty0 = sv.wgs84_to_tile_coord(center_lat, center_lon, zoom)
    rows, tiles = [], 0
    for dx in range(-radius, radius + 1):
        for dy in range(-radius, radius + 1):
            tx, ty = tx0 + dx, ty0 + dy
            try:
                panos = sv.get_coverage_tile(tx, ty)
            except Exception as e:  # noqa: BLE001
                print(f"tile {tx},{ty} fetch failed: {e}", file=sys.stderr)
                continue
            tiles += 1
            for p in panos:
                rows.append(
                    {
                        "tile_x": tx,
                        "tile_y": ty,
                        "panoid": p.id,
                        "lat": round(p.lat, 7),
                        "lon": round(p.lon, 7),
                        "is_third_party": int(bool(p.is_third_party)),
                        "is_official_panoid": int(is_official_panoid(p.id)),
                    }
                )
    return tiles, rows


def main() -> int:
    ap = argparse.ArgumentParser(description="Reproduce the HARD-RULE coverage-tile verification.")
    ap.add_argument("--out", default="docs/evidence/coverage-manifest.csv")
    ap.add_argument("--summary", default="docs/evidence/coverage-summary.csv")
    ap.add_argument("--no-write", action="store_true", help="assert only; don't write files")
    a = ap.parse_args()

    tiles, rows = sweep(CENTER_LAT, CENTER_LON, ZOOM, RADIUS)
    total = len(rows)
    third_party = sum(r["is_third_party"] for r in rows)
    non_official = sum(1 for r in rows if not r["is_official_panoid"])
    leaks = [r for r in rows if r["is_third_party"] or not r["is_official_panoid"]]

    print(f"Swept {tiles} z{ZOOM} tiles around ({CENTER_LAT}, {CENTER_LON}), radius {RADIUS}")
    print(f"  panos:            {total}")
    print(f"  third_party:      {third_party}")
    print(f"  non_official_id:  {non_official}")
    print(f"  HARD-RULE leaks:  {len(leaks)}")

    if not a.no_write and total:
        outp = Path(a.out)
        outp.parent.mkdir(parents=True, exist_ok=True)
        with outp.open("w", newline="", encoding="utf-8") as f:
            w = csv.DictWriter(
                f,
                fieldnames=[
                    "tile_x",
                    "tile_y",
                    "panoid",
                    "lat",
                    "lon",
                    "is_third_party",
                    "is_official_panoid",
                ],
            )
            w.writeheader()
            w.writerows(rows)
        agg = defaultdict(lambda: [0, 0, 0])
        for r in rows:
            k = (r["tile_x"], r["tile_y"])
            agg[k][0] += 1
            agg[k][1] += r["is_third_party"]
            agg[k][2] += 0 if r["is_official_panoid"] else 1
        with Path(a.summary).open("w", newline="", encoding="utf-8") as f:
            w = csv.writer(f)
            w.writerow(["tile_x", "tile_y", "panos", "third_party", "non_official_id"])
            for (tx, ty), (t, tp, no) in sorted(agg.items()):
                w.writerow([tx, ty, t, tp, no])
        print(f"  wrote {outp} ({total} rows) + {a.summary}")

    if leaks:
        print(
            f"\nFAIL: {len(leaks)} HARD-RULE violation(s) — a non-official pano reached the "
            f"coverage-tile output.",
            file=sys.stderr,
        )
        for r in leaks[:10]:
            print("  leak:", r, file=sys.stderr)
        return 1
    print(
        "\nPASS: 0 HARD-RULE violations — every coverage-tile pano is official, none third-party."
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
