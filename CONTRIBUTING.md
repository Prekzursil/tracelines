# Contributing to tracelines

Thanks for your interest! This is a research/GIS tool with one non-negotiable invariant, so
please read the short list below before opening a PR.

## Setup

```bash
git clone https://github.com/Prekzursil/tracelines
cd tracelines
pip install -e ".[dev]"
pre-commit install        # ruff + gitleaks on every commit
```

## The one rule that must never regress

> **Output must contain only official Google car coverage — never a photosphere/photopet.**

Any change touching the Google provider, `is_official_panoid`, or the source filter **must** keep
the HARD-RULE invariant green:

```bash
python scripts/verify_hardrule.py     # re-runs the coverage sweep, asserts 0 non-official
pytest tests/test_nearest.py          # the deterministic skip tests
```

CI re-asserts this on every push. A PR that weakens the filter will not be merged.

## Tests

- **Hermetic tests run offline** and gate every PR: `pytest`.
- **Live tests** hit real endpoints and are marked `@pytest.mark.network` — they run only on the
  nightly canary and locally via `pytest -m network` (fork PRs can't read tokens).
- New pure logic needs a hermetic test. New network code should have a hermetic test of its parse
  logic plus, where possible, a `network`-marked live smoke test.

## Style

- `ruff check` and `ruff format` must pass (enforced in CI + pre-commit).
- Type hints on public functions; `mypy` runs (non-blocking for now).
- Match the surrounding code; keep functions small and testable (pure logic separated from I/O).

## Reverse-engineering findings

If you add or change a claim about an undocumented endpoint / id format / `source` value:
- **date-stamp it** and cite your evidence (a reproducible command or a source URL);
- add or update the relevant row in `docs/findings.md` and, if load-bearing, `scripts/verify_hardrule.py`.

## Licensing of contributions

By contributing you agree your contributions are licensed under **AGPL-3.0-or-later**, the same as
the project. Don't add dependencies with incompatible (proprietary/GPL-incompatible) licenses.

## Commit / PR

- Small, focused commits; conventional-ish messages welcome.
- Update `CHANGELOG.md` under `[Unreleased]`.
- Describe what you verified (tests run, endpoints hit) in the PR.
