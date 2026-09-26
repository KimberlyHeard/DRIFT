"""
RegisterBus implementations.

This module will contain:
  - ScriptedBus: a test-only bus that checks literal ordered expected operations
    and returns literal bytes (Task 04).
  - VirtualDeviceBus: an adapter that routes addressed register calls to a
    virtual device model (Task 05).

Neither implementation is present yet; the Protocol is defined in interfaces.py.
"""

from drift.interfaces import (  # noqa: F401 — re-exported for convenience
    AddressError,
    BusNackError,
    ProtocolReadError,
    RegisterBus,
    validate_7bit_address,
)
