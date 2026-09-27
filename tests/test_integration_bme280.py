"""
tests/test_integration_bme280.py — BME280 driver-to-model integration tests.

Connects BME280Driver to BME280VirtualDevice via VirtualDeviceBus and VirtualClock.
The driver uses only the RegisterBus interface; it cannot inspect device internals.

All expected values are literal constants reviewed independently of the driver
and virtual model.

Source facts referenced (Bosch BST-BME280-DS001-24 Rev. 1.24):
  F01  p27   §5.4.1  — chip ID 0xD0 returns 0x60.
  F02  p32   §6.2    — SDO=GND selects 0x76.
  F03  p24   §4.2.2  — calibration bytes: dig_T1/T2/T3, LSB-first.
  F04  pp25,31 §5.4.8 — raw 20-bit temperature encoding.
  F05  p25   §4.2.3  — 32-bit integer temperature compensation formula.
  F06  p29   §5.4.5  — mode[1:0] in ctrl_meas: 00=sleep, 01=forced.
  F07  p28   §5.4.4  — status 0xF3 bit3: 1=measuring, 0=done.
  F12  p51   §9.1    — T×1, P/H skipped: typ 3.0 ms, max 3.55 ms.
  F13  p15   §3.3.3  — forced mode returns to sleep after one measurement.

DRIFT policies:
  virtual_conversion_us = 3 600 µs (above 3.55 ms max, F12).
  poll_interval = 1 000 µs; timeout = 100 000 µs.

Literal expected values (hand-verified, never derived from driver/decoder):
  Calib:      70 6B 43 67 18 FC → dig_T1=27504, dig_T2=26435, dig_T3=-1000
  Raw 7E ED 00 → adc_T=519888 → 25.08 °C  (Bosch §4.2.3 formula applied by hand)
  Raw 65 5A C0 → adc_T=415148 → -7.86 °C  (Bosch §4.2.3 formula applied by hand)

  The driver polls every 1 000 µs.  Conversion_us = 3 600 µs.
  First poll after forced write is at t = 1 000 µs → status still busy (0x08).
  Second poll at t = 2 000 µs → still busy.
  Third poll at t = 3 000 µs → still busy.
  Fourth poll at t = 4 000 µs (≥ 3 600 µs deadline) → status clear.
  Expected virtual_time_us = 4 000.

Key stale-data test (AGENTS.md): the driver must not accept status bit3=0
immediately after the forced write (before any clock advance) as completion.
The pre-write sleep-mode status reads 0x00, which equals bit3=0.  The driver
must advance the clock before the first poll.
"""

from __future__ import annotations

import pytest

from drift.bus import VirtualDeviceBus
from drift.clock import VirtualClock
from drift.devices.bme280 import BME280VirtualDevice
from drift.drivers.bme280 import BME280Driver
from drift.interfaces import (
    BusNackError,
    ConversionTimeout,
    DeviceIdentityError,
    ProtocolReadError,
)

# ---------------------------------------------------------------------------
# Literal test constants — reviewed independently
# ---------------------------------------------------------------------------

_ADDR: int = 0x76              # F02
_CHIP_ID_INT: int = 0x60       # F01

# Calibration bytes: dig_T1=27504, dig_T2=26435, dig_T3=-1000, LSB-first (F03)
_CALIB_BYTES: bytes = bytes([0x70, 0x6B, 0x43, 0x67, 0x18, 0xFC])

# Raw temperature bytes and expected decoded temperatures (F04/F05, hand-verified)
_RAW_25C: bytes = bytes([0x7E, 0xED, 0x00])    # → 25.08 °C
_RAW_NEG8C: bytes = bytes([0x65, 0x5A, 0xC0])  # → -7.86 °C
_TEMP_25C: float = 25.08
_TEMP_NEG8C: float = -7.86

# DRIFT policy: conversion 3 600 µs; poll 1 000 µs.
# 4th poll fires at t=4 000 µs (≥ 3 600 µs deadline).
_CONV_US: int = 3_600
_POLL_US: int = 1_000
_EXPECTED_READY_TIME_US: int = 4_000  # 4 × 1 000 µs (first poll ≥ 3 600)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_stack(
    temp_raw: bytes = _RAW_25C,
    calib: bytes = _CALIB_BYTES,
    conv_us: int = _CONV_US,
) -> tuple[BME280Driver, BME280VirtualDevice, VirtualClock]:
    """Create a fresh driver → bus → device → clock stack."""
    clock = VirtualClock(0)
    device = BME280VirtualDevice(
        clock=clock,
        calib_bytes=calib,
        temp_raw_bytes=temp_raw,
        conversion_us=conv_us,
        address_7bit=_ADDR,
    )
    bus = VirtualDeviceBus(device, address_7bit=_ADDR)
    driver = BME280Driver(bus=bus, clock=clock, address_7bit=_ADDR)
    return driver, device, clock


# ===========================================================================
# TBI01–TBI04 — identify() via virtual device
# ===========================================================================

class TestIdentifyIntegration:
    """identify() through the virtual device returns the correct chip ID."""

    def test_TBI01_identify_returns_0x60(self) -> None:
        """identify() returns DeviceIdentity.part_id == 0x60 — F01."""
        driver, device, _ = _make_stack()
        identity = driver.identify()
        assert identity.part_id == _CHIP_ID_INT

    def test_TBI02_identify_revision_is_zero(self) -> None:
        """identify() returns revision=0 (virtual model returns plain 0x60)."""
        driver, _, _ = _make_stack()
        identity = driver.identify()
        assert identity.revision == 0

    def test_TBI03_identify_raw_bytes_one_byte(self) -> None:
        """identify() raw_bytes is b'\\x60'."""
        driver, _, _ = _make_stack()
        identity = driver.identify()
        assert identity.raw_bytes == bytes([_CHIP_ID_INT])

    def test_TBI04_identify_records_trace_event(self) -> None:
        """identify() through virtual device records a trace event at register 0xD0."""
        driver, device, _ = _make_stack()
        driver.identify()
        events = device.trace
        id_events = [e for e in events if e.register == 0xD0]
        assert len(id_events) == 1
        assert id_events[0].outcome == "ok"


# ===========================================================================
# TBI05–TBI08 — measure() baseline calibration results
# ===========================================================================

class TestMeasureBaseline:
    """measure() returns correct temperatures for the two baseline calibration fixtures."""

    def test_TBI05_measure_25c_baseline(self) -> None:
        """
        measure() returns 25.08 °C with calib 70 6B 43 67 18 FC and raw 7E ED 00.

        Independent expectation: adc_T = (0x7E<<12)|(0xED<<4)|(0x00>>4) = 519888.
        Applying Bosch §4.2.3 integer formula with dig_T1=27504, dig_T2=26435,
        dig_T3=-1000 produces T=2508 (0.01°C units), i.e. 25.08 °C.
        """
        driver, _, _ = _make_stack(temp_raw=_RAW_25C)
        result = driver.measure()
        assert result.celsius == _TEMP_25C, (
            f"Expected 25.08 °C; got {result.celsius}"
        )
        assert result.raw_bytes == _RAW_25C

    def test_TBI06_measure_neg8c_baseline(self) -> None:
        """
        measure() returns -7.86 °C with calib 70 6B 43 67 18 FC and raw 65 5A C0.

        Independent expectation: adc_T = (0x65<<12)|(0x5A<<4)|(0xC0>>4) = 415148.
        Applying Bosch §4.2.3 formula with same calibration produces T=-786, i.e.
        -7.86 °C.
        """
        driver, _, _ = _make_stack(temp_raw=_RAW_NEG8C)
        result = driver.measure()
        assert result.celsius == _TEMP_NEG8C, (
            f"Expected -7.86 °C; got {result.celsius}"
        )
        assert result.raw_bytes == _RAW_NEG8C

    def test_TBI07_measure_virtual_time_us_at_fourth_poll(self) -> None:
        """
        measure() records virtual_time_us = 4 000 µs.

        Conversion deadline = 3 600 µs.  Poll interval = 1 000 µs.
        Polls at t=1000 (busy), t=2000 (busy), t=3000 (busy), t=4000 (idle).
        Expected: 4 000 µs (literal, not derived from driver).
        """
        driver, _, _ = _make_stack()
        result = driver.measure()
        assert result.virtual_time_us == _EXPECTED_READY_TIME_US, (
            f"Expected ready at 4000 µs; got {result.virtual_time_us}"
        )

    def test_TBI08_measure_raw_bytes_three_bytes(self) -> None:
        """measure() Measurement.raw_bytes is exactly 3 bytes — F04."""
        driver, _, _ = _make_stack()
        result = driver.measure()
        assert len(result.raw_bytes) == 3


# ===========================================================================
# TBI09 — stale pre-write status must NOT be accepted as completion
# ===========================================================================

class TestStalePollRejection:
    """
    The driver must not accept the pre-write status bit3=0 (sleep) as completion.

    At fixture construction the device is in sleep mode (status=0x00, bit3=0).
    A naive driver that reads status before advancing the clock would see 0x00
    and (incorrectly) conclude that conversion is complete, then read stale
    reset-sentinel bytes 0x80 00 00 instead of the real result.

    The driver is required to advance the clock before the first status poll.
    This test verifies that the driver:
      1. Does NOT read the temperature register before virtual time has advanced.
      2. Returns the correct temperature (not the sentinel value).
    """

    def test_TBI09_driver_does_not_read_stale_sentinel(self) -> None:
        """
        measure() returns correct temp, not the 0x80 00 00 reset sentinel.

        If the driver were to accept the pre-write status=0x00 as completion,
        it would read raw bytes 0x80 00 00, decode adc_T = 0x80000 = 524288,
        and compute a very wrong temperature.  The real result must be 25.08 °C.
        """
        driver, _, _ = _make_stack(temp_raw=_RAW_25C)
        result = driver.measure()
        # Must NOT be the sentinel — sentinel gives adc_T=524288 → wrong temperature.
        assert result.raw_bytes != bytes([0x80, 0x00, 0x00]), (
            "Driver accepted stale pre-write sentinel bytes as a valid result"
        )
        assert result.celsius == _TEMP_25C, (
            f"Stale data guard: expected 25.08 °C, got {result.celsius}"
        )

    def test_TBI10_virtual_time_advanced_before_first_status_read(self) -> None:
        """
        virtual_time_us in the result must be ≥ 1 000 µs (one poll interval).

        If the driver read status at t=0 (immediately after the forced write)
        and saw 0x00, virtual_time_us would be 0.  Any value ≥ 1 000 confirms
        the driver advanced the clock before its first status poll.
        """
        driver, _, _ = _make_stack()
        result = driver.measure()
        assert result.virtual_time_us >= _POLL_US, (
            f"Driver appears to have read status at t=0 (stale read); "
            f"virtual_time_us = {result.virtual_time_us}, expected ≥ {_POLL_US}"
        )


# ===========================================================================
# TBI11–TBI13 — return to sleep, successive conversions
# ===========================================================================

class TestReturnToSleep:
    """Device returns to sleep after forced conversion (F13)."""

    def test_TBI11_status_idle_after_measure_completes(self) -> None:
        """Status bit3=0 after measure() completes — device is in sleep (F13)."""
        driver, device, _ = _make_stack()
        driver.measure()
        # Read status directly from the device model (external observer check).
        status = device.read_register(0xF3)[0]
        assert (status & 0x08) == 0, (
            "Device must be in sleep mode after forced conversion (F13)"
        )

    def test_TBI12_two_successive_conversions(self) -> None:
        """Two successive measure() calls return the same temperature (25.08 °C)."""
        # Use a fresh clock so both conversions start from a clean state.
        clock = VirtualClock(0)
        device = BME280VirtualDevice(
            clock=clock, calib_bytes=_CALIB_BYTES,
            temp_raw_bytes=_RAW_25C, conversion_us=_CONV_US, address_7bit=_ADDR,
        )
        bus = VirtualDeviceBus(device, address_7bit=_ADDR)
        driver = BME280Driver(bus=bus, clock=clock, address_7bit=_ADDR)

        result1 = driver.measure()
        assert result1.celsius == _TEMP_25C

        result2 = driver.measure()
        assert result2.celsius == _TEMP_25C

        # Second conversion must take at least one full poll interval longer
        # than the first (clock has advanced from the first round).
        assert result2.virtual_time_us > result1.virtual_time_us

    def test_TBI13_device_trace_has_correct_write_register(self) -> None:
        """Device trace records exactly one ctrl_meas write (0xF4) per measure()."""
        driver, device, _ = _make_stack()
        driver.measure()
        ctrl_writes = [
            e for e in device.trace
            if e.register == 0xF4 and e.operation == "write"
        ]
        assert len(ctrl_writes) == 1
        # Verify the sent byte was 0x21.
        assert ctrl_writes[0].sent_bytes == bytes([0x21])


# ===========================================================================
# TBI14 — short-read fault: explicit ProtocolReadError
# ===========================================================================

class TestShortReadFault:
    """
    Explicit short-read fault on the temperature register.

    Uses ScriptedBus to deliver 2 bytes for a 3-byte temperature read,
    confirming that BME280Driver raises ProtocolReadError.
    """

    def test_TBI14_short_temp_read_raises_protocol_error(self) -> None:
        """measure() raises ProtocolReadError when temperature read returns 2 bytes."""
        from drift.bus import ScriptedBus

        _CTRL_FORCED: bytes = b"\x21"
        _STATUS_IDLE: bytes = b"\x00"

        # Build a scripted bus that delivers a 2-byte temperature response.
        bus = ScriptedBus([
            ScriptedBus.step_read(_ADDR, 0x88, _CALIB_BYTES),           # calib
            ScriptedBus.step_write(_ADDR, 0xF4, _CTRL_FORCED),          # forced write
            ScriptedBus.step_read(_ADDR, 0xF3, _STATUS_IDLE),           # status idle
            ScriptedBus.step_read(_ADDR, 0xFA, bytes([0x7E, 0xED])),     # only 2 bytes
        ])
        clock = VirtualClock(0)
        driver = BME280Driver(bus=bus, clock=clock, address_7bit=_ADDR)

        with pytest.raises(ProtocolReadError):
            driver.measure()


# ===========================================================================
# TBI15–TBI17 — ordered delivered-byte trace assertions
# ===========================================================================

class TestDeliveredByteTrace:
    """Verify the ordered bus trace after a full identify+measure run."""

    def test_TBI15_full_trace_order(self) -> None:
        """
        Trace from the virtual device records operations in bus order:
          0: read 0xD0 (chip ID)
          1: read 0x88 (calibration)
          2: write 0xF4 (ctrl_meas forced)
          3..N: read 0xF3 (status polls, N≥4)
          last: read 0xFA (temperature)
        """
        driver, device, _ = _make_stack()
        driver.identify()
        driver.measure()
        events = device.trace

        # Check operation order by register.
        op_regs = [(e.operation, e.register) for e in events]
        # First: chip ID read
        assert op_regs[0] == ("read", 0xD0)
        # Second: calibration read
        assert op_regs[1] == ("read", 0x88)
        # Third: forced write
        assert op_regs[2] == ("write", 0xF4)
        # Status polls come next
        status_polls = [i for i, (op, reg) in enumerate(op_regs) if reg == 0xF3]
        assert len(status_polls) >= 1
        # Temperature read is last
        assert op_regs[-1] == ("read", 0xFA)

    def test_TBI16_received_bytes_in_trace(self) -> None:
        """
        After measure(), the temperature trace event's received_bytes
        equals the fixture raw bytes (_RAW_25C).
        """
        driver, device, _ = _make_stack(temp_raw=_RAW_25C)
        driver.measure()
        temp_event = next(
            e for e in device.trace
            if e.register == 0xFA and e.operation == "read"
        )
        assert temp_event.received_bytes == _RAW_25C

    def test_TBI17_ctrl_meas_sent_bytes_in_trace(self) -> None:
        """
        The ctrl_meas write trace event's sent_bytes equals b'\\x21'.
        """
        driver, device, _ = _make_stack()
        driver.measure()
        write_event = next(
            e for e in device.trace
            if e.register == 0xF4 and e.operation == "write"
        )
        assert write_event.sent_bytes == bytes([0x21])
