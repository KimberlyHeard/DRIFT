"""
Clock implementations.

This module contains:
  - StepClock: integer-microsecond deterministic clock for driver testing
    (Task 04).  advance_us() is called explicitly; no real sleeps.
  - VirtualClock: full virtual clock for simulation with trace support
    (Task 05).

The Clock Protocol is defined in interfaces.py.
"""

from __future__ import annotations

from drift.interfaces import Clock  # noqa: F401 — re-exported for convenience


class StepClock:
    """
    Deterministic integer-microsecond clock for driver and scripted-bus tests.

    Virtual time starts at 0 and advances only via advance_us().
    No real-wall-clock dependency.

    Implements the Clock protocol from drift.interfaces.
    """

    def __init__(self, start_us: int = 0) -> None:
        if start_us < 0:
            raise ValueError(f"start_us must be non-negative; got {start_us}")
        self._time_us: int = start_us

    def now_us(self) -> int:
        """Return current virtual time in microseconds."""
        return self._time_us

    def advance_us(self, delta_us: int) -> None:
        """Advance virtual time by delta_us microseconds (must be > 0)."""
        if delta_us <= 0:
            raise ValueError(f"advance_us requires delta > 0; got {delta_us}")
        self._time_us += delta_us


class VirtualClock:
    """
    Integer-microsecond virtual clock for virtual-device model simulation.

    Virtual time starts at 0 and advances only via advance_us().
    No real-wall-clock dependency.  Identical semantics to StepClock but
    named separately so simulator code imports a clearly simulator-scoped type.

    Implements the Clock protocol from drift.interfaces.
    """

    def __init__(self, start_us: int = 0) -> None:
        if start_us < 0:
            raise ValueError(f"start_us must be non-negative; got {start_us}")
        self._time_us: int = start_us

    def now_us(self) -> int:
        """Return current virtual time in microseconds."""
        return self._time_us

    def advance_us(self, delta_us: int) -> None:
        """Advance virtual time by delta_us microseconds (must be > 0)."""
        if delta_us <= 0:
            raise ValueError(f"advance_us requires delta > 0; got {delta_us}")
        self._time_us += delta_us
