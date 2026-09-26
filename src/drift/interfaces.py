"""
Core DRIFT interfaces and data types.

All Protocol definitions are structural (runtime_checkable where useful).
Dataclasses are frozen/immutable where appropriate to prevent trace mutation.

Source policy:
  - Seven-bit I2C address range: 0x00–0x7F. Addresses 0x00 and 0x78–0x7F
    are reserved by the I2C specification; 0x48 is the selected TMP117 address
    (ADD0 grounded, TI TMP117 SNOSD82D Table 7-2, p21).
  - A wire address byte includes a read/write bit; this API uses the unshifted
    seven-bit number only.
  - DRIFT policy: 100 ms timeout, 1 ms polling interval.
"""

from __future__ import annotations

import dataclasses
from typing import Protocol, runtime_checkable

# ---------------------------------------------------------------------------
# Address validation
# ---------------------------------------------------------------------------

# Inclusive bounds for valid, non-reserved seven-bit I2C addresses.
# Addresses 0x00 (general call) and 0x78–0x7F (10-bit prefix) are reserved.
_I2C_7BIT_MIN: int = 0x01
_I2C_7BIT_MAX: int = 0x7F
_I2C_RESERVED_HIGH_START: int = 0x78

# Selected TMP117 address per AGENTS.md / playbook section 5.
TMP117_ADDRESS: int = 0x48


class AddressError(ValueError):
    """Raised when a seven-bit I2C address is out of range or reserved."""


def validate_7bit_address(address: int) -> int:
    """
    Validate a seven-bit I2C address and return it unchanged.

    Raises AddressError for:
    - Values outside 0x01–0x7F (out of seven-bit range or general-call 0x00)
    - Values in the reserved 10-bit prefix range 0x78–0x7F

    >>> validate_7bit_address(0x48)
    72
    >>> validate_7bit_address(0x00)
    Traceback (most recent call last):
        ...
    drift.interfaces.AddressError: Address 0x00 is out of the valid seven-bit range (0x01–0x77)
    """
    if not isinstance(address, int) or isinstance(address, bool):
        raise AddressError(
            f"Address {address!r} is not an integer"
        )
    if not (_I2C_7BIT_MIN <= address <= _I2C_7BIT_MAX):
        raise AddressError(
            f"Address {address:#04x} is out of the valid seven-bit range "
            f"(0x01–0x{_I2C_7BIT_MAX:#04x})"
        )
    if address >= _I2C_RESERVED_HIGH_START:
        raise AddressError(
            f"Address {address:#04x} is in the reserved 10-bit address prefix "
            f"range (0x78–0x7F)"
        )
    return address


# ---------------------------------------------------------------------------
# Bus protocol
# ---------------------------------------------------------------------------

@runtime_checkable
class RegisterBus(Protocol):
    """
    Addressed register read/write interface.

    Implementors: scripted test bus, virtual device bus adapter.
    The driver must only use this interface; it cannot inspect device internals.
    """

    def read_register(
        self, address_7bit: int, register: int, length: int
    ) -> bytes:
        """
        Read `length` bytes from `register` on the device at `address_7bit`.

        Raises:
            AddressError: if address is out of valid range.
            BusNackError: if the device does not acknowledge.
            ProtocolReadError: if the response has wrong length.
        """
        ...

    def write_register(
        self, address_7bit: int, register: int, payload: bytes
    ) -> None:
        """
        Write `payload` to `register` on the device at `address_7bit`.

        Raises:
            AddressError: if address is out of valid range.
            BusNackError: if the device does not acknowledge.
        """
        ...


# ---------------------------------------------------------------------------
# Clock protocol
# ---------------------------------------------------------------------------

@runtime_checkable
class Clock(Protocol):
    """
    Integer-microsecond virtual clock.

    Virtual time is advanced explicitly; no real sleeps in simulation.
    """

    def now_us(self) -> int:
        """Return current virtual time in microseconds (non-negative integer)."""
        ...

    def advance_us(self, delta_us: int) -> None:
        """Advance virtual time by `delta_us` microseconds (must be > 0)."""
        ...


# ---------------------------------------------------------------------------
# Typed outcome errors
# ---------------------------------------------------------------------------

class BusNackError(OSError):
    """Device did not acknowledge a bus transaction."""


class DeviceIdentityError(ValueError):
    """Device ID does not match the expected part identifier."""


class ProtocolReadError(ValueError):
    """Register read returned wrong number of bytes."""


class ConversionTimeout(TimeoutError):
    """Conversion did not complete within the allowed virtual time."""


class UnsupportedProfile(NotImplementedError):
    """Requested profile is not reviewed or supported by this build."""


class ExecutionLimitExceeded(RuntimeError):
    """Scenario exceeded the maximum operation count or virtual time budget."""


# ---------------------------------------------------------------------------
# Data types
# ---------------------------------------------------------------------------

@dataclasses.dataclass(frozen=True)
class DeviceIdentity:
    """
    Result of a successful identify() call.

    part_id: lower 12 bits of device-ID register (TMP117: 0x117, SNOSD82D p32)
    revision: upper 4 bits (may vary across chip revisions)
    raw_bytes: the two raw register bytes as received
    """
    part_id: int
    revision: int
    raw_bytes: bytes


@dataclasses.dataclass(frozen=True)
class Measurement:
    """
    Result of a successful measure() call.

    raw_bytes: two register bytes as received (MSB first for TMP117)
    celsius: decoded temperature in degrees Celsius
    virtual_time_us: virtual clock reading when data-ready was observed
    """
    raw_bytes: bytes
    celsius: float
    virtual_time_us: int


@dataclasses.dataclass(frozen=True)
class TraceEvent:
    """
    Immutable record of one bus operation.

    sequence: zero-based operation index within this run
    virtual_time_us: clock reading before the operation
    address_7bit: I2C device address
    register: register number
    operation: "read" or "write"
    sent_bytes: bytes written (empty for reads)
    received_bytes: bytes returned (empty for writes)
    outcome: "ok", "nack", "protocol_error", "timeout", or other error label
    fact_ids: applicable contract fact IDs (e.g. ["F02", "F04"])
    """
    sequence: int
    virtual_time_us: int
    address_7bit: int
    register: int
    operation: str
    sent_bytes: bytes
    received_bytes: bytes
    outcome: str
    fact_ids: tuple[str, ...]


@dataclasses.dataclass(frozen=True)
class AssertionRecord:
    """
    One assertion result from a scenario run.

    assertion_id: short identifier (e.g. "temperature_25c")
    expected: the independently prepared expected value (literal, never derived from production)
    actual: the observed value
    passed: True if actual matches expected within applicable tolerance
    fact_ids: contract fact IDs that the assertion exercises
    trace_indices: sequence numbers of the relevant TraceEvents
    """
    assertion_id: str
    expected: object
    actual: object
    passed: bool
    fact_ids: tuple[str, ...]
    trace_indices: tuple[int, ...]


@dataclasses.dataclass(frozen=True)
class RunReport:
    """
    Immutable run report.  One report per scenario execution.

    schema_version: format version for this report structure
    run_id: unique identifier for this run (e.g. UUID)
    scenario_id: name of the executed scenario
    profile_id: device/operating profile (e.g. "tmp117_one_shot_no_average")
    driver_variant: which driver code was used (e.g. "baseline", "byte_swap")
    execution_status: "completed" or "infrastructure_error"
    device_outcome: typed result or error class name
    assertions: ordered assertion records
    trace: ordered bus trace events
    verification_status: "pass", "fail", or "unsupported"
    expected_behavior_observed: whether the scenario's intended behavior was seen
    limitations: human-readable caveats
    """
    schema_version: str
    run_id: str
    scenario_id: str
    profile_id: str
    driver_variant: str
    execution_status: str
    device_outcome: str
    assertions: tuple[AssertionRecord, ...]
    trace: tuple[TraceEvent, ...]
    verification_status: str
    expected_behavior_observed: bool
    limitations: str
