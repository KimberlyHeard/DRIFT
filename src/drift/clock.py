"""
Clock implementations.

This module will contain:
  - VirtualClock: integer-microsecond deterministic clock for simulation
    (Task 05). State and time reset per scenario run.

The Clock Protocol is defined in interfaces.py.
"""

from drift.interfaces import Clock  # noqa: F401 — re-exported for convenience
