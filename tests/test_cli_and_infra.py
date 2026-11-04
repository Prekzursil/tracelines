"""Deterministic tests for CLI arg-parsing, cache, and config resolution."""

import pytest

from tracelines import cli
from tracelines.cache import Cache
from tracelines.config import AREAS, BBox, Settings


def test_cache_memory_backend_roundtrip(monkeypatch):
    from tracelines import cache as cache_mod

    monkeypatch.setattr(cache_mod, "diskcache", None)  # force in-memory fallback
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


def test_settings_read_secrets_from_env(monkeypatch):
    """_env()'s found-branch: the first set variable wins, in declared order."""
    monkeypatch.setenv("MAPILLARY_ACCESS_TOKEN", "MLY|FALLBACK")
    monkeypatch.setenv("MAPILLARY_TOKEN", "MLY|PRIMARY")
    monkeypatch.setenv("MAPS_API_TOKEN", "gmaps-key")
    s = Settings()
    assert s.mapillary_token == "MLY|PRIMARY"
    assert s.google_api_key == "gmaps-key"


def test_settings_env_fallback_order(monkeypatch):
    monkeypatch.delenv("MAPILLARY_TOKEN", raising=False)
    monkeypatch.setenv("MAPILLARY_ACCESS_TOKEN", "MLY|FALLBACK")
    assert Settings().mapillary_token == "MLY|FALLBACK"
    monkeypatch.delenv("MAPILLARY_ACCESS_TOKEN", raising=False)
    assert Settings().mapillary_token is None


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
    from tracelines.models import CoverageSegment, Source

    seg = CoverageSegment(coords=[(26.0, 44.0), (26.001, 44.0)], source=Source.GOOGLE)
    monkeypatch.setattr(
        "tracelines.pipeline.extract", lambda *a, **k: ([seg], {"counts": {"google": 1}})
    )
    out = tmp_path / "o.geojson"
    rc = cli.main(["extract", "--area", "bucharest-city", "--sources", "google", "--out", str(out)])
    assert rc == 0
    assert out.exists()
    printed = capsys.readouterr().out
    assert '"segments": 1' in printed


# ---- __main__ import surface ---------------------------------------------------


def test_dunder_main_imports_and_exposes_cli():
    import tracelines.__main__ as dunder

    assert callable(dunder.main)


# ---- cache as a context manager -------------------------------------------------


def test_cache_context_manager_closes(tmp_path):
    from tracelines.cache import Cache

    with Cache(str(tmp_path / "cm")) as c:
        c.set("k", 1)
        assert c.get("k") == 1
    # closing twice is safe (memory backend has nothing to close)
    c2 = Cache("unused", enabled=False)
    with c2:
        pass


# ---- cli _resolve branches -------------------------------------------------------


def test_cli_resolve_bbox_wins_over_area(capsys):
    p = cli.build_parser()
    bb = BBox(1, 2, 3, 4)
    a = p.parse_args(["probe", "--area", "bucharest-city", "--bbox", "1,2,3,4"])
    assert cli._resolve(a) == bb


def test_cli_resolve_named_area(capsys):
    p = cli.build_parser()
    a = p.parse_args(["probe", "--area", "BUCHAREST-CITY"])  # case-insensitive
    from tracelines.config import AREAS

    assert cli._resolve(a) == AREAS["bucharest-city"]


def test_cli_resolve_unknown_area_exits(monkeypatch, capsys):
    p = cli.build_parser()
    a = p.parse_args(["probe", "--area", "atlantis"])
    with pytest.raises(SystemExit) as ei:
        cli._resolve(a)
    assert ei.value.code == 2
    assert "unknown area" in capsys.readouterr().err


def test_cli_resolve_requires_area_or_bbox_exits(capsys):
    p = cli.build_parser()
    a = p.parse_args(["probe"])
    with pytest.raises(SystemExit) as ei:
        cli._resolve(a)
    assert ei.value.code == 2
    assert "must pass --area or --bbox" in capsys.readouterr().err


# ---- cmd_probe / cmd_nearest over the CLI entrypoint ----------------------------


def test_cli_probe_prints_provider_stats(monkeypatch, capsys):

    monkeypatch.setattr(
        "tracelines.probe.density_probe",
        lambda bbox, sources, settings: {"google": {"available": True, "segments": 0}},
    )
    rc = cli.main(["probe", "--area", "bucharest-city", "--sources", "google"])
    assert rc == 0
    out = capsys.readouterr().out
    assert '"available": true' in out


def test_cli_nearest_prints_found_pano(monkeypatch, capsys):
    from tracelines.nearest import Nearest

    class FakePano:
        id = "Ui8V1HlfwJBw8pnmoShJfw"
        lat, lon = 44.435, 26.050
        is_third_party = False
        sv_source = "launch"
        date = "2024-07"
        degree = 2

    monkeypatch.setattr(
        "tracelines.nearest.find_nearest_coverage",
        lambda lat, lon, **k: Nearest(pano=FakePano(), distance_m=12.34),
    )
    rc = cli.main(["nearest", "44.435072", "26.050430"])
    assert rc == 0
    out = capsys.readouterr().out
    assert '"id": "Ui8V1HlfwJBw8pnmoShJfw"' in out
    assert '"distance_m": 12.3' in out
    assert "map_action=pano" in out


def test_cli_nearest_returns_one_when_no_coverage(monkeypatch, capsys):
    monkeypatch.setattr("tracelines.nearest.find_nearest_coverage", lambda lat, lon, **k: None)
    rc = cli.main(["nearest", "0.0", "0.0", "--include-trekker"])
    assert rc == 1
    out = capsys.readouterr().out
    assert '"reason": "no official coverage found"' in out


def test_cli_extract_without_out_prints_only(monkeypatch, capsys, tmp_path):
    from tracelines.models import CoverageSegment, Source

    seg = CoverageSegment(coords=[(26.0, 44.0), (26.001, 44.0)], source=Source.GOOGLE)
    monkeypatch.setattr(
        "tracelines.pipeline.extract", lambda *a, **k: ([seg], {"counts": {"google": 1}})
    )
    rc = cli.main(["extract", "--area", "bucharest-city"])
    assert rc == 0
    assert '"segments": 1' in capsys.readouterr().out
