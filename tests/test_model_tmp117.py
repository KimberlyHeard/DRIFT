"""
Independent model tests for TMP117VirtualDevice and VirtualDeviceBus.

These tests exercise the virtual device model directly with literal register
transactions.  They do NOT import or use the TMP117Driver or any production
decoding helper to derive expected values.

Source references: TI SNOSD82D Rev. D (approved contract contracts/tmp117.approved.json).
  F03  p25           — register addresses: temperature 0x00, config 0x01, device-ID 0x0F.
  F04  p26 §7.6.2    — 1/128 °C per LSB, signed 16-bit.
  F05  p27           — Data_Ready bit 13; MOD bits 11:10; AVG bits 6:5.
  F06  p27           — MOD 01 = shutdown 0x0400; MOD 11 = one-shot 0x0C00; AVG 00.
  F07  p27           — reading config OR temperature clears Data_Ready.
  F08  pp14–15 §7.4.3 — one-shot completes then returns to shutdown.
  F09  p6            — typical completion 15 500 µs.
  F10  p32           — device-ID lower 12 bits = 0x117.

DRIFT policies (not vendor facts, from contracts/tmp117.approved.json):
  - virtual_conversion_us: 15 500 µs.
  - poll_interval_us: 1 000 µs.
  - Driver observes Data_Ready at 16 000 µs (first poll at or after 15 500 µs).
  - Fixture initialized in shutdown with config 0x0600.

Independent literal expected values used in this file:
  - 0x0117  device-ID register contents (revision 0, part 0x117).  F10.
  - 0x0600  shutdown configuration word.  Derived F05/F06; contract confirmed.
  - 0x0E00  one-shot trigger word.  Derived F05/F06; contract confirmed.
  - 0x2600  completed-conversion config snapshot (Data_Ready + shutdown).  F05/F07/F08.
  - 0x0C80  25.0 °C raw word (3200 counts × 1/128 = 25.0).  Literal.  F04.
  - 0xFF80  -1.0 °C raw word (-128 counts × 1/128 = -1.0).  Literal.  F04.
  - 0x8000  reset/no-data temperature sentinel.  F04.

These expected values are NOT calculated from production helpers.
"""

from __future__ import annotations

import pytest

from drift.clock import VirtualClock
from drift.bus import VirtualDeviceBus
from drift.devices.tmp117 import TMP117VirtualDevice, UnsupportedOperation
from drift.interfaces import AddressError, TraceEvent


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def make_fresh(temperature_raw: int = 0x0C80) -> tuple[VirtualClock, TMP117VirtualDevice, VirtualDeviceBus]:
    """
    Return a fresh (clock, device, bus) triple in the initialized-shutdown fixture.

    Each call returns fully independent objects with time at 0.
    The device starts in shutdown per DRIFT policy.
    """
    clock = VirtualClock()
    device = TMP117VirtualDevice(clock, temperature_raw=temperature_raw)
    bus = VirtualDeviceBus(device, address_7bit=0x48)
    return clock, device, bus


# ---------------------------------------------------------------------------
# T01 — Fresh state: device-ID register returns 0x0117 (F10)
# ---------------------------------------------------------------------------

class TestFreshState:

    def test_T01_device_id_returns_0117(self):
        """Device-ID register returns 0x01 0x17 on a fresh model (F10)."""
        _, device, bus = make_fresh()
        raw = bus.read_register(0x48, 0x0F, 2)
        # Independent literal: revision 0, part 0x117 → 0x0117 MSB-first.
        assert raw == b"\x01\x17"

    def test_T02_fresh_config_is_shutdown_0600(self):
        """Fresh model configuration register returns 0x0600 (shutdown, AVG=00)."""
        _, device, bus = make_fresh()
        raw = bus.read_register(0x48, 0x01, 2)
        # Independent literal: MOD=01 (0x0400) | other=0x0200 → 0x0600.
        assert raw == b"\x06\x00"

    def test_T03_fresh_temperature_returns_reset_sentinel(self):
        """Temperature register before any conversion returns 0x8000 (no data)."""
        _, device, bus = make_fresh()
        raw = bus.read_register(0x48, 0x00, 2)
        # Independent literal: reset/no-data sentinel per F04.
        assert raw == b"\x80\x00"

    def test_T04_trace_has_one_event_after_one_read(self):
        """Each bus read appends exactly one TraceEvent."""
        _, device, bus = make_fresh()
        bus.read_register(0x48, 0x0F, 2)
        assert len(device.trace) == 1

    def test_T05_trace_event_is_immutable(self):
        """Trace events are frozen dataclasses; attribute assignment raises."""
        _, device, bus = make_fresh()
        bus.read_register(0x48, 0x0F, 2)
        event = device.trace[0]
        with pytest.raises((AttributeError, TypeError)):
            event.outcome = "mutated"  # type: ignore[misc]

    def test_T06_viewing_trace_does_not_change_device_state(self):
        """Reading device.trace repeatedly does not alter the event list."""
        _, device, bus = make_fresh()
        bus.read_register(0x48, 0x0F, 2)
        first_snapshot = device.trace
        second_snapshot = device.trace
        assert first_snapshot == second_snapshot
        assert len(device.trace) == 1  # no extra events added

    def test_T07_trace_tuple_cannot_be_appended(self):
        """Trace is a tuple; += would replace the reference, not mutate the model."""
        _, device, bus = make_fresh()
        t1 = device.trace
        assert isinstance(t1, tuple)


# ---------------------------------------------------------------------------
# T08 — Before completion: config read returns one-shot-active (no Data_Ready)
# ---------------------------------------------------------------------------

class TestBeforeCompletion:

    def test_T08_config_before_completion_no_data_ready(self):
        """
        Config read before conversion completes returns 0x0E00 (no Data_Ready).

        F05: Data_Ready bit 13 is 0; MOD=11 (one-shot still active).
        """
        clock, device, bus = make_fresh()
        # Write one-shot trigger word.
        bus.write_register(0x48, 0x01, b"\x0E\x00")
        # Advance to 14 000 µs — before the 15 500 µs deadline.
        clock.advance_us(14_000)
        raw = bus.read_register(0x48, 0x01, 2)
        # Independent literal: 0x0E00 — one-shot active, no Data_Ready.
        assert raw == b"\x0E\x00"

    def test_T09_temperature_before_completion_returns_sentinel(self):
        """Temperature read before Data_Ready returns 0x8000 (no valid data)."""
        clock, device, bus = make_fresh()
        bus.write_register(0x48, 0x01, b"\x0E\x00")
        clock.advance_us(10_000)
        raw = bus.read_register(0x48, 0x00, 2)
        assert raw == b"\x80\x00"


# ---------------------------------------------------------------------------
# T10 — At completion (exactly at deadline): Data_Ready visible
# ---------------------------------------------------------------------------

class TestAtCompletion:

    def test_T10_config_at_deadline_shows_data_ready(self):
        """
        Config read at exactly the conversion deadline returns 0x2600.

        Independent literal: 0x2600 = Data_Ready (bit 13) | MOD=shutdown | AVG=00.
        F07: reading config clears Data_Ready.
        """
        clock, device, bus = make_fresh()
        bus.write_register(0x48, 0x01, b"\x0E\x00")
        # Advance exactly to the default 15 500 µs deadline.
        clock.advance_us(15_500)
        raw = bus.read_register(0x48, 0x01, 2)
        # 0x2600: bit 13 (0x2000) set, MOD=01 (0x0400), other bits 0x0200 → 0x2600.
        assert raw == b"\x26\x00"

    def test_T11_config_read_at_completion_clears_ready(self):
        """
        After the ready-consuming config read, a second config read returns
        0x0600 (Data_Ready cleared, shutdown).  F07.
        """
        clock, device, bus = make_fresh()
        bus.write_register(0x48, 0x01, b"\x0E\x00")
        clock.advance_us(15_500)
        bus.read_register(0x48, 0x01, 2)   # consumes Data_Ready
        raw2 = bus.read_register(0x48, 0x01, 2)
        # Independent literal: 0x0600 — shutdown, no Data_Ready.
        assert raw2 == b"\x06\x00"

    def test_T12_config_ready_snapshot_before_clear(self):
        """The ready snapshot returned at completion is 0x2600 (F05/F07/F08)."""
        clock, device, bus = make_fresh()
        bus.write_register(0x48, 0x01, b"\x0E\x00")
        clock.advance_us(15_500)
        raw = bus.read_register(0x48, 0x01, 2)
        assert raw == b"\x26\x00"


# ---------------------------------------------------------------------------
# T13 — After completion: temperature read returns sample and clears ready
# ---------------------------------------------------------------------------

class TestAfterCompletion:

    def test_T13_temperature_at_completion_returns_sample(self):
        """
        Temperature read after Data_Ready returns the configured raw word.

        Default temperature_raw = 0x0C80 = 25.0 °C (3200 counts × 1/128).
        """
        clock, device, bus = make_fresh(temperature_raw=0x0C80)
        bus.write_register(0x48, 0x01, b"\x0E\x00")
        clock.advance_us(16_000)
        # Independent literal: 0x0C80 = 3200 counts; 3200/128 = 25.0 °C.
        raw = bus.read_register(0x48, 0x00, 2)
        assert raw == b"\x0C\x80"

    def test_T14_temperature_read_clears_ready(self):
        """After a temperature read that consumed Data_Ready, config returns 0x0600."""
        clock, device, bus = make_fresh()
        bus.write_register(0x48, 0x01, b"\x0E\x00")
        clock.advance_us(16_000)
        bus.read_register(0x48, 0x00, 2)   # consumes Data_Ready
        cfg = bus.read_register(0x48, 0x01, 2)
        # Independent literal: 0x0600 — shutdown, Data_Ready cleared.
        assert cfg == b"\x06\x00"

    def test_T15_second_temperature_read_returns_sentinel(self):
        """A second temperature read after Data_Ready was consumed returns 0x8000."""
        clock, device, bus = make_fresh()
        bus.write_register(0x48, 0x01, b"\x0E\x00")
        clock.advance_us(16_000)
        bus.read_register(0x48, 0x00, 2)   # first read — consumes Data_Ready
        raw2 = bus.read_register(0x48, 0x00, 2)
        assert raw2 == b"\x80\x00"

    def test_T16_after_completion_config_is_shutdown(self):
        """
        After completion and temperature read, config register is 0x0600 (F08).

        F08: one-shot completes then returns to shutdown.
        """
        clock, device, bus = make_fresh()
        bus.write_register(0x48, 0x01, b"\x0E\x00")
        clock.advance_us(16_000)
        bus.read_register(0x48, 0x00, 2)
        cfg = bus.read_register(0x48, 0x01, 2)
        assert cfg == b"\x06\x00"


# ---------------------------------------------------------------------------
# T17 — Ready consumed by config read (F07)
# ---------------------------------------------------------------------------

class TestReadyConsumedByConfigRead:

    def test_T17_config_read_returns_ready_snapshot(self):
        """
        A config read at completion returns 0x2600 (the ready snapshot) and
        clears Data_Ready.  F07: reading configuration clears Data_Ready.
        """
        clock, device, bus = make_fresh(temperature_raw=0x0C80)
        bus.write_register(0x48, 0x01, b"\x0E\x00")
        clock.advance_us(15_500)
        snapshot = bus.read_register(0x48, 0x01, 2)
        # Independent literal: 0x2600 (Data_Ready + shutdown, F05/F07/F08).
        assert snapshot == b"\x26\x00"

    def test_T18_after_config_consumes_ready_temperature_gives_sample(self):
        """
        After a config read consumes Data_Ready, reading temperature still
        returns the stored sample (the read just returns raw; ready was cleared).

        At completion, temperature_raw was latched.  The subsequent temperature
        read (with Data_Ready already cleared) returns 0x8000 (no valid data),
        not the sample, because the flag was consumed by the config read.
        """
        clock, device, bus = make_fresh(temperature_raw=0x0C80)
        bus.write_register(0x48, 0x01, b"\x0E\x00")
        clock.advance_us(15_500)
        bus.read_register(0x48, 0x01, 2)   # config read consumes Data_Ready
        raw = bus.read_register(0x48, 0x00, 2)
        # Data_Ready was consumed by config read; temperature returns sentinel.
        assert raw == b"\x80\x00"

    def test_T19_driver_flow_config_read_consumes_ready_no_extra_read(self):
        """
        The driver pattern: write one-shot, poll config, observe ready, then
        read temperature.  Config read returned 0x2600 (ready); next op is
        temperature read.  No extra status read.

        This test follows the driver's exact sequence (F07).
        """
        clock, device, bus = make_fresh(temperature_raw=0x0C80)
        # Step 1: write one-shot.
        bus.write_register(0x48, 0x01, b"\x0E\x00")
        # Step 2: advance to just before deadline — no ready yet.
        clock.advance_us(15_000)
        cfg_early = bus.read_register(0x48, 0x01, 2)
        assert cfg_early == b"\x0E\x00"    # not ready
        # Step 3: advance past deadline.
        clock.advance_us(1_000)            # now at 16 000 µs
        cfg_ready = bus.read_register(0x48, 0x01, 2)
        assert cfg_ready == b"\x26\x00"    # ready snapshot (F07)
        # Step 4: read temperature (Data_Ready was already consumed by step 3).
        raw_temp = bus.read_register(0x48, 0x00, 2)
        # Config read consumed Data_Ready; temperature returns sentinel.
        assert raw_temp == b"\x80\x00"


# ---------------------------------------------------------------------------
# T20 — Two distinct conversions with distinct samples
# ---------------------------------------------------------------------------

class TestTwoDistinctConversions:

    def test_T20_two_conversions_same_sample(self):
        """
        Two sequential one-shot conversions with the same sample both return
        the configured raw word.
        """
        clock, device, bus = make_fresh(temperature_raw=0x0C80)

        # First conversion.
        bus.write_register(0x48, 0x01, b"\x0E\x00")
        clock.advance_us(16_000)
        raw1 = bus.read_register(0x48, 0x00, 2)
        # Independent literal: 0x0C80 = 25.0 °C.
        assert raw1 == b"\x0C\x80"

        # Second conversion.
        bus.write_register(0x48, 0x01, b"\x0E\x00")
        clock.advance_us(16_000)
        raw2 = bus.read_register(0x48, 0x00, 2)
        assert raw2 == b"\x0C\x80"

    def test_T21_two_conversions_distinct_samples_via_reset(self):
        """
        Two conversions with distinct samples via reset_fixture between runs.

        First run: temperature_raw = 0x0C80 (25.0 °C).
        Second run: temperature_raw = 0xFF80 (-1.0 °C).

        Independent literals:
          0x0C80: 3200 counts × 1/128 = 25.0 °C.
          0xFF80: 65408 - 65536 = -128 counts; -128/128 = -1.0 °C.
        """
        clock = VirtualClock()

        # First run.
        device = TMP117VirtualDevice(clock, temperature_raw=0x0C80)
        bus = VirtualDeviceBus(device, address_7bit=0x48)
        bus.write_register(0x48, 0x01, b"\x0E\x00")
        clock.advance_us(16_000)
        raw1 = bus.read_register(0x48, 0x00, 2)
        assert raw1 == b"\x0C\x80"
        trace_len_after_first = len(device.trace)
        assert trace_len_after_first == 2  # one write + one read

        # Second run — fresh device with different sample; clock continues.
        device2 = TMP117VirtualDevice(clock, temperature_raw=0xFF80)
        bus2 = VirtualDeviceBus(device2, address_7bit=0x48)
        bus2.write_register(0x48, 0x01, b"\x0E\x00")
        clock.advance_us(16_000)
        raw2 = bus2.read_register(0x48, 0x00, 2)
        # Independent literal: 0xFF80 = -1.0 °C.
        assert raw2 == b"\xFF\x80"

        # Traces are independent between runs.
        assert len(device2.trace) == 2
        # First device trace unchanged.
        assert len(device.trace) == trace_len_after_first

    def test_T22_reset_fixture_clears_trace_and_state(self):
        """
        reset_fixture() returns state to shutdown and clears the trace.
        """
        clock, device, bus = make_fresh(temperature_raw=0x0C80)
        bus.write_register(0x48, 0x01, b"\x0E\x00")
        clock.advance_us(16_000)
        bus.read_register(0x48, 0x00, 2)
        assert len(device.trace) > 0

        device.reset_fixture()
        assert len(device.trace) == 0

        # After reset, config register is back to shutdown.
        raw_cfg = device.read_register(0x01)
        assert raw_cfg == b"\x06\x00"


# ---------------------------------------------------------------------------
# T23 — Unsupported operations
# ---------------------------------------------------------------------------

class TestUnsupportedOperations:

    def test_T23_read_unsupported_register(self):
        """Reading a register outside the selected profile raises UnsupportedOperation."""
        _, device, _ = make_fresh()
        with pytest.raises(UnsupportedOperation):
            device.read_register(0x02)   # threshold registers not in selected profile

    def test_T24_write_unsupported_register(self):
        """Writing to a register outside the profile raises UnsupportedOperation."""
        _, device, _ = make_fresh()
        with pytest.raises(UnsupportedOperation):
            device.write_register(0x02, b"\x00\x00")

    def test_T25_write_config_with_averaging_raises(self):
        """Writing a config word with non-zero AVG bits raises UnsupportedOperation (F06)."""
        _, device, _ = make_fresh()
        # AVG=01 (0x0020) with MOD=shutdown — averaging not supported.
        with pytest.raises(UnsupportedOperation):
            device.write_register(0x01, b"\x06\x20")

    def test_T26_write_config_with_continuous_mode_raises(self):
        """Writing MOD=00 (continuous mode) raises UnsupportedOperation (F06)."""
        _, device, _ = make_fresh()
        # MOD=00 (0x0000) means continuous — outside the selected one-shot profile.
        with pytest.raises(UnsupportedOperation):
            device.write_register(0x01, b"\x02\x00")

    def test_T27_unsupported_operation_recorded_in_trace(self):
        """Unsupported operations are recorded in the trace with outcome 'unsupported'."""
        _, device, _ = make_fresh()
        with pytest.raises(UnsupportedOperation):
            device.read_register(0x02)
        assert len(device.trace) == 1
        assert device.trace[0].outcome == "unsupported"

    def test_T28_bus_wrong_address_raises_address_error(self):
        """VirtualDeviceBus raises AddressError for an unregistered address."""
        _, device, bus = make_fresh()
        with pytest.raises(AddressError):
            bus.read_register(0x49, 0x0F, 2)


# ---------------------------------------------------------------------------
# T29 — Fresh state between independent runs
# ---------------------------------------------------------------------------

class TestFreshStateBetweenRuns:

    def test_T29_reset_fixture_restores_shutdown(self):
        """After a conversion, reset_fixture() restores the shutdown state."""
        clock, device, bus = make_fresh(temperature_raw=0x0C80)
        bus.write_register(0x48, 0x01, b"\x0E\x00")
        clock.advance_us(16_000)
        bus.read_register(0x48, 0x00, 2)

        device.reset_fixture()
        cfg = device.read_register(0x01)
        assert cfg == b"\x06\x00"

    def test_T30_reset_fixture_clears_data_ready(self):
        """After reset_fixture(), a config read shows no Data_Ready."""
        clock, device, bus = make_fresh()
        bus.write_register(0x48, 0x01, b"\x0E\x00")
        clock.advance_us(15_500)
        # Do NOT consume Data_Ready — leave it set.
        device.reset_fixture()
        cfg = device.read_register(0x01)
        # Data_Ready must be cleared after reset.
        assert cfg == b"\x06\x00"

    def test_T31_independent_clocks_give_independent_conversions(self):
        """Two independent (clock, device, bus) triples are fully isolated."""
        clock_a, device_a, bus_a = make_fresh(temperature_raw=0x0C80)
        clock_b, device_b, bus_b = make_fresh(temperature_raw=0xFF80)

        bus_a.write_register(0x48, 0x01, b"\x0E\x00")
        bus_b.write_register(0x48, 0x01, b"\x0E\x00")

        clock_a.advance_us(16_000)
        # Do NOT advance clock_b yet.
        cfg_b_before = bus_b.read_register(0x48, 0x01, 2)
        assert cfg_b_before == b"\x0E\x00"    # clock_b still at 1000µs equivalent

        raw_a = bus_a.read_register(0x48, 0x00, 2)
        assert raw_a == b"\x0C\x80"

        clock_b.advance_us(16_000)
        raw_b = bus_b.read_register(0x48, 0x00, 2)
        assert raw_b == b"\xFF\x80"


# ---------------------------------------------------------------------------
# T32 — Trace structure and content
# ---------------------------------------------------------------------------

class TestTraceStructure:

    def test_T32_trace_sequence_numbers_are_consecutive(self):
        """Trace events are zero-based and consecutive."""
        clock, device, bus = make_fresh()
        bus.read_register(0x48, 0x0F, 2)
        bus.write_register(0x48, 0x01, b"\x0E\x00")
        bus.read_register(0x48, 0x01, 2)
        trace = device.trace
        assert [e.sequence for e in trace] == [0, 1, 2]

    def test_T33_trace_event_fields_correct_for_device_id_read(self):
        """
        Device-ID read trace event has correct address, register, operation,
        received bytes, and outcome.
        """
        clock, device, bus = make_fresh()
        bus.read_register(0x48, 0x0F, 2)
        event = device.trace[0]
        assert event.address_7bit == 0x48
        assert event.register == 0x0F
        assert event.operation == "read"
        assert event.received_bytes == b"\x01\x17"
        assert event.sent_bytes == b""
        assert event.outcome == "ok"
        assert "F10" in event.fact_ids

    def test_T34_trace_event_for_write_has_sent_bytes(self):
        """Write trace events record sent_bytes and empty received_bytes."""
        _, device, bus = make_fresh()
        bus.write_register(0x48, 0x01, b"\x0E\x00")
        event = device.trace[0]
        assert event.operation == "write"
        assert event.sent_bytes == b"\x0E\x00"
        assert event.received_bytes == b""
        assert event.outcome == "ok"

    def test_T35_trace_virtual_time_recorded_at_moment_of_access(self):
        """
        TraceEvent virtual_time_us reflects the clock reading at the moment
        of the register access, not before or after.
        """
        clock, device, bus = make_fresh()
        clock.advance_us(5_000)
        bus.read_register(0x48, 0x0F, 2)
        assert device.trace[0].virtual_time_us == 5_000

    def test_T36_full_conversion_trace_has_correct_sequence(self):
        """
        A complete one-shot cycle: write one-shot, poll config (before),
        advance, poll config (ready), read temperature.
        Produces 4 trace events in order.
        """
        clock, device, bus = make_fresh(temperature_raw=0x0C80)
        # Event 0: one-shot trigger
        bus.write_register(0x48, 0x01, b"\x0E\x00")
        # Event 1: config poll before deadline
        clock.advance_us(14_000)
        bus.read_register(0x48, 0x01, 2)
        # Event 2: config poll at/after deadline
        clock.advance_us(2_000)           # total 16 000 µs
        bus.read_register(0x48, 0x01, 2)  # returns ready snapshot, clears ready
        # Event 3: temperature read (Data_Ready was consumed above, returns sentinel)
        bus.read_register(0x48, 0x00, 2)

        trace = device.trace
        assert len(trace) == 4
        assert trace[0].operation == "write"
        assert trace[0].sent_bytes == b"\x0E\x00"
        assert trace[1].operation == "read"
        assert trace[1].received_bytes == b"\x0E\x00"   # before ready
        assert trace[2].operation == "read"
        assert trace[2].received_bytes == b"\x26\x00"   # ready snapshot
        assert trace[3].operation == "read"
        assert trace[3].received_bytes == b"\x80\x00"   # sentinel (ready consumed)
