"""
tests/test_driver_bme280.py — BME280 temperature-only forced-mode driver tests.

Uses ScriptedBus and StepClock only; no virtual model, no framework runner.
All expected bytes and numeric values are literal constants reviewed
independently of the production driver and compensation helper.

Source facts referenced (Bosch BST-BME280-DS001-24 Rev. 1.24):
  F01  p27   §5.4.1  — chip ID register 0xD0 returns 0x60.
  F02  p32   §6.2    — SDO=GND selects address 0x76.
  F03  p24   §4.2.2  — dig_T1 unsigned, dig_T2/T3 signed, little-endian;
                        six bytes from 0x88.
  F04  pp25,31 §5.4.8 — 20-bit raw: 0xFA[19:12], 0xFB[11:4], 0xFC bits[7:4].
  F05  p25   §4.2.3  — 32-bit integer compensation formula.
  F06  p29   §5.4.5  — ctrl_meas 0xF4 bits[1:0]: forced = 01 or 10.
  F07  p28   §5.4.4  — status 0xF3 bit3 (mask 0x08) = measuring.
  F08  p29   §5.4.5  — osrs_t bits[7:5] = 001 → x1 oversampling.
  F09  p29   §5.4.5  — osrs_p bits[4:2] = 000 → skipped.
  F12  p51   §9.1    — forced, T×1, P/H skipped: typical 3.0 ms, max 3.55 ms.
  F13  p15   §3.3.3  — forced mode returns to sleep after one measurement.

DRIFT policies:
  timeout = 100 000 µs; poll interval = 1 000 µs;
  virtual_conversion_us = 3 600 µs (DRIFT fixture assumption above 3.55 ms max).

Literal constants (reviewed independently of driver/decoder):
  Address:       0x76     (F02)
  Chip ID:       0x60     (F01)
  ctrl_meas:     0x21     (derived_candidates from approved contract: osrs_t=001
                            in bits7:5 → 0x20; osrs_p=000 in bits4:2 → 0x00;
                            forced=01 in bits1:0 → 0x01; combined = 0x21)
  Status busy:   0x08     (bit3 set — F07)
  Status idle:   0x00     (bit3 clear — F07)
  Calib bytes:   70 6B 43 67 18 FC
                   dig_T1 = 0x6B70 = 27504  (unsigned little-endian)
                   dig_T2 = 0x6743 = 26435  (signed positive)
                   dig_T3 = 0xFC18 = -1000  (signed: 64536 - 65536 = -1000)
  Raw 7E ED 00:  adc_T = (0x7E<<12)|(0xED<<4)|(0x00>>4) = 519888 → 25.08 °C
  Raw 65 5A C0:  adc_T = (0x65<<12)|(0x5A<<4)|(0xC0>>4) = 415148 → -7.86 °C
    (Both values hand-verified against the Bosch §4.2.3 integer formula.)
"""

from __future__ import annotations

import pytest

from drift.bus import ScriptedBus, ScriptedBusExhausted
from drift.clock import StepClock
from drift.drivers.bme280 import BME280Driver
from drift.interfaces import (
    BusNackError,
    ConversionTimeout,
    DeviceIdentityError,
    ProtocolReadError,
)

# ---------------------------------------------------------------------------
# Literal test constants — must not be derived from driver or decoder
# ---------------------------------------------------------------------------

_ADDR: int = 0x76              # BME280 address, SDO=GND (F02)

# Register addresses (from contract / datasheet)
_REG_ID: int = 0xD0            # Chip ID register (F01)
_REG_CALIB_T: int = 0x88       # Calibration T1/T2/T3 base address (F03)
_REG_STATUS: int = 0xF3        # Status register (F07)
_REG_CTRL_MEAS: int = 0xF4     # Measurement control (F06)
_REG_TEMP_MSB: int = 0xFA      # Raw temperature MSB (F04)

# Identity bytes
_ID_GOOD: bytes = b"\x60"      # 0x60 — BME280 mass-production (F01)
_ID_BAD: bytes = b"\x58"       # 0x58 — BMP280, wrong part

# ctrl_meas forced value (contract derived_candidates, confirmed 0x21)
_CTRL_MEAS_FORCED: bytes = b"\x21"

# Status register byte values (F07)
_STATUS_BUSY: bytes = b"\x08"  # bit3 set: conversion in progress
_STATUS_IDLE: bytes = b"\x00"  # bit3 clear: conversion complete

# Calibration bytes: dig_T1=27504(0x6B70), dig_T2=26435(0x6743), dig_T3=-1000(0xFC18)
# Layout: LSB first (little-endian), F03
_CALIB_BYTES: bytes = bytes([0x70, 0x6B, 0x43, 0x67, 0x18, 0xFC])

# Raw temperature bytes and expected decoded values (hand-verified, F04/F05)
_RAW_25C: bytes = bytes([0x7E, 0xED, 0x00])   # → 25.08 °C
_RAW_NEG8C: bytes = bytes([0x65, 0x5A, 0xC0]) # → -7.86 °C
_TEMP_25C: float = 25.08
_TEMP_NEG8C: float = -7.86


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_driver(bus: ScriptedBus, clock: StepClock | None = None) -> BME280Driver:
    if clock is None:
        clock = StepClock(0)
    return BME280Driver(bus=bus, clock=clock, address_7bit=_ADDR)


def _make_identify_bus(*, chip_id_bytes: bytes = _ID_GOOD, nack: bool = False) -> ScriptedBus:
    """One-step bus for identify(): read register 0xD0."""
    return ScriptedBus([
        ScriptedBus.step_read(_ADDR, _REG_ID, chip_id_bytes, nack=nack),
    ])


def _make_measure_bus(
    *,
    calib: bytes = _CALIB_BYTES,
    status_sequence: list[bytes],
    temp_raw: bytes = _RAW_25C,
) -> ScriptedBus:
    """
    Build a ScriptedBus for measure():
      step 0: read 6 calib bytes from 0x88
      step 1: write ctrl_meas=0x21 to 0xF4
      steps 2..N: read status 0xF3 (one per entry in status_sequence)
      step N+1: read 3 raw temperature bytes from 0xFA
    """
    steps = [
        ScriptedBus.step_read(_ADDR, _REG_CALIB_T, calib),
        ScriptedBus.step_write(_ADDR, _REG_CTRL_MEAS, _CTRL_MEAS_FORCED),
    ]
    for s in status_sequence:
        steps.append(ScriptedBus.step_read(_ADDR, _REG_STATUS, s))
    steps.append(ScriptedBus.step_read(_ADDR, _REG_TEMP_MSB, temp_raw))
    return ScriptedBus(steps)


# ===========================================================================
# TI01–TI04 — identify()
# ===========================================================================

class TestIdentify:
    """Verify BME280Driver.identify() against scripted bus."""

    def test_TI01_good_chip_id_returns_identity(self) -> None:
        """identify() returns DeviceIdentity with part_id=0x60 for a good device."""
        bus = _make_identify_bus()
        driver = _make_driver(bus)
        identity = driver.identify()
        assert identity.part_id == 0x60
        assert identity.revision == 0
        assert identity.raw_bytes == _ID_GOOD
        bus.assert_exhausted()

    def test_TI02_wrong_chip_id_raises_device_identity_error(self) -> None:
        """identify() raises DeviceIdentityError when chip ID is not 0x60."""
        bus = _make_identify_bus(chip_id_bytes=_ID_BAD)
        driver = _make_driver(bus)
        with pytest.raises(DeviceIdentityError, match="0x60"):
            driver.identify()

    def test_TI03_nack_on_id_read_raises_bus_nack(self) -> None:
        """identify() propagates BusNackError from the bus."""
        bus = _make_identify_bus(nack=True)
        driver = _make_driver(bus)
        with pytest.raises(BusNackError):
            driver.identify()

    def test_TI04_short_read_on_id_raises_protocol_error(self) -> None:
        """identify() raises ProtocolReadError when read returns wrong length."""
        # ScriptedBus raises ProtocolReadError when scripted payload length
        # does not match the requested length.
        bus = ScriptedBus([
            ScriptedBus.step_read(_ADDR, _REG_ID, b"\x60\x00"),  # 2 bytes, driver asks 1
        ])
        driver = _make_driver(bus)
        with pytest.raises(ProtocolReadError):
            driver.identify()


# ===========================================================================
# TM01–TM12 — measure()
# ===========================================================================

class TestMeasure:
    """Verify BME280Driver.measure() against scripted bus."""

    def test_TM01_ready_after_one_poll_25c(self) -> None:
        """measure() returns 25.08 °C when status clears after one poll."""
        bus = _make_measure_bus(
            status_sequence=[_STATUS_IDLE],
            temp_raw=_RAW_25C,
        )
        clock = StepClock(0)
        driver = _make_driver(bus, clock)
        result = driver.measure()
        assert result.celsius == _TEMP_25C
        assert result.raw_bytes == _RAW_25C
        bus.assert_exhausted()

    def test_TM02_ready_after_one_poll_neg8c(self) -> None:
        """measure() returns -7.86 °C when status clears after one poll."""
        bus = _make_measure_bus(
            status_sequence=[_STATUS_IDLE],
            temp_raw=_RAW_NEG8C,
        )
        clock = StepClock(0)
        driver = _make_driver(bus, clock)
        result = driver.measure()
        assert result.celsius == _TEMP_NEG8C
        assert result.raw_bytes == _RAW_NEG8C
        bus.assert_exhausted()

    def test_TM03_busy_then_idle_two_polls(self) -> None:
        """measure() waits through one busy poll before reading temperature."""
        bus = _make_measure_bus(
            status_sequence=[_STATUS_BUSY, _STATUS_IDLE],
            temp_raw=_RAW_25C,
        )
        clock = StepClock(0)
        driver = _make_driver(bus, clock)
        result = driver.measure()
        assert result.celsius == _TEMP_25C
        # Two poll advances: virtual time should be 2000 µs
        assert result.virtual_time_us == 2000
        bus.assert_exhausted()

    def test_TM04_virtual_time_recorded_at_idle_observation(self) -> None:
        """virtual_time_us in result equals clock reading when measuring cleared."""
        bus = _make_measure_bus(
            status_sequence=[_STATUS_BUSY, _STATUS_BUSY, _STATUS_IDLE],
            temp_raw=_RAW_25C,
        )
        clock = StepClock(0)
        driver = _make_driver(bus, clock)
        result = driver.measure()
        # Three poll advances × 1000 µs each = 3000 µs
        assert result.virtual_time_us == 3000
        bus.assert_exhausted()

    def test_TM05_immediate_idle_after_write_is_not_stale(self) -> None:
        """
        A single poll advance must occur before the first status check.

        The driver must not accept a pre-write idle status as a completed
        conversion; it advances the clock before the first read so the status
        read happens after at least one poll_interval.
        """
        bus = _make_measure_bus(
            status_sequence=[_STATUS_IDLE],
            temp_raw=_RAW_25C,
        )
        clock = StepClock(0)
        driver = _make_driver(bus, clock)
        result = driver.measure()
        # Clock must have advanced at least one poll interval before first status read
        assert result.virtual_time_us >= 1000
        bus.assert_exhausted()

    def test_TM06_timeout_raises_conversion_timeout(self) -> None:
        """measure() raises ConversionTimeout when measuring never clears."""
        # Provide enough busy responses to exceed the timeout window.
        # With timeout=5000 µs and poll_interval=1000 µs, max 7 polls.
        bus = ScriptedBus(
            [ScriptedBus.step_read(_ADDR, _REG_CALIB_T, _CALIB_BYTES),
             ScriptedBus.step_write(_ADDR, _REG_CTRL_MEAS, _CTRL_MEAS_FORCED)]
            + [ScriptedBus.step_read(_ADDR, _REG_STATUS, _STATUS_BUSY)] * 7
        )
        clock = StepClock(0)
        driver = _make_driver(bus, clock)
        with pytest.raises(ConversionTimeout):
            driver.measure(timeout_us=5000)

    def test_TM07_nack_on_calib_read_raises_bus_nack(self) -> None:
        """measure() propagates BusNackError from calibration read."""
        bus = ScriptedBus([
            ScriptedBus.step_read(_ADDR, _REG_CALIB_T, _CALIB_BYTES, nack=True),
        ])
        driver = _make_driver(bus)
        with pytest.raises(BusNackError):
            driver.measure()

    def test_TM08_nack_on_ctrl_meas_write_raises_bus_nack(self) -> None:
        """measure() propagates BusNackError from ctrl_meas write."""
        bus = ScriptedBus([
            ScriptedBus.step_read(_ADDR, _REG_CALIB_T, _CALIB_BYTES),
            ScriptedBus.step_write(_ADDR, _REG_CTRL_MEAS, _CTRL_MEAS_FORCED, nack=True),
        ])
        driver = _make_driver(bus)
        with pytest.raises(BusNackError):
            driver.measure()

    def test_TM09_nack_on_status_poll_raises_bus_nack(self) -> None:
        """measure() propagates BusNackError from a status poll read."""
        bus = ScriptedBus([
            ScriptedBus.step_read(_ADDR, _REG_CALIB_T, _CALIB_BYTES),
            ScriptedBus.step_write(_ADDR, _REG_CTRL_MEAS, _CTRL_MEAS_FORCED),
            ScriptedBus.step_read(_ADDR, _REG_STATUS, _STATUS_BUSY, nack=True),
        ])
        driver = _make_driver(bus)
        with pytest.raises(BusNackError):
            driver.measure()

    def test_TM10_nack_on_temp_read_raises_bus_nack(self) -> None:
        """measure() propagates BusNackError from the temperature read."""
        bus = ScriptedBus([
            ScriptedBus.step_read(_ADDR, _REG_CALIB_T, _CALIB_BYTES),
            ScriptedBus.step_write(_ADDR, _REG_CTRL_MEAS, _CTRL_MEAS_FORCED),
            ScriptedBus.step_read(_ADDR, _REG_STATUS, _STATUS_IDLE),
            ScriptedBus.step_read(_ADDR, _REG_TEMP_MSB, _RAW_25C, nack=True),
        ])
        driver = _make_driver(bus)
        with pytest.raises(BusNackError):
            driver.measure()

    def test_TM11_short_calib_read_raises_protocol_error(self) -> None:
        """measure() raises ProtocolReadError when calibration returns wrong length."""
        # Scripted 4 bytes but driver requests 6 → ScriptedBus raises ProtocolReadError
        bus = ScriptedBus([
            ScriptedBus.step_read(_ADDR, _REG_CALIB_T, _CALIB_BYTES[:4]),
        ])
        driver = _make_driver(bus)
        with pytest.raises(ProtocolReadError):
            driver.measure()

    def test_TM12_ctrl_meas_write_sends_0x21(self) -> None:
        """measure() writes exactly b'\\x21' to ctrl_meas register 0xF4."""
        bus = _make_measure_bus(
            status_sequence=[_STATUS_IDLE],
            temp_raw=_RAW_25C,
        )
        driver = _make_driver(bus)
        driver.measure()
        # If the wrong byte were written the ScriptedBusStepMismatch would have fired.
        bus.assert_exhausted()


# ===========================================================================
# TS01–TS02 — full identify + measure sequences
# ===========================================================================

class TestFullSequence:
    """Verify identify() followed by measure() over a single scripted bus."""

    def test_TS01_identify_then_measure_25c(self) -> None:
        """Full sequence: identify() then measure() returns 25.08 °C."""
        bus = ScriptedBus([
            # identify
            ScriptedBus.step_read(_ADDR, _REG_ID, _ID_GOOD),
            # measure: calib, write ctrl_meas, status poll, temp read
            ScriptedBus.step_read(_ADDR, _REG_CALIB_T, _CALIB_BYTES),
            ScriptedBus.step_write(_ADDR, _REG_CTRL_MEAS, _CTRL_MEAS_FORCED),
            ScriptedBus.step_read(_ADDR, _REG_STATUS, _STATUS_IDLE),
            ScriptedBus.step_read(_ADDR, _REG_TEMP_MSB, _RAW_25C),
        ])
        clock = StepClock(0)
        driver = BME280Driver(bus=bus, clock=clock, address_7bit=_ADDR)

        identity = driver.identify()
        result = driver.measure()

        assert identity.part_id == 0x60
        assert result.celsius == _TEMP_25C
        bus.assert_exhausted()

    def test_TS02_identify_then_measure_neg8c(self) -> None:
        """Full sequence: identify() then measure() returns -7.86 °C."""
        bus = ScriptedBus([
            # identify
            ScriptedBus.step_read(_ADDR, _REG_ID, _ID_GOOD),
            # measure
            ScriptedBus.step_read(_ADDR, _REG_CALIB_T, _CALIB_BYTES),
            ScriptedBus.step_write(_ADDR, _REG_CTRL_MEAS, _CTRL_MEAS_FORCED),
            ScriptedBus.step_read(_ADDR, _REG_STATUS, _STATUS_IDLE),
            ScriptedBus.step_read(_ADDR, _REG_TEMP_MSB, _RAW_NEG8C),
        ])
        clock = StepClock(0)
        driver = BME280Driver(bus=bus, clock=clock, address_7bit=_ADDR)

        identity = driver.identify()
        result = driver.measure()

        assert identity.part_id == 0x60
        assert result.celsius == _TEMP_NEG8C
        bus.assert_exhausted()
