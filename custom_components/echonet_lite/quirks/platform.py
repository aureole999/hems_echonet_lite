"""Attach quirk behavior to upstream entity classes without editing them.

Platform modules pass their entity class through a ``quirk_*`` helper at setup
time. The helper returns a cached subclass that puts a quirk mixin in front of
the upstream class, so the upstream module only needs a one-line hook and the
behavior itself lives in this package.
"""

from __future__ import annotations

from functools import cache


@cache
def with_mixin[T: type](mixin: type, base: T) -> T:
    """Return ``base`` extended by ``mixin`` (cached per pair)."""
    return type(base.__name__, (mixin, base), {"__module__": base.__module__})  # type: ignore[return-value]
