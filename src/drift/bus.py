"""
RegisterBus implementations.

This module contains:
  - ScriptedBus: a test-only bus that checks literal ordered expected operations
    and returns literal bytes (Task 04).
  - VirtualDeviceBus: an adapter that routes addressed register calls to a
    virtual device model (Task 05).

The Protocol is defined in interfaces.py.
"""

from __future__ import annotations

import dataclasses
from typing import Literal

from drift.interfaces import (  # noqa: F401 — re-exported for convenience
    AddressError,
    BusNackError,
    ProtocolReadError,
    RegisterBus,
    validate_7bit_address,
)


# ---------------------------------------------------------------------------
# Scripted bus — test-only ordered transaction checker
# ---------------------------------------------------------------------------

@dataclasses.dataclass
class _ScriptedStep:
    """One expected bus operation and its scripted response."""
    operation: Literal["read", "write"]
    address_7bit: int
    register: int
    # For reads: bytes to return; for writes: bytes expected from the caller.
    payload: bytes
    # If True, raise BusNackError instead of returning payload.
    nack: bool = False


class ScriptedBusExhausted(RuntimeError):
    """Driver issued more bus calls than the script defined."""


class ScriptedBusStepMismatch(AssertionError):
    """Driver issued a call that does not match the next scripted step."""


class ScriptedBus:
    """
    Test-only RegisterBus that replays a pre-programmed list of transactions.

    Each step asserts the operation type, address, register, and (for writes)
    the written payload.  For reads it returns the scripted bytes.

    The bus deliberately raises ScriptedBusExhausted if more calls are issued
    than the script defines, and ScriptedBusStepMismatch on any mismatch.
    This ensures the driver issues exactly the expected sequence.

    Usage
    -----
    bus = ScriptedBus([
        ScriptedBus.step_read(0x48, 0x0F, b"\\x01\\x17", nack=False),
        ScriptedBus.step_write(0x48, 0x01, b"\\x06\\x00"),
    ])
    """

    def __init__(self, steps: list[_ScriptedStep]) -> None:
        self._steps = list(steps)
        self._index = 0

    # ------------------------------------------------------------------
    # Convenience constructors
    # ------------------------------------------------------------------

    @staticmethod
    def step_read(
        address_7bit: int, register: int, response: bytes, *, nack: bool = False
    ) -> _ScriptedStep:
        """Create a scripted read step."""
        return _ScriptedStep("read", address_7bit, register, response, nack)

    @staticmethod
    def step_write(
        address_7bit: int, register: int, payload: bytes, *, nack: bool = False
    ) -> _ScriptedStep:
        """Create a scripted write step."""
        return _ScriptedStep("write", address_7bit, register, payload, nack)

    # ------------------------------------------------------------------
    # RegisterBus protocol
    # ------------------------------------------------------------------

    def _next_step(self, operation: str, address_7bit: int, register: int) -> _ScriptedStep:
        if self._index >= len(self._steps):
            raise ScriptedBusExhausted(
                f"ScriptedBus: step {self._index} requested "
                f"({operation} addr={address_7bit:#04x} reg={register:#04x}) "
                f"but script has only {len(self._steps)} steps"
            )
        step = self._steps[self._index]
        self._index += 1
        if step.operation != operation:
            raise ScriptedBusStepMismatch(
                f"Step {self._index - 1}: expected {step.operation!r} "
                f"but driver issued {operation!r} "
                f"(addr={address_7bit:#04x} reg={register:#04x})"
            )
        if step.address_7bit != address_7bit:
            raise ScriptedBusStepMismatch(
                f"Step {self._index - 1}: expected address {step.address_7bit:#04x} "
                f"but got {address_7bit:#04x}"
            )
        if step.register != register:
            raise ScriptedBusStepMismatch(
                f"Step {self._index - 1}: expected register {step.register:#04x} "
                f"but got {register:#04x}"
            )
        if step.nack:
            raise BusNackError(
                f"Scripted NACK at step {self._index - 1} "
                f"({operation} addr={address_7bit:#04x} reg={register:#04x})"
            )
        return step

    def read_register(self, address_7bit: int, register: int, length: int) -> bytes:
        step = self._next_step("read", address_7bit, register)
        if len(step.payload) != length:
            raise ProtocolReadError(
                f"ScriptedBus: step {self._index - 1} scripted {len(step.payload)} bytes "
                f"but driver requested {length}"
            )
        return step.payload

    def write_register(self, address_7bit: int, register: int, payload: bytes) -> None:
        step = self._next_step("write", address_7bit, register)
        if step.payload != payload:
            raise ScriptedBusStepMismatch(
                f"Step {self._index - 1}: expected write payload {step.payload.hex()} "
                f"but driver wrote {payload.hex()}"
            )

    @property
    def steps_remaining(self) -> int:
        """Number of scripted steps not yet consumed."""
        return len(self._steps) - self._index

    def assert_exhausted(self) -> None:
        """Assert that all scripted steps were consumed.  Call at test end."""
        if self._index < len(self._steps):
            remaining = self._steps[self._index:]
            raise AssertionError(
                f"ScriptedBus: {len(remaining)} step(s) not consumed: "
                + ", ".join(
                    f"{s.operation} reg={s.register:#04x}" for s in remaining
                )
            )


# ---------------------------------------------------------------------------
# VirtualDeviceBus — routes addressed bus calls to a virtual device model
# ---------------------------------------------------------------------------

class VirtualDeviceBus:
    """
    RegisterBus adapter that routes addressed register calls to a virtual
    device model.

    Only calls addressed to the registered device address are dispatched;
    any other address raises AddressError.

    The adapter itself does not accumulate a trace; trace events are recorded
    by the underlying device model and accessible via ``device.trace``.

    Parameters
    ----------
    device:
        The virtual device model.  Must expose ``read_register(register)``
        and ``write_register(register, payload)`` methods.
    address_7bit:
        The seven-bit I2C address that this device occupies on the bus.
    """

    def __init__(self, device, address_7bit: int = 0x48) -> None:
        self._device = device
        self._address = validate_7bit_address(address_7bit)

    def read_register(self, address_7bit: int, register: int, length: int) -> bytes:
        """
        Route a register read to the device if the address matches.

        Raises
        ------
        AddressError
            If the address does not match the registered device address.
        """
        validate_7bit_address(address_7bit)
        if address_7bit != self._address:
            raise AddressError(
                f"VirtualDeviceBus: no device at address {address_7bit:#04x}; "
                f"registered address is {self._address:#04x}"
            )
        return self._device.read_register(register)

    def write_register(self, address_7bit: int, register: int, payload: bytes) -> None:
        """
        Route a register write to the device if the address matches.

        Raises
        ------
        AddressError
            If the address does not match the registered device address.
        """
        validate_7bit_address(address_7bit)
        if address_7bit != self._address:
            raise AddressError(
                f"VirtualDeviceBus: no device at address {address_7bit:#04x}; "
                f"registered address is {self._address:#04x}"
            )
        self._device.write_register(register, payload)
