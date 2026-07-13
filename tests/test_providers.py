import pytest

from tracelines.models import Source
from tracelines.providers import PROVIDERS, get_provider


def test_get_provider_returns_instances():
    assert get_provider("google").source == Source.GOOGLE
    assert get_provider("mapillary").source == Source.MAPILLARY
    assert get_provider("kartaview").source == Source.KARTAVIEW


def test_get_provider_unknown_raises():
    with pytest.raises(ValueError):
        get_provider("bing")


def test_providers_constant():
    assert set(PROVIDERS) == {"google", "mapillary", "kartaview"}


def test_provider_availability_shape():
    for name in PROVIDERS:
        ok, why = get_provider(name).available()
        assert isinstance(ok, bool)
        assert isinstance(why, str)
