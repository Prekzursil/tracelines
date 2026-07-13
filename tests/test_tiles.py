import mercantile

from svcoverage.tiles import count_tiles, deg2tile, tile2deg, tile_bounds, tiles_in_bbox

BUCH = (44.4268, 26.1025)


def test_deg2tile_matches_mercantile():
    for z in (12, 14, 17):
        x, y = deg2tile(BUCH[0], BUCH[1], z)
        t = mercantile.tile(BUCH[1], BUCH[0], z)  # mercantile.tile(lng, lat, zoom)
        assert (x, y) == (t.x, t.y)


def test_tile_bounds_contain_point_and_nw_corner():
    z = 17
    x, y = deg2tile(BUCH[0], BUCH[1], z)
    lat, lon = tile2deg(x, y, z)
    w, s, e, n = tile_bounds(x, y, z)
    assert w <= BUCH[1] <= e
    assert s <= BUCH[0] <= n
    assert abs(n - lat) < 1e-9 and abs(w - lon) < 1e-9


def test_tiles_in_bbox_covers_corners_and_counts():
    w, s, e, n = 26.09, 44.42, 26.11, 44.44
    z = 17
    tiles = list(tiles_in_bbox(w, s, e, n, z))
    assert len(tiles) == count_tiles(w, s, e, n, z)
    for lat, lon in [(s, w), (n, e), (s, e), (n, w)]:
        assert deg2tile(lat, lon, z) in tiles


def test_bbox_inside_single_tile():
    z = 17
    x, y = deg2tile(BUCH[0], BUCH[1], z)
    w, s, e, n = tile_bounds(x, y, z)
    tiles = list(tiles_in_bbox(w + 1e-7, s + 1e-7, e - 1e-7, n - 1e-7, z))
    assert (x, y) in tiles
