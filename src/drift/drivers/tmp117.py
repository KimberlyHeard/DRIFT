"""
TMP117 reference driver.

Implements identify(), configure(), and measure() against the RegisterBus and
Clock interfaces only.  The driver has no knowledge of any virtual device
internals, fixture state, or expected values.

Source references: TI SNOSD82D Rev. D.
  F01  p21  §Table 7-2  — selected seven-bit address 0x48.
  F02  p20  §7.5.3.1    — register bytes MSB first.
  F03  p25              — temperature 0x00, configuration 0x01, device-ID 0x0F.
  F04  p26  §7.6.2      — signed 16-bit two's-complement, 1/128 °C per LSB.
  F05  p27              — Data_Ready bit 13; MOD bits 11:10; AVG bits 6:5.
  F06  p27              — MOD 01 = shutdown; MOD 11 = one-shot; AVG 00 = none.
  F07  p27              — reading configuration OR temperature clears Data_Ready.
  F08  pp14–15 §7.4.3   — one-shot completes then returns to shutdown.
  F09  p6               — single conversion: 13 ms min, 15.5 ms typical, 17.5 ms max.
  F10  p32              — device-ID lower 12 bits = 0x117; upper 4 bits = revision.

DRIFT policies (not vendor facts):
  - Timeout: 100 000 µs.
  - Poll interval: 1 000 µs.
  - Fixture initialized in shutdown with configuration 0x0600 before measure().
"""

from __future__ import annotations

from drift.decoders.tmp117 import decode_device_id, decode_temperature
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
# Register addresses — F03, SNOSD82D p25
# ---------------------------------------------------------------------------
_REG_TEMPERATURE: int = 0x00    # Temperature result register (read-only)
_REG_CONFIGURATION: int = 0x01  # Configuration register (read/write)
_REG_DEVICE_ID: int = 0x0F      # Device-ID register (read-only)

# ---------------------------------------------------------------------------
# Configuration bit masks — F05/F06, SNOSD82D p27
# ---------------------------------------------------------------------------
_DATA_READY_BIT: int = 0x2000   # bit 13: conversion complete (F05)
_MOD_MASK: int = 0x0C00         # bits 11:10: operating mode (F05)
_AVG_MASK: int = 0x0060         # bits 6:5: averaging mode (F05)

# ---------------------------------------------------------------------------
# Selected configuration words — derived from F05/F06, verified in contract.
# Derivation: reset 0x0220, clear MOD (0x0C00) and AVG (0x0060) masks,
# set shutdown (MOD=01, 0x0400) or one-shot (MOD=11, 0x0C00).
# Contract derived_candidates confirm: shutdown=0x0600, start=0x0E00.
# ---------------------------------------------------------------------------
_CONFIG_SHUTDOWN: int = 0x0600  # shutdown, AVG=00 — DRIFT initialized fixture
_CONFIG_ONE_SHOT: int = 0x0E00  # one-shot, AVG=00 — triggers conversion (F06)

# ---------------------------------------------------------------------------
# DRIFT policies (not vendor facts)
# ---------------------------------------------------------------------------
_TIMEOUT_US: int = 100_000      # 100 ms maximum polling window
_POLL_INTERVAL_US: int = 1_000  # 1 ms poll interval

# ---------------------------------------------------------------------------
# Wire width
# ---------------------------------------------------------------------------
_REGISTER_WIDTH: int = 2        # all TMP117 registers are 16-bit (2 bytes)


class TMP117Driver:
    """
    TMP117 reference driver for the selected profile:
      - One-shot conversion, averaging disabled, address 0x48.
      - Fixture initialized in shutdown before measure() is called.
      - Uses RegisterBus and Clock protocols; no device internals accessible.

    Parameters
    ----------
    bus:
        A RegisterBus implementation (scripted or virtual device adapter).
    clock:
        A Clock implementation providing integer-microsecond virtual time.
    address_7bit:
        Seven-bit I2C device address (default 0x48, selected by ADD0=GND, F01).
    """

    def __init__(
        self,
        bus: RegisterBus,
        clock: Clock,
        address_7bit: int = 0x48,
    ) -> None:
        self._bus = bus
        self._clock = clock
        self._address = validate_7bit_address(address_7bit)

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def identify(self) -> DeviceIdentity:
        """
        Read device-ID register and validate TMP117 part identity.

        Reads register 0x0F (2 bytes, MSB first — F02/F03).
        Lower 12 bits must equal 0x117 (F10).
        Upper 4 bits carry the silicon revision; any value is accepted.

        Returns
        -------
        DeviceIdentity
            Frozen dataclass with part_id, revision, and raw_bytes.

        Raises
        ------
        BusNackError
            If the device does not acknowledge the read.
        ProtocolReadError
            If the response length is not 2 bytes.
        DeviceIdentityError
            If the lower 12-bit part ID does not equal 0x117.
        """
        raw = self._bus.read_register(self._address, _REG_DEVICE_ID, _REGISTER_WIDTH)
        if len(raw) != _REGISTER_WIDTH:
            raise ProtocolReadError(
                f"TMP117 device-ID register returned {len(raw)} byte(s); expected 2"
            )
        try:
            part_id, revision = decode_device_id(raw)
        except Exception as exc:
            raise DeviceIdentityError(str(exc)) from exc
        return DeviceIdentity(part_id=part_id, revision=revision, raw_bytes=raw)

    def configure(self) -> None:
        """
        Write the selected shutdown configuration to the TMP117.

        Writes 0x0600 to register 0x01:
          - MOD = 01 (shutdown, F06)
          - AVG = 00 (averaging disabled, F06)

        The fixture is declared initialized in shutdown before measure() is
        called; this write confirms the exact register state for the selected
        profile.

        Raises
        ------
        BusNackError
            If the device does not acknowledge the write.
        """
        config_bytes = _CONFIG_SHUTDOWN.to_bytes(2, "big")
        self._bus.write_register(self._address, _REG_CONFIGURATION, config_bytes)

    def measure(self, timeout_us: int = _TIMEOUT_US) -> Measurement:
        """
        Trigger one-shot conversion and wait for Data_Ready, then read temperature.

        Procedure (all per approved contract):
          1. Write 0x0E00 (one-shot, AVG=00) to configuration register (F06/F08).
          2. Poll configuration register every 1 000 µs (DRIFT policy).
             - If bit 13 (Data_Ready) is set in the returned word, the reading is
               complete.  The poll read itself consumes the Data_Ready flag (F07);
               no second configuration read is issued.
          3. Read the temperature register (2 bytes, MSB first) (F02/F03/F04).
          4. Decode signed 16-bit two's-complement at 1/128 °C per LSB (F04).

        Parameters
        ----------
        timeout_us:
            Maximum virtual microseconds to wait; default 100 000 µs.

        Returns
        -------
        Measurement
            Frozen dataclass with raw_bytes, celsius, and virtual_time_us at
            the moment Data_Ready was observed.

        Raises
        ------
        BusNackError
            If any bus transaction does not acknowledge.
        ProtocolReadError
            If the temperature register response is not exactly 2 bytes.
        ConversionTimeout
            If Data_Ready is not set within timeout_us virtual microseconds.
        """
        # Step 1: trigger one-shot conversion.
        start_config = _CONFIG_ONE_SHOT.to_bytes(2, "big")
        self._bus.write_register(self._address, _REG_CONFIGURATION, start_config)

        # Step 2: poll for Data_Ready.
        deadline_us = self._clock.now_us() + timeout_us
        max_polls = timeout_us // _POLL_INTERVAL_US + 2  # bounded loop guard
        ready_time_us: int | None = None

        for _ in range(max_polls):
            self._clock.advance_us(_POLL_INTERVAL_US)
            if self._clock.now_us() > deadline_us:
                break
            cfg_raw = self._bus.read_register(
                self._address, _REG_CONFIGURATION, _REGISTER_WIDTH
            )
            cfg_word = (cfg_raw[0] << 8) | cfg_raw[1]
            if cfg_word & _DATA_READY_BIT:
                # Data_Ready observed.  The configuration read has already
                # consumed the flag (F07); do NOT issue another status read.
                ready_time_us = self._clock.now_us()
                break
        else:
            raise ConversionTimeout(
                f"TMP117 conversion did not complete within {timeout_us} µs"
            )

        if ready_time_us is None:
            raise ConversionTimeout(
                f"TMP117 conversion did not complete within {timeout_us} µs"
            )

        # Step 3: read temperature register.
        temp_raw = self._bus.read_register(
            self._address, _REG_TEMPERATURE, _REGISTER_WIDTH
        )
        if len(temp_raw) != _REGISTER_WIDTH:
            raise ProtocolReadError(
                f"TMP117 temperature register returned {len(temp_raw)} byte(s); expected 2"
            )

        # Step 4: decode temperature.
        celsius = decode_temperature(temp_raw)
        return Measurement(
            raw_bytes=temp_raw,
            celsius=celsius,
            virtual_time_us=ready_time_us,
        )
