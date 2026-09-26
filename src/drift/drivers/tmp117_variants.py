"""
TMP117 driver variants.

This module holds the byte-swap variant driver, which is a deliberately seeded
defect used to demonstrate the verification pipeline.

DRIFT labeling (AGENTS.md):
  "byte_swap" is a seeded defect — a code-level change that introduces a
  known-wrong behavior.  It is NOT a fault-injection scenario (which changes
  the environment).  The byte-swap variant reverses the two temperature register
  bytes before decoding, producing incorrect output against the fixed literal
  25.0 °C expectation.

  The independent expected value (25.0 °C) does not change.  Only the driver
  decode path is broken.

Expected failing behavior (independent arithmetic, not derived from this code):
  - Raw bytes from device: 0x0C 0x80 (TMP117 register for 25.0 °C).
  - Byte-swapped: 0x80 0x0C (i.e. raw word 0x800C).
  - 0x800C as signed 16-bit = 0x800C − 0x10000 = −32756 counts.
  - −32756 / 128 = −255.90625 °C.
  - The 25.0 °C assertion therefore fails with actual = −255.90625 °C.
  (STATUS.md: "swapped bytes 0C 80 become 0x800C, or −255.90625 °C")
"""

from __future__ import annotations

from drift.decoders.tmp117 import decode_temperature
from drift.interfaces import (
    Clock,
    ConversionTimeout,
    DeviceIdentity,
    Measurement,
    ProtocolReadError,
    RegisterBus,
    validate_7bit_address,
)

# Registers and constants — same as the reference driver.
_REG_TEMPERATURE: int = 0x00
_REG_CONFIGURATION: int = 0x01
_REG_DEVICE_ID: int = 0x0F
_DATA_READY_BIT: int = 0x2000
_CONFIG_ONE_SHOT: int = 0x0E00
_TIMEOUT_US: int = 100_000
_POLL_INTERVAL_US: int = 1_000
_REGISTER_WIDTH: int = 2


class ByteSwapDriver:
    """
    TMP117 driver with a deliberately seeded byte-swap defect.

    LABELED SEEDED DEFECT — this driver intentionally reverses the two bytes
    of the temperature register response before decoding.  The measure() method
    otherwise follows the same protocol as TMP117Driver.

    Purpose: demonstrate that the verification pipeline produces a genuine
    FAIL report with the literal 25.0 °C expectation unchanged.

    The identify() and configure() methods are identical to the reference driver
    (defect is only in the temperature decode path).
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

    def identify(self) -> DeviceIdentity:
        """Identical to TMP117Driver.identify()."""
        from drift.drivers.tmp117 import TMP117Driver
        # Delegate to reference driver — defect is only in temperature decode.
        ref = TMP117Driver(self._bus, self._clock, self._address)
        return ref.identify()

    def configure(self) -> None:
        """Identical to TMP117Driver.configure()."""
        from drift.drivers.tmp117 import TMP117Driver
        ref = TMP117Driver(self._bus, self._clock, self._address)
        ref.configure()

    def measure(self, timeout_us: int = _TIMEOUT_US) -> Measurement:
        """
        Trigger one-shot conversion, poll for Data_Ready, then read temperature.

        SEEDED DEFECT: The two temperature bytes are reversed before decoding.
        This produces −255.90625 °C for the 25.0 °C fixture (0x0C80 → 0x800C).
        """
        # Step 1: trigger one-shot.
        start_config = _CONFIG_ONE_SHOT.to_bytes(2, "big")
        self._bus.write_register(self._address, _REG_CONFIGURATION, start_config)

        # Step 2: poll for Data_Ready.
        deadline_us = self._clock.now_us() + timeout_us
        max_polls = timeout_us // _POLL_INTERVAL_US + 2
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
                ready_time_us = self._clock.now_us()
                break
        else:
            raise ConversionTimeout(
                f"ByteSwapDriver: conversion did not complete within {timeout_us} µs"
            )

        if ready_time_us is None:
            raise ConversionTimeout(
                f"ByteSwapDriver: conversion did not complete within {timeout_us} µs"
            )

        # Step 3: read temperature register.
        temp_raw = self._bus.read_register(
            self._address, _REG_TEMPERATURE, _REGISTER_WIDTH
        )
        if len(temp_raw) != _REGISTER_WIDTH:
            raise ProtocolReadError(
                f"ByteSwapDriver: temperature register returned {len(temp_raw)} byte(s); expected 2"
            )

        # SEEDED DEFECT: reverse the byte order before decoding.
        # Correct order: temp_raw[0]=MSB, temp_raw[1]=LSB.
        # Defective order: temp_raw[1]=MSB, temp_raw[0]=LSB.
        defective_raw = bytes([temp_raw[1], temp_raw[0]])
        celsius = decode_temperature(defective_raw)

        return Measurement(
            raw_bytes=temp_raw,          # preserve original bytes in report
            celsius=celsius,             # decoded from swapped bytes — wrong value
            virtual_time_us=ready_time_us,
        )
