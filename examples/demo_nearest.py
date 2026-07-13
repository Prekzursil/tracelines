"""Live proof of the HARD RULE for a single point: nearest official car coverage,
never a photosphere/photopet. Prints ALL nearby candidates so the skip is visible."""
from streetlevel import streetview as sv

from svcoverage.models import haversine_m
from svcoverage.nearest import find_nearest_coverage

LAT, LON = 44.435072, 26.050430
Z = 17


def idkind(p):
    return "THIRD_PARTY(photosphere/photopet)" if p.is_third_party else "official"


def main():
    tx, ty = sv.wgs84_to_tile_coord(LAT, LON, Z)
    seen = {}
    for dx in (-1, 0, 1):
        for dy in (-1, 0, 1):
            for p in sv.get_coverage_tile(tx + dx, ty + dy):
                seen.setdefault(p.id, p)
    cands = sorted(seen.values(), key=lambda p: haversine_m(LON, LAT, p.lon, p.lat))

    print(f"Query point: {LAT}, {LON}  (z{Z} tile {tx},{ty} + 3x3 neighborhood)")
    print(f"Total candidate panos in neighborhood: {len(cands)}")
    print("\n--- 8 absolute nearest panos (ANY type), by distance ---")
    print(f"{'dist_m':>8}  {'idlen':>5}  {'is_3p':>5}  {'kind':<34}  id")
    for p in cands[:8]:
        d = haversine_m(LON, LAT, p.lon, p.lat)
        print(f"{d:8.1f}  {len(p.id):5d}  {str(p.is_third_party):>5}  {idkind(p):<34}  {p.id[:24]}")

    nearest_any = cands[0]
    nearest_3p = next((p for p in cands if p.is_third_party), None)
    nearest_official = next((p for p in cands if not p.is_third_party), None)

    print("\n--- HARD RULE check ---")
    print(f"Nearest pano of ANY type : {haversine_m(LON,LAT,nearest_any.lon,nearest_any.lat):.1f} m  "
          f"({idkind(nearest_any)})")
    if nearest_3p:
        print(f"Nearest THIRD-PARTY      : {haversine_m(LON,LAT,nearest_3p.lon,nearest_3p.lat):.1f} m  "
              f"(id {nearest_3p.id[:20]}...)  <-- MUST be skipped")
    else:
        print("Nearest THIRD-PARTY      : (none in neighborhood)")
    if nearest_official:
        print(f"Nearest OFFICIAL         : {haversine_m(LON,LAT,nearest_official.lon,nearest_official.lat):.1f} m")

    print("\n--- find_nearest_coverage() result (the function under test) ---")
    res = find_nearest_coverage(LAT, LON, verify_source=True)
    if res is None:
        print("No official continuous coverage found.")
        return
    pn = res.pano
    print(f"  id           : {pn.id}  (len {len(pn.id)} -> {'official 22-char' if len(pn.id)==22 else 'CHECK'})")
    print(f"  is_third_party: {pn.is_third_party}   <-- MUST be False")
    print(f"  sv_source    : {pn.sv_source}   <-- 'launch' = official car / blue line")
    print(f"  date         : {pn.date}")
    print(f"  degree(links): {pn.degree}   <-- >=1 => on a continuous line, not a dot")
    print(f"  position     : {pn.lat:.6f}, {pn.lon:.6f}")
    print(f"  distance     : {res.distance_m:.1f} m from query point")
    print(f"  permalink    : {sv.build_permalink(pn.id) if hasattr(sv,'build_permalink') else 'n/a'}")

    assert pn.is_third_party is False, "HARD RULE VIOLATED: returned a third-party pano"
    print("\nPASS: returned official car coverage; no photosphere/photopet.")


if __name__ == "__main__":
    main()
