"""Slippy-map tile math (Web Mercator / XYZ). No external dependency required.

mercantile is used in tests as an independent cross-check, but the runtime uses
these ~5-line implementations so the package stays dependency-light.
"""

from __future__ import annotations

import math
from collections.abc import Iterator

_MAX_LAT = 85.05112877980659  # Web Mercator clamp


def deg2tile(lat: float, lon: float, z: int) -> tuple[int, int]:
    """(lat, lon) -> (x, y) tile indices at zoom z."""
    lat = max(min(lat, _MAX_LAT), -_MAX_LAT)
    n = 1 << z
    x = int((lon + 180.0) / 360.0 * n)
    lat_r = math.radians(lat)
    y = int((1.0 - math.asinh(math.tan(lat_r)) / math.pi) / 2.0 * n)
    x = max(0, min(n - 1, x))
    y = max(0, min(n - 1, y))
    return x, y


def tile2deg(x: int, y: int, z: int) -> tuple[float, float]:
    """NW (top-left) corner of tile (x, y) at zoom z -> (lat, lon)."""
    n = 1 << z
    lon = x / n * 360.0 - 180.0
    lat = math.degrees(math.atan(math.sinh(math.pi * (1.0 - 2.0 * y / n))))
    return lat, lon


def tile_bounds(x: int, y: int, z: int) -> tuple[float, float, float, float]:
    """(west, south, east, north) geographic bounds of tile (x, y) at zoom z."""
    north, west = tile2deg(x, y, z)
    south, east = tile2deg(x + 1, y + 1, z)
    return west, south, east, north


def tiles_in_bbox(
    west: float, south: float, east: float, north: float, z: int
) -> Iterator[tuple[int, int]]:
    """Yield every (x, y) tile at zoom z intersecting the bbox."""
    x_nw, y_nw = deg2tile(north, west, z)  # NW corner: min x, min y
    x_se, y_se = deg2tile(south, east, z)  # SE corner: max x, max y
    for x in range(min(x_nw, x_se), max(x_nw, x_se) + 1):
        for y in range(min(y_nw, y_se), max(y_nw, y_se) + 1):
            yield x, y


def count_tiles(west: float, south: float, east: float, north: float, z: int) -> int:
    x_nw, y_nw = deg2tile(north, west, z)
    x_se, y_se = deg2tile(south, east, z)
    return (abs(x_se - x_nw) + 1) * (abs(y_se - y_nw) + 1)
