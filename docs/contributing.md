# Contributing

The full guide is [`CONTRIBUTING.md`](https://github.com/Prekzursil/tracelines/blob/main/CONTRIBUTING.md)
in the repo. The essentials:

```bash
git clone https://github.com/Prekzursil/tracelines
cd tracelines
pip install -e ".[dev]"
pre-commit install
```

## The one rule that must never regress

> Output must contain only official Google car coverage — never a photosphere/photopet.

Any change to the Google provider, `is_official_panoid`, or the source filter **must** keep the
invariant green:

```bash
python scripts/verify_hardrule.py    # re-runs the sweep, asserts 0 leaks (CI gates on this)
pytest tests/test_nearest.py         # deterministic HARD-RULE skip tests
```

## Tests

- Hermetic tests (`pytest`) gate every PR. Live tests are `@pytest.mark.network` and run on the
  nightly canary / locally with `pytest -m network`.
- New reverse-engineering findings must be **date-stamped**, cited, and reflected in
  [Findings](findings.md) (and `verify_hardrule.py` if load-bearing).

## Licensing

Contributions are licensed **AGPL-3.0-or-later**, like the project. Don't add dependencies with
incompatible licenses.
