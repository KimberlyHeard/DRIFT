"""
BME280 temperature-only forced-mode driver.

Implements identify(), configure(), and measure() against the RegisterBus and
Clock interfaces only.  The driver has no knowledge of any virtual device
internals, fixture state, or expected values.

Source references: Bosch BST-BME280-DS001-24 Rev. 1.24.
  F01  p27  §5.4.1    — chip ID register 0xD0 returns 0x60.
  F02  p32  §6.2      — SDO=GND selects address 0x76.
  F03  p24  §4.2.2    — dig_T1 unsigned short; dig_T2/T3 signed short; LSB at
                         lower address (little-endian); T1 at 0x88/0x89,
                         T2 at 0x8A/0x8B, T3 at 0x8C/0x8D.
  F04  pp25,31 §5.4.8 — raw 20-bit unsigned: bits[19:12] at 0xFA, bits[11:4] at
                         0xFB, bits[3:0] at 0xFC[7:4].
  F05  p25  §4.2.3    — 32-bit integer temperature compensation formula.
  F06  p29  §5.4.5    — mode[1:0] in ctrl_meas 0xF4 bits[1:0]: 00=sleep, 01/10=forced.
  F07  p28  §5.4.4    — status 0xF3 bit3 (mask 0x08) = measuring.
  F08  p29  §5.4.5    — osrs_t[2:0] in ctrl_meas bits[7:5]: 001=x1.
  F09  p29  §5.4.5    — osrs_p[2:0] in ctrl_meas bits[4:2]: 000=skipped.
  F12  p51  §9.1      — temperature x1, P/H skipped: typical 3.0 ms, max 3.55 ms.
  F13  p15  §3.3.3    — forced mode: one measurement, then returns to sleep.

DRIFT policies (not vendor facts):
  - Timeout:                 100 000 µs.
  - Poll interval:             1 000 µs.
  - Virtual conversion time:   3 600 µs (slightly above 3.55 ms max per F12).
  - Fixture initial state: sleep_after_nvm_copy (status bit3=0 before forced write).
"""

from __future__ import annotations

import struct

from drift.interfaces import (
    Clock,
    ConversionTimeout,
    DeviceIdentity,
    DeviceIdentityError,
    Measurement,
    ProtocolReadError,
    RegisterBus,
    validate_7bit_address,
)

# ---------------------------------------------------------------------------
# Register addresses
# ---------------------------------------------------------------------------
_REG_ID: int = 0xD0          # Chip ID — F01
_REG_CALIB_T: int = 0x88     # Six calibration bytes: dig_T1/T2/T3 — F03
_REG_STATUS: int = 0xF3      # Status register — F07
_REG_CTRL_MEAS: int = 0xF4   # Measurement control — F06/F08/F09
_REG_TEMP_MSB: int = 0xFA    # Three raw temperature bytes — F04

# ---------------------------------------------------------------------------
# Identity
# ---------------------------------------------------------------------------
_EXPECTED_CHIP_ID: int = 0x60        # BME280 mass-production chip ID — F01

# ---------------------------------------------------------------------------
# Control register values (derived_candidates from approved contract)
# ctrl_meas = 0x21: osrs_t=001 (bits7:5=001→0x20), osrs_p=000, mode=01 (forced)
# ---------------------------------------------------------------------------
_CTRL_MEAS_FORCED: bytes = b"\x21"   # forced, osrs_t=x1, osrs_p=skipped — F05/F06/F08/F09

# ---------------------------------------------------------------------------
# Status bit mask — F07
# ---------------------------------------------------------------------------
_STATUS_MEASURING_BIT: int = 0x08    # bit3: set while conversion running

# ---------------------------------------------------------------------------
# Calibration sizes and struct formats — F03
# ---------------------------------------------------------------------------
_CALIB_T_LENGTH: int = 6             # 6 bytes: T1(2)+T2(2)+T3(2)
# dig_T1 unsigned, dig_T2 signed, dig_T3 signed — all little-endian — F03
_CALIB_T_FMT: str = "<Hhh"           # '<' little-endian, H=uint16, h=int16, h=int16

# ---------------------------------------------------------------------------
# Raw temperature length — F04
# ---------------------------------------------------------------------------
_TEMP_RAW_LENGTH: int = 3            # 0xFA, 0xFB, 0xFC

# ---------------------------------------------------------------------------
# DRIFT policies (not vendor facts)
# ---------------------------------------------------------------------------
_TIMEOUT_US: int = 100_000           # 100 ms polling window
_POLL_INTERVAL_US: int = 1_000       # 1 ms poll interval


class BME280Driver:
    """
    BME280 reference driver for the selected temperature-only forced-mode profile:
      - Forced mode, osrs_t=x1, osrs_p=skipped, osrs_h=skipped, filter off.
      - Address 0x76 (SDO tied to GND, F02).
      - Fixture initialized in sleep_after_nvm_copy before measure() is called.
      - Uses RegisterBus and Clock protocols; no device internals accessible.

    Parameters
    ----------
    bus:
        A RegisterBus implementation (scripted or virtual device adapter).
    clock:
        A Clock implementation providing integer-microsecond virtual time.
    address_7bit:
        Seven-bit I2C device address (default 0x76, SDO=GND, F02).
    """

    def __init__(
        self,
        bus: RegisterBus,
        clock: Clock,
        address_7bit: int = 0x76,
    ) -> None:
        self._bus = bus
        self._clock = clock
        self._address = validate_7bit_address(address_7bit)

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def identify(self) -> DeviceIdentity:
        """
        Read chip-ID register 0xD0 and validate BME280 identity.

        Reads register 0xD0 (1 byte — F01).
        The byte must equal 0x60 for BME280 mass-production devices (F01).

        Returns
        -------
        DeviceIdentity
            Frozen dataclass with part_id=0x60, revision=0, raw_bytes (1 byte).

        Raises
        ------
        BusNackError
            If the device does not acknowledge.
        ProtocolReadError
            If the response length is not 1 byte.
        DeviceIdentityError
            If the chip ID does not equal 0x60.
        """
        raw = self._bus.read_register(self._address, _REG_ID, 1)
        if len(raw) != 1:
            raise ProtocolReadError(
                f"BME280 chip-ID register returned {len(raw)} byte(s); expected 1"
            )
        chip_id = raw[0]
        if chip_id != _EXPECTED_CHIP_ID:
            raise DeviceIdentityError(
                f"BME280 chip-ID mismatch: expected 0x{_EXPECTED_CHIP_ID:02X}, "
                f"got 0x{chip_id:02X}"
            )
        return DeviceIdentity(part_id=chip_id, revision=0, raw_bytes=raw)

    def measure(self, timeout_us: int = _TIMEOUT_US) -> Measurement:
        """
        Perform one forced-mode temperature measurement and return the result.

        Procedure (all per approved contract):
          1. Read 6 calibration bytes from 0x88 (dig_T1 unsigned, dig_T2/T3
             signed, all little-endian) — F03.
          2. Write ctrl_meas=0x21 to register 0xF4 to trigger forced measurement
             (osrs_t=x1, osrs_p=skipped, forced mode) — F06/F08/F09.
          3. Poll status register 0xF3 every 1 000 µs.  Wait until bit3
             (measuring=0x08) is clear, meaning conversion is complete — F07.
             A clear measuring bit immediately after the forced write does NOT
             indicate completion; at least one poll_interval must elapse before
             the first status check to avoid accepting a stale pre-write clear.
          4. Read 3 raw temperature bytes from 0xFA (temp_msb, temp_lsb,
             temp_xlsb) — F04.
          5. Decode 20-bit unsigned adc_T from the three bytes — F04.
          6. Apply 32-bit integer compensation formula to produce temperature
             in 0.01 °C units — F05.

        Parameters
        ----------
        timeout_us:
            Maximum virtual microseconds to wait; default 100 000 µs.

        Returns
        -------
        Measurement
            Frozen dataclass with raw_bytes (3 bytes), celsius, and
            virtual_time_us at the moment measuring=0 was observed.

        Raises
        ------
        BusNackError
            If any bus transaction does not acknowledge.
        ProtocolReadError
            If calibration or temperature reads return wrong lengths.
        ConversionTimeout
            If measuring bit does not clear within timeout_us virtual µs.
        """
        # Step 1: read calibration bytes dig_T1/T2/T3 from 0x88 — F03
        calib_raw = self._bus.read_register(self._address, _REG_CALIB_T, _CALIB_T_LENGTH)
        if len(calib_raw) != _CALIB_T_LENGTH:
            raise ProtocolReadError(
                f"BME280 calibration read returned {len(calib_raw)} byte(s); "
                f"expected {_CALIB_T_LENGTH}"
            )
        dig_T1, dig_T2, dig_T3 = struct.unpack(_CALIB_T_FMT, calib_raw)

        # Step 2: write ctrl_meas=0x21 to trigger forced measurement — F06/F08/F09
        self._bus.write_register(self._address, _REG_CTRL_MEAS, _CTRL_MEAS_FORCED)

        # Step 3: poll status register until measuring bit (bit3) clears — F07
        # Advance clock before first poll so an immediate clear after the forced
        # write is not mistaken for a completed conversion.
        deadline_us = self._clock.now_us() + timeout_us
        max_polls = timeout_us // _POLL_INTERVAL_US + 2  # bounded loop guard
        ready_time_us: int | None = None

        for _ in range(max_polls):
            self._clock.advance_us(_POLL_INTERVAL_US)
            if self._clock.now_us() > deadline_us:
                break
            status_raw = self._bus.read_register(self._address, _REG_STATUS, 1)
            if not (status_raw[0] & _STATUS_MEASURING_BIT):
                # measuring bit is clear — conversion complete
                ready_time_us = self._clock.now_us()
                break
        else:
            raise ConversionTimeout(
                f"BME280 conversion did not complete within {timeout_us} µs"
            )

        if ready_time_us is None:
            raise ConversionTimeout(
                f"BME280 conversion did not complete within {timeout_us} µs"
            )

        # Step 4: read raw temperature bytes 0xFA..0xFC — F04
        temp_raw = self._bus.read_register(self._address, _REG_TEMP_MSB, _TEMP_RAW_LENGTH)
        if len(temp_raw) != _TEMP_RAW_LENGTH:
            raise ProtocolReadError(
                f"BME280 temperature read returned {len(temp_raw)} byte(s); "
                f"expected {_TEMP_RAW_LENGTH}"
            )

        # Step 5: decode 20-bit unsigned adc_T — F04
        # ut[19:12] at temp_msb, ut[11:4] at temp_lsb, ut[3:0] at temp_xlsb[7:4]
        adc_T = (temp_raw[0] << 12) | (temp_raw[1] << 4) | (temp_raw[2] >> 4)

        # Step 6: 32-bit integer compensation — F05
        celsius = _compensate_temperature(adc_T, dig_T1, dig_T2, dig_T3)

        return Measurement(
            raw_bytes=temp_raw,
            celsius=celsius,
            virtual_time_us=ready_time_us,
        )


# ---------------------------------------------------------------------------
# Temperature compensation — F05, BST-BME280-DS001-24 §4.2.3 p25
# ---------------------------------------------------------------------------

def _compensate_temperature(
    adc_T: int,
    dig_T1: int,
    dig_T2: int,
    dig_T3: int,
) -> float:
    """
    32-bit integer temperature compensation.

    Implements the exact Bosch formula from BST-BME280-DS001-24 §4.2.3 p25:

        var1 = ((adc_T >> 3) - (dig_T1 << 1)) * dig_T2 >> 11
        var2 = (((adc_T >> 4) - dig_T1)^2 >> 12) * dig_T3 >> 14
        t_fine = var1 + var2
        T = (t_fine * 5 + 128) >> 8          [units: 0.01 °C]

    All intermediate values use Python's arbitrary-precision integers, matching
    the signed 32-bit behaviour of the Bosch reference implementation.

    Parameters
    ----------
    adc_T : int
        20-bit unsigned raw temperature value.
    dig_T1 : int
        Calibration coefficient T1 (unsigned 16-bit).
    dig_T2 : int
        Calibration coefficient T2 (signed 16-bit).
    dig_T3 : int
        Calibration coefficient T3 (signed 16-bit).

    Returns
    -------
    float
        Temperature in degrees Celsius.
    """
    var1 = ((adc_T >> 3) - (dig_T1 << 1)) * dig_T2 >> 11
    var2_inner = (adc_T >> 4) - dig_T1
    var2 = (var2_inner * var2_inner >> 12) * dig_T3 >> 14
    t_fine = var1 + var2
    t_int = (t_fine * 5 + 128) >> 8   # units: 0.01 °C
    return t_int / 100.0
