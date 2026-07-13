"""Coverage source providers."""

from .base import Provider, ProviderResult

__all__ = ["Provider", "ProviderResult", "get_provider", "PROVIDERS"]


def get_provider(name: str):
    """Lazy-import a provider by name so a missing optional dep only breaks that source."""
    name = name.strip().lower()
    if name == "google":
        from .google_sl import GoogleStreetlevelProvider

        return GoogleStreetlevelProvider()
    if name == "mapillary":
        from .mapillary import MapillaryProvider

        return MapillaryProvider()
    if name == "kartaview":
        from .kartaview import KartaViewProvider

        return KartaViewProvider()
    raise ValueError(f"unknown provider '{name}'")


PROVIDERS = ("google", "mapillary", "kartaview")
