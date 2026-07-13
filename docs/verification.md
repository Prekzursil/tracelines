# Verification — reproduce the proof

The HARD RULE is not a "trust us." This page is one command that re-asserts it against live data,
plus the committed evidence from the reference run.

## The invariant

> Every panorama returned by the z17 coverage-tile layer over the test region is official —
> it passes `is_official_panoid` and is not third-party. **Leaks MUST be 0.**

## Run it yourself

```bash
pip install svcoverage
python scripts/verify_hardrule.py
```

It sweeps a fixed 7×7 block of z17 tiles (49 tiles) centred on `44.4268, 26.1025` (central
Bucharest), checks every pano, writes the evidence manifest, and **exits non-zero if any leak is
found**. Expected output:

```
Swept 49 z17 tiles around (44.4268, 26.1025), radius 3
  panos:            7433
  third_party:      0
  non_official_id:  0
  HARD-RULE leaks:  0

PASS: 0 HARD-RULE violations — every coverage-tile pano is official, none third-party.
```

`--no-write` runs the assertion without writing files (this is what CI's nightly canary uses).

## Committed evidence (2026-07-13 snapshot)

| Metric | Value |
|--------|-------|
| Tiles swept (z17) | 49 |
| Panoramas | 7,433 |
| Third-party | **0** |
| Failing `is_official_panoid` | **0** |
| HARD-RULE leaks | **0** |

- Full manifest: [`docs/evidence/coverage-manifest.csv`](evidence/coverage-manifest.csv) — one row
  per pano (`tile_x, tile_y, panoid, lat, lon, is_third_party, is_official_panoid`).
- Per-tile summary: [`docs/evidence/coverage-summary.csv`](evidence/coverage-summary.csv).

!!! note "The count drifts; the invariant does not"
    Google updates coverage continuously, so the pano **count** changes between runs (it was 7,438
    a few hours before this snapshot, 7,433 at snapshot time). The **0-leak invariant** is the
    stable claim. Re-running `verify_hardrule.py` re-asserts it against whatever is live now.

## `is_official_panoid`, independently

The Layer-1 whitelist is a pure function you can exercise directly:

```python
from svcoverage.models import is_official_panoid
assert is_official_panoid("Ui8V1HlfwJBw8pnmoShJfw")          # real official -> True
assert not is_official_panoid("CIHM0ogKEICAgICfxxxxxx")      # real photosphere prefix -> False
assert not is_official_panoid("AF1QipMExampleUserPhotoSphere")  # UGC / >22 -> False
```

The deterministic HARD-RULE unit tests (a photosphere placed *on* the query point is skipped for
the official pano nearby) live in `tests/test_nearest.py` and run on every push:

```bash
pytest tests/test_nearest.py            # hermetic
pytest tests/test_nearest.py -m network # live (hits Google)
```

## CI enforcement

`scripts/verify_hardrule.py --no-write` runs on a **nightly canary** workflow. If Google's data or
streetlevel's behaviour ever changed such that a non-official pano appeared in the coverage-tile
layer, the canary would go red and the invariant claim would be retracted — not silently broken.
