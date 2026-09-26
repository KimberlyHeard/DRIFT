"""
FaultBus — a bus wrapper that intercepts one specific bus transaction and
injects a declared fault, leaving all other transactions routed normally to
the underlying bus.

Design constraints (AGENTS.md):
  - Fault injection changes the environment; it does not change driver code.
  - The normal virtual device is NOT silently altered; every transaction is
    either passed through unchanged or intercepted exactly once.
  - Every attempted transaction (including faulted ones) is recorded with the
    bytes or error actually delivered to the driver.

Supported fault kinds
---------------------
  "nack"          — raise BusNackError instead of completing the transaction.
  "short_read"    — return fewer bytes than the driver requested (1 byte for a
                    2-byte register read).
  "never_ready"   — for the configuration register read that would return
                    Data_Ready=1, return the one-shot-active word instead, so
                    the driver times out.
  "wrong_id_bits" — for a device-ID register read, corrupt the lower 12 bits
                    so they no longer equal 0x117.
"""

from __future__ import annotations

import dataclasses
from typing import Literal

from drift.interfaces import (
    BusNackError,
    RegisterBus,
    TraceEvent,
    validate_7bit_address,
)

# Configuration register (0x01) word used during an active conversion — F05/F06.
# Returned in place of the ready word to simulate "conversion never completes".
_CONFIG_ONE_SHOT_ACTIVE: int = 0x0E00

FaultKind = Literal["nack", "short_read", "never_ready", "wrong_id_bits"]


@dataclasses.dataclass(frozen=True)
class FaultSpec:
    """
    Declares one fault to inject.

    Parameters
    ----------
    kind:
        The fault type.
    match_register:
        Intercept only reads/writes to this register address.
    match_operation:
        "read" or "write" (default "read").
    trigger_count:
        Which matching transaction (1-based) to fault.  Default 1 = first.
    """

    kind: FaultKind
    match_register: int
    match_operation: str = "read"
    trigger_count: int = 1


class FaultTraceEvent:
    """Mutable accumulator for FaultBus trace events (separate from device trace)."""

    def __init__(self) -> None:
        self._events: list[TraceEvent] = []

    def record(
        self,
        sequence: int,
        virtual_time_us: int,
        address_7bit: int,
        register: int,
        operation: str,
        sent_bytes: bytes,
        received_bytes: bytes,
        outcome: str,
    ) -> None:
        self._events.append(
            TraceEvent(
                sequence=sequence,
                virtual_time_us=virtual_time_us,
                address_7bit=address_7bit,
                register=register,
                operation=operation,
                sent_bytes=sent_bytes,
                received_bytes=received_bytes,
                outcome=outcome,
                fact_ids=(),
            )
        )

    @property
    def events(self) -> tuple[TraceEvent, ...]:
        return tuple(self._events)


class FaultBus:
    """
    RegisterBus wrapper that injects exactly one declared fault per scenario.

    All transactions that do not match the fault spec are passed through to
    the underlying bus unchanged.  The matching transaction (by register,
    operation, and trigger_count) is intercepted and the declared fault is
    applied.  After the fault fires, subsequent matching transactions are
    passed through normally.

    Every transaction — pass-through or faulted — is recorded in
    ``fault_trace`` with the bytes or error label actually delivered.

    Parameters
    ----------
    inner:
        The underlying RegisterBus (e.g. VirtualDeviceBus).
    clock:
        Clock used to stamp trace events.
    spec:
        The fault to inject.
    address_7bit:
        The seven-bit address used to stamp trace events.
    """

    def __init__(
        self,
        inner: RegisterBus,
        clock,
        spec: FaultSpec,
        address_7bit: int = 0x48,
    ) -> None:
        self._inner = inner
        self._clock = clock
        self._spec = spec
        self._address = validate_7bit_address(address_7bit)
        self._match_counts: dict[tuple[str, int], int] = {}  # (op, reg) → count
        self._fault_fired = False
        self._fault_trace = FaultTraceEvent()
        self._seq = 0

    # ------------------------------------------------------------------
    # Trace access
    # ------------------------------------------------------------------

    @property
    def fault_trace(self) -> tuple[TraceEvent, ...]:
        """
        Immutable snapshot of every transaction attempted through this wrapper.

        Inspecting this does not perform a bus operation or mutate device state.
        """
        return self._fault_trace.events

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _should_fault(self, operation: str, register: int) -> bool:
        """
        Return True when this transaction should be faulted.

        For most fault kinds: fires exactly once (on the trigger_count-th
        matching transaction) and then passes through.

        For "never_ready": fires on every matching transaction after the
        trigger_count-th one, so that all config-register polls return
        not-ready and the driver eventually times out.
        """
        if operation != self._spec.match_operation:
            return False
        if register != self._spec.match_register:
            return False
        key = (operation, register)
        self._match_counts[key] = self._match_counts.get(key, 0) + 1
        count = self._match_counts[key]

        if self._spec.kind == "never_ready":
            # Fire on this and every subsequent matching transaction.
            return count >= self._spec.trigger_count

        # All other kinds: fire exactly once.
        if self._fault_fired:
            return False
        if count == self._spec.trigger_count:
            self._fault_fired = True
            return True
        return False

    def _stamp(
        self,
        address_7bit: int,
        register: int,
        operation: str,
        sent_bytes: bytes,
        received_bytes: bytes,
        outcome: str,
    ) -> None:
        self._fault_trace.record(
            self._seq,
            self._clock.now_us(),
            address_7bit,
            register,
            operation,
            sent_bytes,
            received_bytes,
            outcome,
        )
        self._seq += 1

    # ------------------------------------------------------------------
    # RegisterBus protocol
    # ------------------------------------------------------------------

    def read_register(self, address_7bit: int, register: int, length: int) -> bytes:
        if self._should_fault("read", register):
            kind = self._spec.kind

            if kind == "nack":
                self._stamp(address_7bit, register, "read", b"", b"", "nack_injected")
                raise BusNackError(
                    f"FaultBus: injected NACK on read of register {register:#04x}"
                )

            if kind == "short_read":
                # Return 1 byte instead of the requested length.
                short = bytes([0xAA])
                self._stamp(
                    address_7bit, register, "read", b"", short, "short_read_injected"
                )
                return short

            if kind == "never_ready":
                # Return the one-shot-active config word (Data_Ready bit clear)
                # so the driver keeps polling and eventually times out.
                word = _CONFIG_ONE_SHOT_ACTIVE.to_bytes(2, "big")
                self._stamp(
                    address_7bit, register, "read", b"", word, "never_ready_injected"
                )
                return word

            if kind == "wrong_id_bits":
                # Return a device-ID word where the lower 12 bits are corrupted
                # (0x118 instead of 0x117) — independent literal, not derived.
                # 0x0118: lower 12 bits = 0x118, revision nibble = 0.
                bad_id = bytes([0x01, 0x18])
                self._stamp(
                    address_7bit, register, "read", b"", bad_id, "wrong_id_injected"
                )
                return bad_id

            # Unreachable if FaultKind is exhaustive; pass through as safety.
            pass

        # Pass-through — route to inner bus.
        try:
            result = self._inner.read_register(address_7bit, register, length)
            self._stamp(address_7bit, register, "read", b"", result, "ok")
            return result
        except BusNackError as exc:
            self._stamp(address_7bit, register, "read", b"", b"", "nack")
            raise
        except Exception as exc:
            self._stamp(address_7bit, register, "read", b"", b"", f"error:{type(exc).__name__}")
            raise

    def write_register(self, address_7bit: int, register: int, payload: bytes) -> None:
        if self._should_fault("write", register):
            kind = self._spec.kind
            if kind == "nack":
                self._stamp(address_7bit, register, "write", payload, b"", "nack_injected")
                raise BusNackError(
                    f"FaultBus: injected NACK on write of register {register:#04x}"
                )
            # Other fault kinds don't intercept writes in the current spec.

        try:
            self._inner.write_register(address_7bit, register, payload)
            self._stamp(address_7bit, register, "write", payload, b"", "ok")
        except BusNackError:
            self._stamp(address_7bit, register, "write", payload, b"", "nack")
            raise
        except Exception as exc:
            self._stamp(address_7bit, register, "write", payload, b"", f"error:{type(exc).__name__}")
            raise
