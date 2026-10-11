"""The targets time-assistant can write to. To add one, see docs/adding-a-target.md."""
from __future__ import annotations

from .base import Existing, Target, Wanted  # noqa: F401  (re-exported for target authors)
from .timekeeper import TimeKeeperTarget

# Shipped with time-assistant; each needs docs/targets/<type>.md and
# tests/test_target_<type>.py (tests/test_registry.py checks both).
BUILTIN = (TimeKeeperTarget,)

TARGETS: dict[str, type] = {cls.type: cls for cls in BUILTIN}


def register(cls) -> type:
    """Make a Target subclass available under its `type` (also usable as a decorator)."""
    if not cls.type:
        raise ValueError(f"{cls.__name__} has no `type`")
    TARGETS[cls.type] = cls
    return cls


def get(type_name: str) -> type:
    try:
        return TARGETS[type_name]
    except KeyError:
        raise SystemExit(f"Unknown target type {type_name!r}. Available: "
                         f"{', '.join(sorted(TARGETS))}.") from None
