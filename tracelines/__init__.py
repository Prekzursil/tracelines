"""tracelines — extract continuous street-level coverage polylines (the "blue lines").

Multi-source fusion of Google (via streetlevel), Mapillary (sequence vector tiles), and
KartaView (bbox polylines), filtering out isolated panoramas / photospheres (the "circles").

Output is only official Google car Street View coverage — never a photosphere (the HARD RULE).
See the docs for the filter contract and verification: https://prekzursil.github.io/tracelines/docs/
"""

from .config import AREAS, BUCHAREST_CITY, BUCHAREST_METRO, BBox, Settings
from .models import CoverageSegment, Pano, Source, haversine_m, line_length_m

__version__ = "0.2.0"

__all__ = [
    "Source",
    "Pano",
    "CoverageSegment",
    "haversine_m",
    "line_length_m",
    "Settings",
    "BBox",
    "AREAS",
    "BUCHAREST_CITY",
    "BUCHAREST_METRO",
    "__version__",
]
