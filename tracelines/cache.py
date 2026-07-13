"""Tile-level cache for resumable crawls. diskcache-backed, in-memory fallback.

We cache lightweight JSON-able dicts (never live library objects) so entries are
portable and picklable, and a crawl can resume after interruption.
"""

from __future__ import annotations

from typing import Any

try:
    import diskcache  # type: ignore

    _HAS_DISKCACHE = True
except ImportError:  # pragma: no cover - environment dependent
    _HAS_DISKCACHE = False


class Cache:
    def __init__(self, path: str, enabled: bool = True):
        self.enabled = enabled
        self._c = None
        self._mem: dict | None = None
        if enabled and _HAS_DISKCACHE:
            self._c = diskcache.Cache(path)
        else:
            self._mem = {}

    @property
    def backend(self) -> str:
        if not self.enabled:
            return "disabled"
        return "diskcache" if self._c is not None else "memory"

    def get(self, key: str, default: Any = None) -> Any:
        if not self.enabled:
            return default
        if self._c is not None:
            return self._c.get(key, default)
        return self._mem.get(key, default)  # type: ignore[union-attr]

    def set(self, key: str, value: Any) -> None:
        if not self.enabled:
            return
        if self._c is not None:
            self._c.set(key, value)
        else:
            self._mem[key] = value  # type: ignore[index]

    def __contains__(self, key: str) -> bool:
        if not self.enabled:
            return False
        if self._c is not None:
            return key in self._c
        return key in self._mem  # type: ignore[operator]

    def close(self) -> None:
        if self._c is not None:
            self._c.close()

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        self.close()
