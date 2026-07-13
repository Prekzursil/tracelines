"""
check_street_view_availability — FIXED.

The original hit the Google `/streetview/metadata` endpoint and returned True for ANY
panorama with status OK — including user photospheres/photopets — so it could NOT tell a
blue continuous line from a blue circle/dot. This version answers the real question:

    "Is there genuine official Google CAR Street View coverage (a blue line) near here —
     never a photosphere/photopet?"

It uses the `tracelines` package (streetlevel-based), which sources ONLY the official z17
coverage layer and gates on is_official_panoid + source == 'launch'. No API key needed.

For bulk area extraction to GeoJSON polylines, use the CLI instead:
    python -m tracelines extract --area bucharest-city --sources google --out out.geojson
    python -m tracelines nearest 44.435072 26.050430
"""
from tracelines.nearest import find_nearest_coverage


def check_street_view_availability(lat, lng, api_key=None, retry=3, radius=50,
                                   include_trekker=False):
    """True iff genuine official car Street View coverage exists within `radius` metres.

    Never returns True for a photosphere/photopet (the HARD RULE). `api_key` is accepted
    for backwards compatibility but unused — streetlevel needs no key. `retry` is likewise
    kept for signature compatibility (retries are handled inside tracelines).
    """
    res = find_nearest_coverage(lat, lng, verify_source=True, include_trekker=include_trekker)
    if res is None:
        return False
    return res.distance_m <= radius


if __name__ == "__main__":
    for lat, lng in [(44.435072, 26.050430), (44.455934, 26.097371)]:
        res = find_nearest_coverage(lat, lng, verify_source=True)
        tag = f"{res.pano.sv_source} @ {res.distance_m:.0f} m" if res else "none"
        print(f"{lat}, {lng} -> coverage={check_street_view_availability(lat, lng)}  ({tag})")
