"""
BME280 virtual device model — temperature-only forced-mode profile.

Implements the selected profile:
  - Forced mode, osrs_t=x1, osrs_p=skipped, osrs_h=skipped, filter off.
  - Seven-bit I2C address 0x76 (SDO=GND, F02).
  - Fixture initialized in sleep_after_nvm_copy (status bit3=0) at construction.
  - State machine: sleep → measuring → sleep (forced mode F06/F13).
  - Default completion delay: 3 600 µs (DRIFT policy, above 3.55 ms max, F12).

Source references: Bosch BST-BME280-DS001-24 Rev. 1.24.
  F01  p27  §5.4.1    — chip ID register 0xD0 returns 0x60.
  F02  p32  §6.2      — SDO=GND selects 0x76.
  F03  p24  §4.2.2    — dig_T1 unsigned short; dig_T2/T3 signed short; LSB at
                         lower address (little-endian); T1 at 0x88/0x89,
                         T2 at 0x8A/0x8B, T3 at 0x8C/0x8D.
  F04  pp25,31 §5.4.8 — raw 20-bit unsigned: bits[19:12] at 0xFA, bits[11:4]
                         at 0xFB, bits[3:0] at 0xFC[7:4].
  F06  p29  §5.4.5    — mode[1:0] in ctrl_meas 0xF4 bits[1:0]: 00=sleep, 01=forced.
  F07  p28  §5.4.4    — status 0xF3 bit3=measuring (1=running, 0=complete).
  F08  p29  §5.4.5    — osrs_t[2:0] in ctrl_meas bits[7:5]: 001=x1.
  F12  p51  §9.1      — T×1, P/H skipped: typical 3.0 ms, max 3.55 ms.
  F13  p15  §3.3.3    — forced mode: one measurement, then return to sleep.

DRIFT policies (not vendor facts):
  - virtual_conversion_us: 3 600 µs (DRIFT policy, above 3.55 ms max per F12).
  - Fixture initial state: sleep_after_nvm_copy (status bit3=0 before forced write).
  - Unsupported registers/modes raise UnsupportedOperation.
  - State and time reset via reset_fixture() between independent scenarios.

Important: after a forced write the status register bit3 (measuring) is SET
(conversion in progress).  It clears when the conversion result is transferred
to the data registers (F07).  The driver must advance the clock before its
first status read to avoid accepting the pre-write cleared state as completion.
"""

from __future__ import annotations

import dataclasses
import enum
import struct

from drift.interfaces import (
    TraceEvent,
    UnsupportedProfile,
)


# ---------------------------------------------------------------------------
# Register addresses
# ---------------------------------------------------------------------------
_REG_ID: int = 0xD0           # Chip ID — F01
_REG_CALIB_T: int = 0x88      # Six calibration bytes dig_T1/T2/T3 — F03
_REG_STATUS: int = 0xF3       # Status register — F07
_REG_CTRL_MEAS: int = 0xF4    # Measurement control — F06/F08
_REG_TEMP_MSB: int = 0xFA     # Three raw temperature bytes — F04

# ---------------------------------------------------------------------------
# Identity
# ---------------------------------------------------------------------------
_CHIP_ID: int = 0x60           # BME280 mass-production chip ID — F01

# ---------------------------------------------------------------------------
# Status register bit masks — F07
# ---------------------------------------------------------------------------
_STATUS_MEASURING: int = 0x08  # bit3: set while conversion running

# ---------------------------------------------------------------------------
# ctrl_meas values — F06/F08
# ---------------------------------------------------------------------------
_CTRL_MEAS_SLEEP: int = 0x00   # mode=00, all oversampling=000
_CTRL_MEAS_FORCED_MASK: int = 0x03  # bits[1:0] — 01 or 10 = forced
_CTRL_MEAS_OSRS_T_MASK: int = 0xE0  # bits[7:5] — osrs_t

# Expected ctrl_meas for selected profile: osrs_t=001, osrs_p=000, mode=01 → 0x21
_CTRL_MEAS_FORCED_EXPECTED: int = 0x21

# ---------------------------------------------------------------------------
# Default calibration — populated in reset_fixture() from constructor arg.
# Default matches the test fixture: dig_T1=27504, dig_T2=26435, dig_T3=-1000.
# Bytes: 70 6B 43 67 18 FC (LSB first per F03).
# ---------------------------------------------------------------------------
_DEFAULT_CALIB_T: bytes = bytes([0x70, 0x6B, 0x43, 0x67, 0x18, 0xFC])

# Default raw temperature: 25.08 °C (adc_T=519888)
_DEFAULT_TEMP_RAW: bytes = bytes([0x7E, 0xED, 0x00])

# DRIFT policy: conversion time 3600 µs (above 3.55 ms max, F12)
_DEFAULT_CONVERSION_US: int = 3_600


# ---------------------------------------------------------------------------
# Simulator state machine
# ---------------------------------------------------------------------------

class _State(enum.Enum):
    SLEEP = "sleep"
    MEASURING = "measuring"


class UnsupportedOperation(UnsupportedProfile):
    """
    Virtual model received a register access outside the selected profile.
    This is a simulator policy, not a hardware NACK.
    """


# ---------------------------------------------------------------------------
# Trace accumulator
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
# Virtual BME280 model
# ---------------------------------------------------------------------------

class BME280VirtualDevice:
    """
    Virtual BME280 model for the selected temperature-only forced-mode profile.

    The device starts in sleep_after_nvm_copy with status bit3=0 (not measuring).
    A forced-mode write to ctrl_meas (0x21) triggers one conversion:
      - Status bit3 immediately becomes 1 (measuring).
      - After virtual_conversion_us, bit3 clears and the result is available
        in the raw temperature registers 0xFA–0xFC.
      - The device returns to sleep mode (ctrl_meas mode bits → 00, F13).

    Status register (0xF3):
      - bit3=1: conversion in progress.
      - bit3=0: sleep or conversion complete.
    The driver must read status AFTER advancing the clock; it must not accept
    the pre-write bit3=0 as a completion signal.

    Calibration register (0x88, 6 bytes):
      Returns dig_T1/T2/T3 in little-endian format (F03).
      These bytes are fixed for the lifetime of the fixture.

    Temperature registers (0xFA–0xFC, 3 bytes):
      Before any conversion completes, returns the reset sentinel 0x800000 >> 4
      encoded as three bytes (all-zero xlsb nibble).  After completion, returns
      the latched raw bytes.  Retained across status reads; only reset by
      reset_fixture().

    The virtual clock is external; this model queries it via clock.now_us().
    No real sleeps; time advances only when the caller advances the clock.

    Parameters
    ----------
    clock:
        A Clock implementation (typically VirtualClock).
    calib_bytes:
        6 calibration bytes (dig_T1/T2/T3, LSB-first, per F03).
        Default: bytes matching dig_T1=27504, dig_T2=26435, dig_T3=-1000.
    temp_raw_bytes:
        3 raw temperature bytes (0xFA/0xFB/0xFC encoding, per F04).
        Default: bytes for 25.08 °C.
    conversion_us:
        Virtual µs from forced write until conversion complete.
        Default 3 600 µs (DRIFT policy, above 3.55 ms max, F12).
    address_7bit:
        Device address for trace events (default 0x76).
    """

    def __init__(
        self,
        clock,
        calib_bytes: bytes = _DEFAULT_CALIB_T,
        temp_raw_bytes: bytes = _DEFAULT_TEMP_RAW,
        conversion_us: int = _DEFAULT_CONVERSION_US,
        address_7bit: int = 0x76,
    ) -> None:
        if len(calib_bytes) != 6:
            raise ValueError(
                f"calib_bytes must be 6 bytes; got {len(calib_bytes)}"
            )
        if len(temp_raw_bytes) != 3:
            raise ValueError(
                f"temp_raw_bytes must be 3 bytes; got {len(temp_raw_bytes)}"
            )
        self._clock = clock
        self._calib_bytes = bytes(calib_bytes)
        self._temp_raw_bytes = bytes(temp_raw_bytes)
        self._conversion_us = conversion_us
        self._address = address_7bit

        # Mutable device state — reset to fixture in __init__ and reset_fixture()
        self._state: _State = _State.SLEEP
        self._conversion_deadline_us: int = 0
        # Latched temperature bytes — reset sentinel until first completion.
        # Reset sentinel is 0x80000 left-shifted, i.e. 0x80 00 00 per F04.
        self._latched_temp: bytes = bytes([0x80, 0x00, 0x00])
        self._result_ready: bool = False

        self._trace = _TraceAccumulator()

    # ------------------------------------------------------------------
    # State management
    # ------------------------------------------------------------------

    def reset_fixture(self) -> None:
        """
        Reset all mutable state to the declared sleep_after_nvm_copy fixture.

        Call between independent scenario runs to enforce fresh state.
        """
        self._state = _State.SLEEP
        self._conversion_deadline_us = 0
        self._latched_temp = bytes([0x80, 0x00, 0x00])
        self._result_ready = False
        self._trace = _TraceAccumulator()

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _tick(self) -> None:
        """
        Advance internal state based on current virtual time.

        If a conversion is in progress and the deadline has been reached,
        transition to SLEEP: latch the temperature result and clear
        the measuring bit (status bit3=0, F07/F13).
        """
        if self._state is _State.MEASURING:
            if self._clock.now_us() >= self._conversion_deadline_us:
                self._state = _State.SLEEP
                self._latched_temp = self._temp_raw_bytes
                self._result_ready = True

    def _status_byte(self) -> int:
        """
        Return the status register byte reflecting current state.

        bit3=1 when measuring (conversion in progress) — F07.
        bit3=0 when sleeping or complete.
        """
        self._tick()
        if self._state is _State.MEASURING:
            return _STATUS_MEASURING  # 0x08
        return 0x00

    # ------------------------------------------------------------------
    # Register access — called by VirtualDeviceBus
    # ------------------------------------------------------------------

    def read_register(self, register: int) -> bytes:
        """
        Process a register read from the bus adapter.

        Supported registers:
          0xD0 — chip ID (1 byte)
          0x88 — calibration T (6 bytes)
          0xF3 — status (1 byte)
          0xFA — raw temperature (3 bytes)
        """
        self._tick()
        now = self._clock.now_us()

        if register == _REG_ID:
            result = bytes([_CHIP_ID])
            self._trace.record(
                now, self._address, register, "read",
                b"", result, "ok", ("F01",),
            )
            return result

        if register == _REG_CALIB_T:
            # Return the 6-byte calibration block (dig_T1/T2/T3, F03).
            result = self._calib_bytes
            self._trace.record(
                now, self._address, register, "read",
                b"", result, "ok", ("F03",),
            )
            return result

        if register == _REG_STATUS:
            # Return 1-byte status.  bit3=measuring (F07).
            # The tick was already called at the start of this method.
            status = self._status_byte()
            result = bytes([status])
            self._trace.record(
                now, self._address, register, "read",
                b"", result, "ok", ("F07",),
            )
            return result

        if register == _REG_TEMP_MSB:
            # Return 3 bytes: 0xFA (msb), 0xFB (lsb), 0xFC (xlsb) — F04.
            # Returns reset sentinel before first completion.
            result = self._latched_temp
            self._trace.record(
                now, self._address, register, "read",
                b"", result, "ok", ("F04",),
            )
            return result

        # Outside the selected profile.
        self._trace.record(
            now, self._address, register, "read",
            b"", b"", "unsupported", (),
        )
        raise UnsupportedOperation(
            f"BME280 virtual model: read of register {register:#04x} is outside "
            f"the selected temperature-only forced-mode profile"
        )

    def write_register(self, register: int, payload: bytes) -> None:
        """
        Process a register write from the bus adapter.

        Only ctrl_meas (0xF4) with the forced-mode byte 0x21 is supported.
        Writing 0x00 (sleep) is also accepted.
        """
        self._tick()
        now = self._clock.now_us()

        if register == _REG_CTRL_MEAS:
            if len(payload) != 1:
                self._trace.record(
                    now, self._address, register, "write",
                    payload, b"", "unsupported", ("F06",),
                )
                raise UnsupportedOperation(
                    f"BME280 virtual model: ctrl_meas write payload must be 1 byte; "
                    f"got {len(payload)}"
                )
            byte = payload[0]
            mode_bits = byte & _CTRL_MEAS_FORCED_MASK

            if mode_bits == 0x00:
                # Sleep write — accepted; returns to sleep.
                self._state = _State.SLEEP
                self._trace.record(
                    now, self._address, register, "write",
                    payload, b"", "ok", ("F06", "F13"),
                )
                return

            if mode_bits in (0x01, 0x02):
                # Forced mode (01 or 10 per F06).
                # Only support the selected profile: osrs_t=001 (0x21).
                osrs_t = (byte & _CTRL_MEAS_OSRS_T_MASK) >> 5
                if osrs_t != 0b001:
                    self._trace.record(
                        now, self._address, register, "write",
                        payload, b"", "unsupported", ("F08",),
                    )
                    raise UnsupportedOperation(
                        f"BME280 virtual model: osrs_t={osrs_t} is not supported; "
                        f"selected profile requires osrs_t=001 (x1 oversampling, F08)"
                    )
                # Start conversion: status bit3 = 1, schedule completion.
                self._state = _State.MEASURING
                self._result_ready = False
                self._conversion_deadline_us = (
                    self._clock.now_us() + self._conversion_us
                )
                self._trace.record(
                    now, self._address, register, "write",
                    payload, b"", "ok", ("F06", "F08", "F12", "F13"),
                )
                return

            # mode_bits == 0x03 = normal mode — outside selected profile.
            self._trace.record(
                now, self._address, register, "write",
                payload, b"", "unsupported", ("F06",),
            )
            raise UnsupportedOperation(
                f"BME280 virtual model: mode bits {mode_bits:#04x} are outside the "
                f"selected profile (forced=01/10 only, F06)"
            )

        # Any other register write is outside the selected profile.
        self._trace.record(
            now, self._address, register, "write",
            payload, b"", "unsupported", (),
        )
        raise UnsupportedOperation(
            f"BME280 virtual model: write to register {register:#04x} is outside "
            f"the selected temperature-only forced-mode profile"
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
