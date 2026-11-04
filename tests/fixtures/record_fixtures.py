"""Manual fixture recorder — NOT run by the test suite.

Re-records the live-source fixtures documented in PROVENANCE.md:

    python tests/fixtures/record_fixtures.py

Only the fixtures whose upstream is reachable without credentials are fetched
(Google coverage tiles are keyless; KartaView's public API answers with its
restriction envelope). Mapillary tiles need a private access token and are
constructed instead (see PROVENANCE.md).
"""

from __future__ import annotations

import json
import pathlib
import urllib.request

from streetlevel import streetview as sv
from streetlevel.streetview import api as svapi
from streetlevel.streetview.parse import parse_panorama_id_response

HERE = pathlib.Path(__file__).parent
UA = {"User-Agent": "tracelines/0.1 (research; contact owner)"}


def _fetch(url: str) -> bytes:
    req = urllib.request.Request(url, headers=UA)
    with urllib.request.urlopen(req, timeout=60) as r:
        return r.read()


def record_google() -> None:
    tx, ty = sv.wgs84_to_tile_coord(44.435072, 26.050430, 17)
    raw = _fetch(svapi.build_coverage_tile_request_url(tx, ty))
    panos = sv.parse_coverage_tile_response(json.loads(raw.decode("utf-8")[4:]))
    recs = [
        {
            "id": p.id,
            "lat": p.lat,
            "lon": p.lon,
            "is_third_party": bool(p.is_third_party),
            "links": [lk.pano.id for lk in (p.links or []) if lk.pano],
        }
        for p in panos[:60]
    ]
    out = HERE / "google" / f"coverage_tile_z17_{tx}_{ty}.json"
    with open(out, "w", encoding="utf-8") as f:
        json.dump({"tile": [tx, ty, 17], "panos": recs}, f, indent=1)
    print(f"google tile -> {out} ({len(recs)} panos)")

    pid = recs[0]["id"]
    raw2 = _fetch(svapi.build_find_panorama_by_id_request_url(pid, False, "en"))
    q = parse_panorama_id_response(json.loads(raw2.decode("utf-8")[4:]))
    byid = {
        "id": q.id,
        "lat": q.lat,
        "lon": q.lon,
        "source": getattr(q, "source", None),
        "date": str(getattr(q, "date", None)),
        "links": [lk.pano.id for lk in (q.links or []) if lk.pano],
        "historical": [
            {
                "id": h.id,
                "date": str(getattr(h, "date", None)),
                "lat": h.lat,
                "lon": h.lon,
                "source": getattr(h, "source", None),
            }
            for h in (getattr(q, "historical", None) or [])
        ],
    }
    out2 = HERE / "google" / "pano_by_id_launch_2024-07.json"
    with open(out2, "w", encoding="utf-8") as f:
        json.dump(byid, f, indent=1)
    print(f"google by-id -> {out2} (source={byid['source']}, date={byid['date']})")


def record_kartaview() -> None:
    url = (
        "https://api.kartaview.org/2.0/sequence/"
        "?bbTopLeft=44.55,25.95&bbBottomRight=44.30,26.25&itemsPerPage=1000"
    )
    body = _fetch(url)
    out = HERE / "kartaview" / "sequence_2.0_live_restricted_200.json"
    out.write_bytes(body)
    print(f"kartaview live envelope -> {out} ({len(body)} bytes)")


if __name__ == "__main__":
    record_google()
    record_kartaview()
