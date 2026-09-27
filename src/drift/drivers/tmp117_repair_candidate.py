"""
TMP117 repair candidate driver.

This is the specimen to be diagnosed and patched.  It is a copy of the
byte-swap variant (ByteSwapDriver) with no changes applied yet.

DRIFT labeling (AGENTS.md / Task 09):
  "repair_candidate" is a seeded defect — code-level, not environment fault.
  The byte-swap defect is isolated here so the original ByteSwapDriver in
  tmp117_variants.py is preserved unchanged as the permanent failing example.

  Patch is applied ONLY to this file.  The original byte-swap variant must
  continue to fail after the repair.

Pre-repair state:
  - Raw bytes from device for 25.0 °C : 0x0C 0x80  (MSB first, F02)
  - Byte-swapped : 0x80 0x0C → word 0x800C → signed -32756 → -255.90625 °C
  - Raw bytes from device for -1.0 °C : 0xFF 0x80  (MSB first, F02)
  - Byte-swapped : 0x80 0xFF → word 0x80FF → signed -32513 → -254.0078125 °C
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

_REG_TEMPERATURE: int = 0x00
_REG_CONFIGURATION: int = 0x01
_DATA_READY_BIT: int = 0x2000
_CONFIG_ONE_SHOT: int = 0x0E00
_TIMEOUT_US: int = 100_000
_POLL_INTERVAL_US: int = 1_000
_REGISTER_WIDTH: int = 2


class RepairCandidateDriver:
    """
    TMP117 repair candidate — pre-patch state contains the byte-swap defect.

    LABELED SEEDED DEFECT (pre-patch): reverses the two temperature bytes
    before decoding, identical to ByteSwapDriver.  This copy is the specimen
    that Bob will diagnose and patch.  The original ByteSwapDriver is kept
    untouched as a permanent failing reference.

    After the patch the byte order must be corrected to match F02 (MSB first).
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
        """Identical to TMP117Driver.identify() — defect is decode-path only."""
        from drift.drivers.tmp117 import TMP117Driver
        ref = TMP117Driver(self._bus, self._clock, self._address)
        return ref.identify()

    def configure(self) -> None:
        """Identical to TMP117Driver.configure() — defect is decode-path only."""
        from drift.drivers.tmp117 import TMP117Driver
        ref = TMP117Driver(self._bus, self._clock, self._address)
        ref.configure()

    def measure(self, timeout_us: int = _TIMEOUT_US) -> Measurement:
        """
        Trigger one-shot conversion, poll for Data_Ready, read temperature.

        SEEDED DEFECT (pre-patch): byte order is reversed before decoding.
        """
        start_config = _CONFIG_ONE_SHOT.to_bytes(2, "big")
        self._bus.write_register(self._address, _REG_CONFIGURATION, start_config)

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
                f"RepairCandidateDriver: conversion did not complete within {timeout_us} µs"
            )

        if ready_time_us is None:
            raise ConversionTimeout(
                f"RepairCandidateDriver: conversion did not complete within {timeout_us} µs"
            )

        temp_raw = self._bus.read_register(
            self._address, _REG_TEMPERATURE, _REGISTER_WIDTH
        )
        if len(temp_raw) != _REGISTER_WIDTH:
            raise ProtocolReadError(
                f"RepairCandidateDriver: temperature register returned {len(temp_raw)} byte(s); expected 2"
            )

        # PATCH (F02, SNOSD82D p20 §7.5.3.1): register bytes are MSB first.
        # temp_raw[0] is the high byte, temp_raw[1] is the low byte — no swap.
        celsius = decode_temperature(temp_raw)

        return Measurement(
            raw_bytes=temp_raw,
            celsius=celsius,
            virtual_time_us=ready_time_us,
        )
