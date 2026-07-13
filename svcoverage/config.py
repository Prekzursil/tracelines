"""Configuration: bbox presets and runtime settings.

Secrets are read from the environment at runtime and never hardcoded:
  - MAPS_API_TOKEN         : Google Maps key (optional; official /streetview/metadata enrichment)
  - MAPILLARY_TOKEN        : Mapillary access token 'MLY|...' (required for the Mapillary provider)
"""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from typing import NamedTuple


class BBox(NamedTuple):
    west: float
    south: float
    east: float
    north: float

    def __str__(self) -> str:  # pragma: no cover - trivial
        return f"{self.west},{self.south},{self.east},{self.north}"


# Approximate administrative envelopes (EPSG:4326), from OSM relation bounds.
BUCHAREST_CITY = BBox(25.9670, 44.3340, 26.2250, 44.5410)  # Municipiul Bucuresti
BUCHAREST_METRO = BBox(25.7900, 44.2300, 26.4700, 44.7200)  # + Ilfov county envelope

AREAS: dict[str, BBox] = {
    "bucharest": BUCHAREST_CITY,
    "bucharest-city": BUCHAREST_CITY,
    "bucharest-metro": BUCHAREST_METRO,
    "ilfov": BUCHAREST_METRO,
}


def _env(*names: str) -> str | None:
    for n in names:
        v = os.environ.get(n)
        if v:
            return v
    return None


@dataclass
class Settings:
    # concurrency / networking
    concurrency: int = 16
    timeout: float = 30.0
    max_retries: int = 4
    retry_base: float = 0.5  # exponential backoff base seconds
    request_jitter: float = 0.15  # +/- jitter fraction on backoff

    # tiling
    zoom_google: int = 17  # streetlevel coverage tiles
    zoom_mapillary: int = 14  # mapillary sequence layer max zoom

    # filtering ("circle" exclusion)
    min_run: int = 2  # min points/panos for a kept segment
    # DEBUG/RESEARCH ONLY. Setting this True disables BOTH Layer-1 guards and lets
    # Google-hosted photospheres/photo-paths into the output — it VIOLATES the blue-line
    # HARD RULE. Not exposed on the CLI. Never enable for the coverage deliverable.
    include_third_party: bool = False
    include_trekker: bool = False  # google: keep source in {launch, scout} vs launch-only
    precision: bool = (
        False  # google: find_panorama_by_id per pano (adds source/date, cross-tile links)
    )

    # fusion
    snap: bool = False  # snap onto OSM network (needs osmnx)
    dedupe: bool = False  # cross-source spatial dedup (default: union w/ provenance)
    dedupe_buffer_m: float = 12.0  # dedup buffer radius, meters
    dedupe_min_overlap: float = 0.6  # drop lower-priority seg if >= this fraction lies in buffer
    source_priority: tuple = ("google", "mapillary", "kartaview")

    # storage
    cache_dir: str = ".svcache"
    cache_enabled: bool = True

    # identity / secrets (from env; never hardcode)
    user_agent: str = "svcoverage/0.1 (research; contact owner)"
    mapillary_token: str | None = field(
        default_factory=lambda: _env("MAPILLARY_TOKEN", "MAPILLARY_ACCESS_TOKEN")
    )
    google_api_key: str | None = field(
        default_factory=lambda: _env("MAPS_API_TOKEN", "STREETVIEW_API_KEY", "GOOGLE_MAPS_API_KEY")
    )

    def resolve_area(self, area: str | None, bbox: BBox | None) -> BBox:
        if bbox is not None:
            return bbox
        if area is not None:
            key = area.strip().lower()
            if key in AREAS:
                return AREAS[key]
            raise ValueError(f"unknown area '{area}'. known: {sorted(AREAS)}")
        raise ValueError("must pass area or bbox")
