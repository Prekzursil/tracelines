"""Provider-agnostic data model for coverage nodes and continuous polylines."""

from __future__ import annotations

import base64
import math
from dataclasses import dataclass, field
from enum import Enum
from typing import Any

# Mean Earth radius (WGS84 mean), meters. Good to ~0.3% for lengths.
EARTH_R = 6371008.8

# Official Google pano ids are 22 URL-safe-base64 chars encoding exactly 16 bytes;
# only 2 bits of the final char are meaningful => it is always one of {A,Q,g,w}.
_OFFICIAL_TERMINAL = frozenset("AQgw")
_THIRD_PARTY_PREFIXES = ("CIHM", "CIAB", "AF1Q")


def is_official_panoid(pid: str) -> bool:
    """Positive whitelist for official Google pano ids (Layer-1 HARD-RULE guard).

    Stricter and safer than streetlevel's prefix denylist: it *positively*
    confirms the 22-char / 16-byte / terminal-{A,Q,g,w} invariant, which rejects
    the documented false-negative classes (legacy 22-char photospheres, the new
    CIAB/AF1Q UGC schemes) that a `CIHM0og`/`len>22` denylist would let through.
    Verified 2026-07-13 against 628 live official Bucharest ids (100% accept) and
    live CIHM photosphere ids (100% reject).
    """
    if not isinstance(pid, str) or len(pid) != 22:
        return False
    if pid[-1] not in _OFFICIAL_TERMINAL:
        return False
    if pid.startswith(_THIRD_PARTY_PREFIXES):
        return False
    try:
        raw = base64.urlsafe_b64decode(pid + "==")
    except Exception:
        return False
    return len(raw) == 16


class Source(str, Enum):
    GOOGLE = "google"
    MAPILLARY = "mapillary"
    KARTAVIEW = "kartaview"


def haversine_m(lon1: float, lat1: float, lon2: float, lat2: float) -> float:
    """Great-circle distance in meters between two lon/lat points."""
    p1, p2 = math.radians(lat1), math.radians(lat2)
    dphi = math.radians(lat2 - lat1)
    dlmb = math.radians(lon2 - lon1)
    a = math.sin(dphi / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dlmb / 2) ** 2
    return 2 * EARTH_R * math.asin(min(1.0, math.sqrt(a)))


def line_length_m(coords: list[tuple[float, float]]) -> float:
    """Length in meters of a [(lon,lat), ...] polyline."""
    if len(coords) < 2:
        return 0.0
    return sum(
        haversine_m(coords[i][0], coords[i][1], coords[i + 1][0], coords[i + 1][1])
        for i in range(len(coords) - 1)
    )


@dataclass
class Pano:
    """A single coverage node (one panorama / image point), provider-agnostic.

    Google/KartaView emit these and rely on graph stitching; Mapillary emits
    native segments directly (see CoverageSegment).
    """

    id: str
    lon: float
    lat: float
    source: Source
    heading: float | None = None
    is_third_party: bool = False  # True => user photosphere ("circle")
    sv_source: str | None = None  # google: 'launch'(car)/'scout'(trekker)/'innerspace'...
    date: str | None = None  # 'YYYY-MM' or ISO
    neighbors: list[str] = field(default_factory=list)  # adjacent pano ids => graph edges
    is_pano: bool | None = None  # mapillary: 360 flag
    raw: Any = None

    @property
    def degree(self) -> int:
        return len(self.neighbors)


@dataclass
class CoverageSegment:
    """A continuous coverage polyline — one of the "blue lines"."""

    coords: list[tuple[float, float]]  # [(lon,lat), ...] in EPSG:4326
    source: Source
    id: str | None = None
    pano_ids: list[str] = field(default_factory=list)
    capture_date: str | None = None
    is_pano: bool | None = None
    meta: dict = field(default_factory=dict)

    @property
    def length_m(self) -> float:
        return line_length_m(self.coords)

    @property
    def n_points(self) -> int:
        return len(self.coords)

    def to_geojson_feature(self) -> dict:
        src = self.source.value if isinstance(self.source, Source) else self.source
        props: dict[str, Any] = {
            "source": src,
            "length_m": round(self.length_m, 2),
            "n_points": self.n_points,
        }
        if self.id:
            props["id"] = self.id
        if self.capture_date:
            props["capture_date"] = self.capture_date
        if self.is_pano is not None:
            props["is_pano"] = self.is_pano
        if self.pano_ids:
            props["pano_ids"] = self.pano_ids
        props.update(self.meta)
        return {
            "type": "Feature",
            "geometry": {
                "type": "LineString",
                "coordinates": [[round(x, 7), round(y, 7)] for x, y in self.coords],
            },
            "properties": props,
        }
