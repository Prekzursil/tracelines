"""Deterministic tests for CLI arg-parsing, cache, and config resolution."""

import pytest

from svcoverage import cli
from svcoverage.cache import Cache
from svcoverage.config import AREAS, BBox, Settings


def test_cache_memory_backend_roundtrip(monkeypatch):
    from svcoverage import cache as cache_mod

    monkeypatch.setattr(cache_mod, "_HAS_DISKCACHE", False)  # force in-memory fallback
    c = Cache("mem-only", enabled=True)
    assert c.backend == "memory"
    assert "k" not in c
    c.set("k", [1, 2, 3])
    assert c.get("k") == [1, 2, 3]
    assert "k" in c
    c.close()


def test_cache_diskcache_roundtrip(tmp_path):
    import importlib.util

    if importlib.util.find_spec("diskcache") is None:
        pytest.skip("diskcache not installed")
    c = Cache(str(tmp_path / "dc"), enabled=True)
    assert c.backend == "diskcache"
    c.set("k", {"a": 1})
    assert c.get("k") == {"a": 1}
    assert "k" in c
    c.close()


def test_cache_disabled():
    c = Cache("unused", enabled=False)
    c.set("k", 1)
    assert c.get("k", "default") == "default"
    assert "k" not in c
    assert c.backend == "disabled"


def test_settings_resolve_area_and_bbox():
    s = Settings()
    assert s.resolve_area("bucharest-city", None) == AREAS["bucharest-city"]
    bb = BBox(1, 2, 3, 4)
    assert s.resolve_area(None, bb) is bb
    with pytest.raises(ValueError):
        s.resolve_area("atlantis", None)
    with pytest.raises(ValueError):
        s.resolve_area(None, None)


def test_cli_parse_bbox():
    assert cli._parse_bbox("1,2,3,4") == BBox(1.0, 2.0, 3.0, 4.0)
    import argparse

    with pytest.raises(argparse.ArgumentTypeError):
        cli._parse_bbox("1,2,3")


def test_cli_settings_from_args_overrides():
    p = cli.build_parser()
    a = p.parse_args(
        [
            "extract",
            "--area",
            "bucharest-city",
            "--min-run",
            "5",
            "--precision",
            "--concurrency",
            "8",
        ]
    )
    s = cli._settings_from_args(a)
    assert s.min_run == 5
    assert s.precision is True
    assert s.concurrency == 8
    # untouched defaults remain
    assert s.include_trekker is False


def test_cli_resolve_requires_area_or_bbox():
    p = cli.build_parser()
    a = p.parse_args(["probe"])
    with pytest.raises(SystemExit):
        cli._resolve(a)


def test_cli_extract_with_fake_pipeline(monkeypatch, tmp_path, capsys):
    from svcoverage.models import CoverageSegment, Source

    seg = CoverageSegment(coords=[(26.0, 44.0), (26.001, 44.0)], source=Source.GOOGLE)
    monkeypatch.setattr(
        "svcoverage.pipeline.extract", lambda *a, **k: ([seg], {"counts": {"google": 1}})
    )
    out = tmp_path / "o.geojson"
    rc = cli.main(["extract", "--area", "bucharest-city", "--sources", "google", "--out", str(out)])
    assert rc == 0
    assert out.exists()
    printed = capsys.readouterr().out
    assert '"segments": 1' in printed
