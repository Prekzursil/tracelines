"""Provider abstract base class + result container."""

from __future__ import annotations

import abc
from dataclasses import dataclass, field
from typing import TYPE_CHECKING

from ..models import CoverageSegment, Pano, Source

if TYPE_CHECKING:
    from ..cache import Cache
    from ..config import BBox, Settings


@dataclass
class ProviderResult:
    """What a provider returns for a bbox.

    Point sources (Google, KartaView-as-points) fill `panos` and rely on the
    stitcher. Native-line sources (Mapillary, KartaView bbox API) fill `segments`.
    A provider may fill both.
    """

    source: Source
    panos: list[Pano] = field(default_factory=list)
    segments: list[CoverageSegment] = field(default_factory=list)
    stats: dict = field(default_factory=dict)


class Provider(abc.ABC):
    source: Source

    def available(self) -> tuple[bool, str]:
        """(is_available, reason_if_not). Default: always available."""
        return True, ""

    @abc.abstractmethod
    async def fetch(self, bbox: BBox, settings: Settings, cache: Cache) -> ProviderResult:
        """Fetch coverage over bbox; must be resumable via `cache`.

        Abstract by contract: `@abc.abstractmethod` makes `Provider` non-instantiable and
        forces every concrete provider (google_sl/mapillary/kartaview) to override this.
        There is no base behaviour to inherit, so the body is intentionally empty.
        """
