"""
TMP117 virtual device model.

Implements the selected profile:
  - One-shot conversion, averaging disabled, seven-bit address 0x48.
  - Fixture initialized in shutdown (configuration 0x0600) at construction.
  - State machine: shutdown → converting → ready → shutdown (F08).
  - Default completion delay: 15 500 µs (SNOSD82D p6, F09 — typical).

Source references: TI SNOSD82D Rev. D.
  F03  p25       — temperature 0x00, configuration 0x01, device-ID 0x0F.
  F04  p26 §7.6.2 — signed 16-bit two's-complement, 1/128 °C per LSB.
  F05  p27       — Data_Ready bit 13; MOD bits 11:10; AVG bits 6:5.
  F06  p27       — MOD 01 = shutdown; MOD 11 = one-shot; AVG 00 = none.
  F07  p27       — reading configuration OR temperature clears Data_Ready.
  F08  pp14–15 §7.4.3 — one-shot completes then returns to shutdown.
  F09  p6        — single conversion: 13 ms min, 15.5 ms typical, 17.5 ms max.
  F10  p32       — device-ID lower 12 bits = 0x117; upper 4 bits = revision.

DRIFT policies (not vendor facts):
  - virtual_conversion_us: 15 500 µs (typical from F09; DRIFT simulator choice).
  - Unsupported registers/modes return UnsupportedOperation; this is a simulator
    policy, not a claim about hardware NACK behavior.
  - State and clock reset between independent scenarios via reset_fixture().
"""

from __future__ import annotations

import dataclasses
import enum
from typing import Sequence

from drift.interfaces import (
    AddressError,
    TraceEvent,
    UnsupportedProfile,
    validate_7bit_address,
)


# ---------------------------------------------------------------------------
# Register addresses — F03, SNOSD82D p25
# ---------------------------------------------------------------------------
_REG_TEMPERATURE: int = 0x00    # Temperature result (read-only from driver)
_REG_CONFIGURATION: int = 0x01  # Configuration (read/write)
_REG_DEVICE_ID: int = 0x0F      # Device identity (read-only)

# ---------------------------------------------------------------------------
# Configuration bit constants — F05/F06, SNOSD82D p27
# ---------------------------------------------------------------------------
_DATA_READY_BIT: int = 0x2000   # bit 13 — conversion complete
_MOD_MASK: int = 0x0C00         # bits 11:10 — operating mode
_MOD_SHUTDOWN: int = 0x0400     # MOD = 01 — shutdown
_MOD_ONE_SHOT: int = 0x0C00     # MOD = 11 — one-shot
_AVG_MASK: int = 0x0060         # bits 6:5 — averaging

# Selected configuration words — derived from F05/F06, confirmed in contract.
_CONFIG_SHUTDOWN: int = 0x0600  # shutdown, AVG=00 (DRIFT initialized fixture)
_CONFIG_ONE_SHOT_ACTIVE: int = 0x0E00  # one-shot in progress, AVG=00
_CONFIG_READY: int = 0x2600     # Data_Ready set, MOD=shutdown, AVG=00 (F07/F08)
_CONFIG_AFTER_READY_READ: int = 0x0600  # Data_Ready cleared after config read (F07)

# Device-ID register value: part 0x117, revision 0 → 0x0117 — F10
_DEVICE_ID_WORD: int = 0x0117

# Conversion completion delay — DRIFT policy using F09 typical value.
_DEFAULT_CONVERSION_US: int = 15_500


# ---------------------------------------------------------------------------
# Simulator state machine
# ---------------------------------------------------------------------------

class _State(enum.Enum):
    SHUTDOWN = "shutdown"
    CONVERTING = "converting"
    READY = "ready"


class UnsupportedOperation(UnsupportedProfile):
    """
    Virtual model received a register access that is outside the selected
    profile.  This is a simulator policy, not a hardware NACK.
    """


# ---------------------------------------------------------------------------
# Trace accumulator (mutable during a run; exposed as immutable tuple)
# ---------------------------------------------------------------------------

class _TraceAccumulator:
    """Collects TraceEvent instances during one scenario run."""

    def __init__(self) -> None:
        self._events: list[TraceEvent] = []

    def record(
        self,
        virtual_time_us: int,
        address_7bit: int,
        register: int,
        operation: str,
        sent_bytes: bytes,
        received_bytes: bytes,
        outcome: str,
        fact_ids: tuple[str, ...],
    ) -> None:
        event = TraceEvent(
            sequence=len(self._events),
            virtual_time_us=virtual_time_us,
            address_7bit=address_7bit,
            register=register,
            operation=operation,
            sent_bytes=sent_bytes,
            received_bytes=received_bytes,
            outcome=outcome,
            fact_ids=fact_ids,
        )
        self._events.append(event)

    @property
    def events(self) -> tuple[TraceEvent, ...]:
        """Return an immutable snapshot of the accumulated trace."""
        return tuple(self._events)


# ---------------------------------------------------------------------------
# Virtual TMP117 model
# ---------------------------------------------------------------------------

class TMP117VirtualDevice:
    """
    Virtual TMP117 model for the selected one-shot profile.

    The device starts initialized in shutdown (0x0600).  A one-shot write
    transitions to converting; after ``conversion_us`` virtual microseconds
    the conversion completes: Data_Ready sets and the mode reverts to shutdown
    (F07/F08).

    Reading the configuration register while Data_Ready is set returns the
    ready snapshot (0x2600) and clears Data_Ready (F07).
    Reading the temperature register returns the sampled raw word and clears
    Data_Ready (F07).

    The virtual clock is external; this model queries it via ``clock.now_us()``.
    No real sleeps; time advances only when the caller advances the clock.

    Parameters
    ----------
    clock:
        A Clock implementation (typically VirtualClock).
    temperature_raw:
        16-bit unsigned raw temperature word (MSB-first encoding, 1/128 °C/LSB).
        Default 0x0C80 = 25.0 °C (3200 counts × 1/128).
    conversion_us:
        Virtual microseconds from one-shot write until Data_Ready is set.
        Default 15 500 µs (F09 typical; DRIFT policy).
    """

    def __init__(
        self,
        clock,            # Clock protocol — avoid circular import with annotation
        temperature_raw: int = 0x0C80,
        conversion_us: int = _DEFAULT_CONVERSION_US,
    ) -> None:
        self._clock = clock
        self._temperature_raw = temperature_raw
        self._conversion_us = conversion_us

        # Mutable device state
        self._state: _State = _State.SHUTDOWN
        self._config_word: int = _CONFIG_SHUTDOWN
        self._data_ready: bool = False
        self._conversion_deadline_us: int = 0

        # Trace for the current scenario
        self._trace = _TraceAccumulator()

    # ------------------------------------------------------------------
    # State management
    # ------------------------------------------------------------------

    def reset_fixture(self) -> None:
        """
        Reset all mutable state to the declared initialized-shutdown fixture.

        Call between independent scenario runs to enforce fresh state.
        """
        self._state = _State.SHUTDOWN
        self._config_word = _CONFIG_SHUTDOWN
        self._data_ready = False
        self._conversion_deadline_us = 0
        self._trace = _TraceAccumulator()

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _tick(self) -> None:
        """
        Advance internal state based on current virtual time.

        If a conversion is in progress and the deadline has been reached,
        transition to READY and set Data_Ready (F07/F08).
        """
        if self._state is _State.CONVERTING:
            if self._clock.now_us() >= self._conversion_deadline_us:
                self._state = _State.READY
                self._data_ready = True
                self._config_word = _CONFIG_READY

    def _current_config_snapshot(self) -> int:
        """Return current configuration word including Data_Ready bit."""
        if self._data_ready:
            return _CONFIG_READY
        # During conversion the MOD bits remain one-shot; no Data_Ready.
        if self._state is _State.CONVERTING:
            return _CONFIG_ONE_SHOT_ACTIVE
        return _CONFIG_SHUTDOWN

    # ------------------------------------------------------------------
    # Register access — called by VirtualDeviceBus
    # ------------------------------------------------------------------

    def read_register(self, register: int) -> bytes:
        """
        Process a register read from the bus adapter.

        Returns 2 bytes (all TMP117 registers are 16-bit, F02).
        """
        self._tick()
        now = self._clock.now_us()

        if register == _REG_DEVICE_ID:
            word = _DEVICE_ID_WORD
            result = word.to_bytes(2, "big")
            self._trace.record(
                now, 0x48, register, "read",
                b"", result, "ok", ("F03", "F10"),
            )
            return result

        if register == _REG_CONFIGURATION:
            word = self._current_config_snapshot()
            result = word.to_bytes(2, "big")
            # Reading configuration always clears Data_Ready (F07).
            if self._data_ready:
                self._data_ready = False
                self._config_word = _CONFIG_AFTER_READY_READ
                self._state = _State.SHUTDOWN
            self._trace.record(
                now, 0x48, register, "read",
                b"", result, "ok", ("F05", "F06", "F07"),
            )
            return result

        if register == _REG_TEMPERATURE:
            # Temperature read returns the sampled raw word.
            # If Data_Ready is set, clear it (F07).
            ready_now = self._data_ready
            raw_word = self._temperature_raw if ready_now else 0x8000
            result = raw_word.to_bytes(2, "big")
            if ready_now:
                self._data_ready = False
                self._config_word = _CONFIG_AFTER_READY_READ
                self._state = _State.SHUTDOWN
            self._trace.record(
                now, 0x48, register, "read",
                b"", result, "ok", ("F03", "F04", "F07"),
            )
            return result

        # Any other register is outside the selected profile.
        self._trace.record(
            now, 0x48, register, "read",
            b"", b"", "unsupported", (),
        )
        raise UnsupportedOperation(
            f"TMP117 virtual model: read of register {register:#04x} is outside "
            f"the selected profile (selected profile: one-shot, 0x48)"
        )

    def write_register(self, register: int, payload: bytes) -> None:
        """
        Process a register write from the bus adapter.
        """
        self._tick()
        now = self._clock.now_us()

        if register == _REG_CONFIGURATION:
            word = (payload[0] << 8) | payload[1]
            mod_bits = word & _MOD_MASK
            avg_bits = word & _AVG_MASK

            # Only MOD=shutdown and MOD=one-shot with AVG=00 are supported.
            if avg_bits != 0x0000:
                self._trace.record(
                    now, 0x48, register, "write",
                    payload, b"", "unsupported", ("F06",),
                )
                raise UnsupportedOperation(
                    f"TMP117 virtual model: averaging mode {avg_bits:#06x} is not "
                    f"supported in the selected profile (AVG must be 00)"
                )

            if mod_bits == _MOD_SHUTDOWN:
                self._state = _State.SHUTDOWN
                self._config_word = _CONFIG_SHUTDOWN
                self._data_ready = False
                self._trace.record(
                    now, 0x48, register, "write",
                    payload, b"", "ok", ("F05", "F06"),
                )
                return

            if mod_bits == _MOD_ONE_SHOT:
                self._state = _State.CONVERTING
                self._data_ready = False
                self._conversion_deadline_us = (
                    self._clock.now_us() + self._conversion_us
                )
                self._config_word = _CONFIG_ONE_SHOT_ACTIVE
                self._trace.record(
                    now, 0x48, register, "write",
                    payload, b"", "ok", ("F05", "F06", "F08", "F09"),
                )
                return

            # MOD=00 (continuous) and MOD=10 are not in the selected profile.
            self._trace.record(
                now, 0x48, register, "write",
                payload, b"", "unsupported", ("F06",),
            )
            raise UnsupportedOperation(
                f"TMP117 virtual model: MOD bits {mod_bits:#06x} are outside the "
                f"selected profile (supported: MOD=shutdown 0x0400, MOD=one-shot 0x0C00)"
            )

        # Any other register write is outside the selected profile.
        self._trace.record(
            now, 0x48, register, "write",
            payload, b"", "unsupported", (),
        )
        raise UnsupportedOperation(
            f"TMP117 virtual model: write to register {register:#04x} is outside "
            f"the selected profile"
        )

    # ------------------------------------------------------------------
    # Trace access (immutable; cannot mutate device state)
    # ------------------------------------------------------------------

    @property
    def trace(self) -> tuple[TraceEvent, ...]:
        """
        Return an immutable snapshot of the trace for the current run.

        Inspecting this tuple cannot perform a bus read or mutate device state.
        """
        return self._trace.events
