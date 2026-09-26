"""
Task 06 integration gate: TMP117Driver connected to VirtualDeviceBus,
TMP117VirtualDevice, and VirtualClock.

These tests are INDEPENDENT of model internals.  Expected temperatures are
literal values derived independently from F04:
  - 0x0C80 = 3200 counts × (1/128 °C/count) = 25.0 °C   (F04, SNOSD82D p26)
  - 0xFF80 = -128 counts × (1/128 °C/count) = -1.0 °C   (F04, SNOSD82D p26)
    (0xFF80 as signed 16-bit = -128, two's complement)

DRIFT policy: poll_interval_us = 1 000, virtual_conversion_us = 15 500.
Driver polls at 1 000, 2 000, … 16 000 µs; Data_Ready is first seen at 16 000 µs.

The driver issues:
  1. write_register(0x48, 0x01, b'\\x0e\\x00')  — one-shot trigger
  2. read_register(0x48,  0x01, 2)  × N polls   — config polls until Data_Ready
  3. read_register(0x48,  0x00, 2)              — temperature read

F07: reading configuration clears Data_Ready.  The poll that observes
Data_Ready is a configuration read; it therefore clears the flag.  The
subsequent temperature read must still return the stored conversion result
(the temperature register stores the last completed conversion and is not
erased by reading configuration).

Source: TI SNOSD82D Rev. D.
  F04 p26 §7.6.2 — signed 16-bit two's-complement, 1/128 °C per LSB.
  F07 p27        — reading configuration OR temperature clears Data_Ready.
  F08 pp14–15    — one-shot completes then returns to shutdown.
  F09 p6         — typical 15 500 µs.
"""

from __future__ import annotations

import pytest

from drift.bus import VirtualDeviceBus
from drift.clock import VirtualClock
from drift.devices.tmp117 import TMP117VirtualDevice
from drift.drivers.tmp117 import TMP117Driver


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def make_integration_stack(
    temperature_raw: int = 0x0C80,
) -> tuple[VirtualClock, TMP117VirtualDevice, TMP117Driver]:
    """
    Return (clock, device, driver) wired together.

    The VirtualClock is shared by both the device and the driver so that
    clock.advance_us() inside the driver is visible to the device's _tick().
    """
    clock = VirtualClock()
    device = TMP117VirtualDevice(clock, temperature_raw=temperature_raw)
    bus = VirtualDeviceBus(device, address_7bit=0x48)
    driver = TMP117Driver(bus, clock, address_7bit=0x48)
    return clock, device, driver


def print_trace(device: TMP117VirtualDevice) -> None:
    """Print the accumulated trace to stdout (captured by pytest -s)."""
    print()
    print(f"  {'seq':>3}  {'µs':>7}  {'op':>5}  {'reg':>4}  {'sent':>8}  {'recv':>8}  {'outcome'}")
    for ev in device.trace:
        sent = ev.sent_bytes.hex() if ev.sent_bytes else "-"
        recv = ev.received_bytes.hex() if ev.received_bytes else "-"
        print(
            f"  {ev.sequence:>3}  {ev.virtual_time_us:>7}  "
            f"{ev.operation:>5}  {ev.register:#04x}  "
            f"{sent:>8}  {recv:>8}  {ev.outcome}"
        )


# ---------------------------------------------------------------------------
# IT01 — 0x0C80 fixture: identify + configure + measure → 25.0 °C at 16 000 µs
# ---------------------------------------------------------------------------

class TestIntegration:

    def test_IT01_positive_temperature_25C(self):
        """
        Full driver flow with 0x0C80 fixture must produce 25.0 °C at 16 000 µs.

        Independent literal: 0x0C80 = 3200 counts; 3200 / 128 = 25.0 °C (F04).
        Clock: driver polls at 1 000 µs intervals; Data_Ready set at 15 500 µs
        virtual time; first poll to observe it is at 16 000 µs.
        """
        clock, device, driver = make_integration_stack(temperature_raw=0x0C80)

        identity = driver.identify()
        driver.configure()
        measurement = driver.measure()

        print_trace(device)

        # Identity must confirm TMP117 part.
        assert identity.part_id == 0x117

        # Temperature: independent literal 25.0 °C.
        assert measurement.celsius == 25.0, (
            f"Expected 25.0 °C; got {measurement.celsius} °C"
        )

        # Raw bytes: independent literal 0x0C 0x80.
        assert measurement.raw_bytes == b"\x0C\x80", (
            f"Expected raw b'\\x0c\\x80'; got {measurement.raw_bytes.hex()}"
        )

        # Timing: driver polls at 1 000 µs steps; Data_Ready becomes available
        # at 15 500 µs; the first poll at or after that is 16 000 µs.
        assert measurement.virtual_time_us == 16_000, (
            f"Expected ready at 16 000 µs; got {measurement.virtual_time_us} µs"
        )

    def test_IT02_negative_temperature_minus1C(self):
        """
        Full driver flow with 0xFF80 fixture must produce -1.0 °C at 16 000 µs.

        Independent literal: 0xFF80 as signed 16-bit two's-complement = -128;
        -128 / 128 = -1.0 °C (F04).
        """
        clock, device, driver = make_integration_stack(temperature_raw=0xFF80)

        identity = driver.identify()
        driver.configure()
        measurement = driver.measure()

        print_trace(device)

        assert identity.part_id == 0x117

        # Temperature: independent literal -1.0 °C.
        assert measurement.celsius == -1.0, (
            f"Expected -1.0 °C; got {measurement.celsius} °C"
        )

        # Raw bytes: independent literal 0xFF 0x80.
        assert measurement.raw_bytes == b"\xFF\x80", (
            f"Expected raw b'\\xff\\x80'; got {measurement.raw_bytes.hex()}"
        )

        assert measurement.virtual_time_us == 16_000, (
            f"Expected ready at 16 000 µs; got {measurement.virtual_time_us} µs"
        )
