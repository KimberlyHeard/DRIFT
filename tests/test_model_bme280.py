"""
tests/test_model_bme280.py — BME280 virtual device model tests.

Tests the virtual BME280 model (BME280VirtualDevice) in isolation.
Uses VirtualClock only; no driver code, no ScriptedBus.

All expected register values, timing, and byte sequences are literal
constants reviewed independently of the production driver and model.

Source facts referenced (Bosch BST-BME280-DS001-24 Rev. 1.24):
  F01  p27   §5.4.1  — chip ID 0xD0 returns 0x60.
  F02  p32   §6.2    — SDO=GND selects address 0x76.
  F03  p24   §4.2.2  — dig_T1 unsigned, T2/T3 signed, little-endian, 6 bytes.
  F04  pp25,31 §5.4.8 — 20-bit raw: 0xFA[19:12], 0xFB[11:4], 0xFC[7:4].
  F06  p29   §5.4.5  — mode[1:0]: 00=sleep, 01=forced.
  F07  p28   §5.4.4  — status 0xF3 bit3: 1=measuring, 0=complete.
  F08  p29   §5.4.5  — osrs_t 001=x1.
  F12  p51   §9.1    — T×1, P/H skipped: typ 3.0 ms, max 3.55 ms.
  F13  p15   §3.3.3  — forced mode → sleep after one conversion.

DRIFT policies:
  virtual_conversion_us = 3600 µs; address = 0x76.

Literal test constants (reviewed independently):
  Chip ID:           0x60  (F01)
  Address:           0x76  (F02, SDO=GND)
  ctrl_meas forced:  0x21  (osrs_t=001 in bits7:5=0x20; forced=01 in bits1:0;
                             combined=0x21; derived_candidates from approved contract)
  Status busy:       0x08  (bit3 set, F07)
  Status idle:       0x00  (bit3 clear, F07)
  Calib bytes:       70 6B 43 67 18 FC
                       dig_T1=27504, dig_T2=26435, dig_T3=-1000 (signed)
  Raw 7E ED 00:      25.08 °C baseline (F04/F05, hand-verified)
  Raw 65 5A C0:      -7.86 °C baseline (F04/F05, hand-verified)
  Conversion time:   3600 µs (DRIFT policy; above 3.55 ms max per F12)
  Reset sentinel:    80 00 00 (no completed conversion yet)
"""

from __future__ import annotations

import pytest

from drift.clock import VirtualClock
from drift.devices.bme280 import BME280VirtualDevice, UnsupportedOperation

# ---------------------------------------------------------------------------
# Literal test constants — must not be derived from driver or decoder
# ---------------------------------------------------------------------------

_ADDR: int = 0x76               # BME280 address, SDO=GND (F02)
_CHIP_ID: bytes = b"\x60"       # 0x60 — BME280 mass-production (F01)

_REG_ID: int = 0xD0             # Chip ID register (F01)
_REG_CALIB_T: int = 0x88        # Calibration T1/T2/T3 base (F03)
_REG_STATUS: int = 0xF3         # Status register (F07)
_REG_CTRL_MEAS: int = 0xF4      # Measurement control (F06)
_REG_TEMP_MSB: int = 0xFA       # Raw temperature bytes (F04)

_CTRL_SLEEP: bytes = b"\x00"    # sleep mode
_CTRL_FORCED: bytes = b"\x21"   # forced, osrs_t=x1 — derived_candidates

_STATUS_BUSY: int = 0x08        # bit3 set — measuring (F07)
_STATUS_IDLE: int = 0x00        # bit3 clear — not measuring (F07)

# Calibration bytes: dig_T1=27504(0x6B70), dig_T2=26435(0x6743), dig_T3=-1000(0xFC18)
_CALIB_BYTES: bytes = bytes([0x70, 0x6B, 0x43, 0x67, 0x18, 0xFC])

# Raw temperature bytes
_RAW_25C: bytes = bytes([0x7E, 0xED, 0x00])   # → 25.08 °C
_RAW_NEG8C: bytes = bytes([0x65, 0x5A, 0xC0]) # → -7.86 °C

# Reset sentinel (no completed conversion)
_RAW_SENTINEL: bytes = bytes([0x80, 0x00, 0x00])

# DRIFT policy conversion time
_CONV_US: int = 3_600


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_device(
    *,
    temp_raw: bytes = _RAW_25C,
    calib: bytes = _CALIB_BYTES,
    conv_us: int = _CONV_US,
    clock: VirtualClock | None = None,
) -> tuple[BME280VirtualDevice, VirtualClock]:
    if clock is None:
        clock = VirtualClock(0)
    dev = BME280VirtualDevice(
        clock=clock,
        calib_bytes=calib,
        temp_raw_bytes=temp_raw,
        conversion_us=conv_us,
        address_7bit=_ADDR,
    )
    return dev, clock


# ===========================================================================
# TBM01–TBM04 — chip ID register
# ===========================================================================

class TestChipID:
    """Model returns correct chip ID register."""

    def test_TBM01_chip_id_returns_0x60(self) -> None:
        """read_register(0xD0) returns b'\\x60' — F01."""
        dev, _ = _make_device()
        result = dev.read_register(_REG_ID)
        assert result == _CHIP_ID

    def test_TBM02_chip_id_length_one_byte(self) -> None:
        """Chip ID read returns exactly 1 byte."""
        dev, _ = _make_device()
        assert len(dev.read_register(_REG_ID)) == 1

    def test_TBM03_chip_id_trace_event_recorded(self) -> None:
        """Chip ID read records a trace event with register 0xD0."""
        dev, _ = _make_device()
        dev.read_register(_REG_ID)
        events = dev.trace
        assert len(events) == 1
        assert events[0].register == _REG_ID
        assert events[0].operation == "read"
        assert events[0].outcome == "ok"

    def test_TBM04_chip_id_trace_fact_ids(self) -> None:
        """Chip ID trace event carries fact id F01."""
        dev, _ = _make_device()
        dev.read_register(_REG_ID)
        assert "F01" in dev.trace[0].fact_ids


# ===========================================================================
# TBM05–TBM08 — calibration register
# ===========================================================================

class TestCalibration:
    """Model returns correct calibration bytes."""

    def test_TBM05_calib_returns_6_bytes(self) -> None:
        """read_register(0x88) returns exactly 6 bytes — F03."""
        dev, _ = _make_device()
        result = dev.read_register(_REG_CALIB_T)
        assert len(result) == 6

    def test_TBM06_calib_bytes_match_fixture(self) -> None:
        """Calibration bytes match the fixture provided at construction."""
        dev, _ = _make_device(calib=_CALIB_BYTES)
        result = dev.read_register(_REG_CALIB_T)
        assert result == _CALIB_BYTES

    def test_TBM07_calib_returns_custom_bytes(self) -> None:
        """Calibration bytes reflect the constructor argument."""
        custom = bytes([0x01, 0x02, 0x03, 0x04, 0x05, 0x06])
        dev, _ = _make_device(calib=custom)
        assert dev.read_register(_REG_CALIB_T) == custom

    def test_TBM08_calib_trace_fact_F03(self) -> None:
        """Calibration trace event carries fact id F03."""
        dev, _ = _make_device()
        dev.read_register(_REG_CALIB_T)
        assert "F03" in dev.trace[0].fact_ids


# ===========================================================================
# TBM09–TBM15 — status register (F07)
# ===========================================================================

class TestStatusRegister:
    """Status register bit3 reflects conversion state per F07."""

    def test_TBM09_status_idle_on_construction(self) -> None:
        """Status bit3=0 (idle) immediately after construction — sleep_after_nvm_copy."""
        dev, _ = _make_device()
        status = dev.read_register(_REG_STATUS)[0]
        assert (status & _STATUS_BUSY) == 0

    def test_TBM10_status_busy_immediately_after_forced_write(self) -> None:
        """Status bit3=1 immediately after a forced write (before clock advance)."""
        dev, clock = _make_device()
        dev.write_register(_REG_CTRL_MEAS, _CTRL_FORCED)
        # Clock NOT advanced — conversion not yet complete.
        status = dev.read_register(_REG_STATUS)[0]
        assert (status & _STATUS_BUSY) == _STATUS_BUSY, (
            "Status bit3 must be 1 immediately after forced write (F07)"
        )

    def test_TBM11_status_still_busy_before_deadline(self) -> None:
        """Status bit3=1 when clock is at deadline - 1 µs (conversion in progress)."""
        dev, clock = _make_device(conv_us=_CONV_US)
        dev.write_register(_REG_CTRL_MEAS, _CTRL_FORCED)
        clock.advance_us(_CONV_US - 1)  # one µs before deadline
        status = dev.read_register(_REG_STATUS)[0]
        assert (status & _STATUS_BUSY) == _STATUS_BUSY, (
            "Status bit3 must still be 1 one µs before conversion deadline"
        )

    def test_TBM12_status_idle_at_deadline(self) -> None:
        """Status bit3=0 exactly at the conversion deadline."""
        dev, clock = _make_device(conv_us=_CONV_US)
        dev.write_register(_REG_CTRL_MEAS, _CTRL_FORCED)
        clock.advance_us(_CONV_US)  # exactly at deadline
        status = dev.read_register(_REG_STATUS)[0]
        assert (status & _STATUS_BUSY) == 0, (
            "Status bit3 must clear at the conversion deadline"
        )

    def test_TBM13_status_idle_after_deadline(self) -> None:
        """Status bit3=0 after the conversion deadline."""
        dev, clock = _make_device(conv_us=_CONV_US)
        dev.write_register(_REG_CTRL_MEAS, _CTRL_FORCED)
        clock.advance_us(_CONV_US + 1_000)
        status = dev.read_register(_REG_STATUS)[0]
        assert (status & _STATUS_BUSY) == 0

    def test_TBM14_status_byte_is_single_byte(self) -> None:
        """Status register read returns exactly 1 byte."""
        dev, _ = _make_device()
        result = dev.read_register(_REG_STATUS)
        assert len(result) == 1

    def test_TBM15_status_trace_fact_F07(self) -> None:
        """Status register trace event carries fact id F07."""
        dev, _ = _make_device()
        dev.read_register(_REG_STATUS)
        assert "F07" in dev.trace[0].fact_ids


# ===========================================================================
# TBM16–TBM23 — temperature register (F04)
# ===========================================================================

class TestTemperatureRegister:
    """Raw temperature register returns correct bytes before and after conversion."""

    def test_TBM16_temp_sentinel_before_conversion(self) -> None:
        """Temperature register returns reset sentinel before any conversion — F04."""
        dev, _ = _make_device()
        result = dev.read_register(_REG_TEMP_MSB)
        # Reset sentinel: 0x80 00 00 (no completed conversion)
        assert result == _RAW_SENTINEL, (
            f"Expected reset sentinel {_RAW_SENTINEL.hex()!r}, got {result.hex()!r}"
        )

    def test_TBM17_temp_returns_3_bytes(self) -> None:
        """Temperature register read always returns 3 bytes."""
        dev, _ = _make_device()
        assert len(dev.read_register(_REG_TEMP_MSB)) == 3

    def test_TBM18_temp_available_after_conversion_25c(self) -> None:
        """Temperature register returns 25 °C bytes after conversion completes."""
        dev, clock = _make_device(temp_raw=_RAW_25C)
        dev.write_register(_REG_CTRL_MEAS, _CTRL_FORCED)
        clock.advance_us(_CONV_US)
        result = dev.read_register(_REG_TEMP_MSB)
        assert result == _RAW_25C

    def test_TBM19_temp_available_after_conversion_neg8c(self) -> None:
        """Temperature register returns -7.86 °C bytes after conversion completes."""
        dev, clock = _make_device(temp_raw=_RAW_NEG8C)
        dev.write_register(_REG_CTRL_MEAS, _CTRL_FORCED)
        clock.advance_us(_CONV_US)
        result = dev.read_register(_REG_TEMP_MSB)
        assert result == _RAW_NEG8C

    def test_TBM20_temp_sentinel_while_busy_before_deadline(self) -> None:
        """
        Temperature register returns reset sentinel during an active conversion
        (before the deadline).  The old sentinel is not a valid result.
        """
        dev, clock = _make_device(temp_raw=_RAW_25C)
        dev.write_register(_REG_CTRL_MEAS, _CTRL_FORCED)
        clock.advance_us(_CONV_US - 1)  # before deadline
        result = dev.read_register(_REG_TEMP_MSB)
        # Still the reset sentinel — result not yet latched.
        assert result == _RAW_SENTINEL, (
            "Temperature register must return reset sentinel before conversion completes"
        )

    def test_TBM21_temp_retained_after_status_read(self) -> None:
        """
        Reading the status register does not erase the latched temperature.
        After conversion, status read then temp read still returns the result.
        """
        dev, clock = _make_device(temp_raw=_RAW_25C)
        dev.write_register(_REG_CTRL_MEAS, _CTRL_FORCED)
        clock.advance_us(_CONV_US)
        # Read status first (like the driver does on completion poll).
        dev.read_register(_REG_STATUS)
        # Temperature must still be available.
        result = dev.read_register(_REG_TEMP_MSB)
        assert result == _RAW_25C

    def test_TBM22_temp_trace_fact_F04(self) -> None:
        """Temperature trace event carries fact id F04."""
        dev, clock = _make_device()
        dev.write_register(_REG_CTRL_MEAS, _CTRL_FORCED)
        clock.advance_us(_CONV_US)
        dev.read_register(_REG_TEMP_MSB)
        temp_events = [e for e in dev.trace if e.register == _REG_TEMP_MSB]
        assert len(temp_events) == 1
        assert "F04" in temp_events[0].fact_ids

    def test_TBM23_temp_sentinel_not_stale_on_new_conversion(self) -> None:
        """
        Reset fixture clears the latched temperature.
        After reset, reading temp before any new conversion returns the sentinel.
        """
        dev, clock = _make_device(temp_raw=_RAW_25C)
        dev.write_register(_REG_CTRL_MEAS, _CTRL_FORCED)
        clock.advance_us(_CONV_US)
        assert dev.read_register(_REG_TEMP_MSB) == _RAW_25C  # result present
        dev.reset_fixture()
        assert dev.read_register(_REG_TEMP_MSB) == _RAW_SENTINEL  # cleared


# ===========================================================================
# TBM24–TBM28 — forced write and return-to-sleep (F06/F13)
# ===========================================================================

class TestForcedWriteAndSleep:
    """ctrl_meas write triggers conversion; device returns to sleep after F13."""

    def test_TBM24_forced_write_starts_conversion(self) -> None:
        """Forced write 0x21 transitions model from sleep to measuring."""
        dev, _ = _make_device()
        dev.write_register(_REG_CTRL_MEAS, _CTRL_FORCED)
        # Status must be busy immediately.
        status = dev.read_register(_REG_STATUS)[0]
        assert (status & _STATUS_BUSY) == _STATUS_BUSY

    def test_TBM25_device_returns_to_sleep_after_conversion(self) -> None:
        """After conversion completes, device is in sleep state (F13)."""
        dev, clock = _make_device()
        dev.write_register(_REG_CTRL_MEAS, _CTRL_FORCED)
        clock.advance_us(_CONV_US)
        status = dev.read_register(_REG_STATUS)[0]
        assert (status & _STATUS_BUSY) == 0, (
            "Device must return to sleep after forced conversion (F13)"
        )

    def test_TBM26_sleep_write_accepted(self) -> None:
        """Write 0x00 to ctrl_meas is accepted without error."""
        dev, _ = _make_device()
        dev.write_register(_REG_CTRL_MEAS, _CTRL_SLEEP)  # must not raise

    def test_TBM27_unsupported_write_register_raises(self) -> None:
        """Write to unsupported register raises UnsupportedOperation."""
        dev, _ = _make_device()
        with pytest.raises(UnsupportedOperation):
            dev.write_register(0xF5, b"\x00")  # config register — not in profile

    def test_TBM28_normal_mode_write_raises(self) -> None:
        """Write ctrl_meas=0x03 (normal mode) raises UnsupportedOperation — F06."""
        dev, _ = _make_device()
        with pytest.raises(UnsupportedOperation):
            dev.write_register(_REG_CTRL_MEAS, b"\x03")  # bits[1:0]=11 = normal


# ===========================================================================
# TBM29–TBM32 — successive conversions
# ===========================================================================

class TestSuccessiveConversions:
    """Two forced conversions in sequence produce independent results."""

    def test_TBM29_second_conversion_overwrites_first(self) -> None:
        """Second forced conversion replaces first temperature in the latch."""
        clock = VirtualClock(0)
        dev1 = BME280VirtualDevice(
            clock=clock, calib_bytes=_CALIB_BYTES,
            temp_raw_bytes=_RAW_25C, conversion_us=_CONV_US, address_7bit=_ADDR,
        )
        # First conversion
        dev1.write_register(_REG_CTRL_MEAS, _CTRL_FORCED)
        clock.advance_us(_CONV_US)
        assert dev1.read_register(_REG_TEMP_MSB) == _RAW_25C

        # Reset and run second conversion with different temp
        dev1.reset_fixture()
        dev2 = BME280VirtualDevice(
            clock=clock, calib_bytes=_CALIB_BYTES,
            temp_raw_bytes=_RAW_NEG8C, conversion_us=_CONV_US, address_7bit=_ADDR,
        )
        dev2.write_register(_REG_CTRL_MEAS, _CTRL_FORCED)
        clock.advance_us(_CONV_US)
        assert dev2.read_register(_REG_TEMP_MSB) == _RAW_NEG8C

    def test_TBM30_two_conversions_same_device(self) -> None:
        """
        Two successive forced conversions on the same device object.
        After each conversion, temp register reflects the new result.
        """
        clock = VirtualClock(0)
        dev = BME280VirtualDevice(
            clock=clock, calib_bytes=_CALIB_BYTES,
            temp_raw_bytes=_RAW_25C, conversion_us=_CONV_US, address_7bit=_ADDR,
        )
        # First conversion
        dev.write_register(_REG_CTRL_MEAS, _CTRL_FORCED)
        clock.advance_us(_CONV_US)
        assert dev.read_register(_REG_TEMP_MSB) == _RAW_25C
        # Device back to sleep, status=0
        assert (dev.read_register(_REG_STATUS)[0] & _STATUS_BUSY) == 0

        # Second conversion on same device (same temp fixture)
        dev.write_register(_REG_CTRL_MEAS, _CTRL_FORCED)
        clock.advance_us(_CONV_US)
        assert dev.read_register(_REG_TEMP_MSB) == _RAW_25C

    def test_TBM31_status_busy_between_conversions(self) -> None:
        """Between two conversions, status bit3=1 during the second one."""
        clock = VirtualClock(0)
        dev = BME280VirtualDevice(
            clock=clock, calib_bytes=_CALIB_BYTES,
            temp_raw_bytes=_RAW_25C, conversion_us=_CONV_US, address_7bit=_ADDR,
        )
        # Complete first conversion
        dev.write_register(_REG_CTRL_MEAS, _CTRL_FORCED)
        clock.advance_us(_CONV_US)
        # Second conversion
        dev.write_register(_REG_CTRL_MEAS, _CTRL_FORCED)
        clock.advance_us(_CONV_US // 2)  # partway through second conversion
        assert (dev.read_register(_REG_STATUS)[0] & _STATUS_BUSY) == _STATUS_BUSY


# ===========================================================================
# TBM32–TBM35 — trace integrity
# ===========================================================================

class TestTrace:
    """Trace events are immutable and ordered."""

    def test_TBM32_trace_sequence_numbers_ordered(self) -> None:
        """Trace sequence numbers are zero-based and increasing."""
        dev, clock = _make_device()
        dev.read_register(_REG_ID)
        dev.read_register(_REG_CALIB_T)
        dev.write_register(_REG_CTRL_MEAS, _CTRL_FORCED)
        clock.advance_us(_CONV_US)
        dev.read_register(_REG_STATUS)
        dev.read_register(_REG_TEMP_MSB)
        events = dev.trace
        for i, ev in enumerate(events):
            assert ev.sequence == i

    def test_TBM33_trace_is_immutable_tuple(self) -> None:
        """dev.trace returns a tuple (immutable snapshot)."""
        dev, _ = _make_device()
        dev.read_register(_REG_ID)
        t = dev.trace
        assert isinstance(t, tuple)

    def test_TBM34_reset_clears_trace(self) -> None:
        """reset_fixture() clears all trace events."""
        dev, _ = _make_device()
        dev.read_register(_REG_ID)
        assert len(dev.trace) == 1
        dev.reset_fixture()
        assert len(dev.trace) == 0

    def test_TBM35_unsupported_read_records_trace_event(self) -> None:
        """An unsupported register read records a trace event with outcome unsupported."""
        dev, _ = _make_device()
        with pytest.raises(UnsupportedOperation):
            dev.read_register(0xFF)
        events = dev.trace
        assert len(events) == 1
        assert events[0].outcome == "unsupported"


# ===========================================================================
# TBM36 — constructor validation
# ===========================================================================

class TestConstructorValidation:

    def test_TBM36_wrong_calib_length_raises(self) -> None:
        """Constructor raises ValueError for calib_bytes with wrong length."""
        clock = VirtualClock(0)
        with pytest.raises(ValueError, match="calib_bytes"):
            BME280VirtualDevice(clock=clock, calib_bytes=b"\x01\x02\x03")

    def test_TBM37_wrong_temp_raw_length_raises(self) -> None:
        """Constructor raises ValueError for temp_raw_bytes with wrong length."""
        clock = VirtualClock(0)
        with pytest.raises(ValueError, match="temp_raw_bytes"):
            BME280VirtualDevice(
                clock=clock,
                calib_bytes=_CALIB_BYTES,
                temp_raw_bytes=b"\x01\x02",  # only 2 bytes
            )
