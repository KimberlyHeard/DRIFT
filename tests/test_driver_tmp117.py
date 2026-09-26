"""
TMP117 driver tests using ScriptedBus and StepClock.

All expected bytes and numeric values are literal constants reviewed independently
of the production decoder and driver.  Never import the driver or decoder to
compute expected answers.

Source facts referenced (TI SNOSD82D Rev. D):
  F01  p21   selected address 0x48.
  F02  p20   MSB first.
  F03  p25   temp=0x00, config=0x01, device-ID=0x0F.
  F05  p27   Data_Ready bit 13 (0x2000), MOD bits 11:10, AVG bits 6:5.
  F06  p27   MOD 01 = shutdown (0x0400), MOD 11 = one-shot (0x0C00), AVG 00.
  F07  p27   reading config or temperature clears Data_Ready.
  F08  pp14–15 §7.4.3  one-shot returns to shutdown after completion.
  F10  p32   device-ID lower 12 bits = 0x117; upper 4 bits = revision.

DRIFT policies:
  timeout = 100 000 µs; poll interval = 1 000 µs.

Literal configuration words (independently derived from the above facts
and confirmed by contracts/tmp117.approved.json derived_candidates):
  shutdown config   = 0x0600  → bytes b"\\x06\\x00"
  one-shot config   = 0x0E00  → bytes b"\\x0E\\x00"
  completed config  = 0x2600  → bytes b"\\x26\\x00"  (Data_Ready | shutdown)

Literal temperature values:
  25 °C  = 0x0C80 (3200/128) → bytes b"\\x0C\\x80"
  -1 °C  = 0xFF80 ((65408-65536)/128) → bytes b"\\xFF\\x80"
"""

from __future__ import annotations

import pytest

from drift.bus import ScriptedBus, ScriptedBusExhausted, ScriptedBusStepMismatch
from drift.clock import StepClock
from drift.drivers.tmp117 import TMP117Driver
from drift.interfaces import (
    BusNackError,
    ConversionTimeout,
    DeviceIdentityError,
    ProtocolReadError,
)

# ---------------------------------------------------------------------------
# Literal test constants — must not be derived from driver or decoder
# ---------------------------------------------------------------------------

_ADDR: int = 0x48           # selected I2C address (F01)

# Register addresses (F03)
_REG_TEMP: int = 0x00
_REG_CONFIG: int = 0x01
_REG_ID: int = 0x0F

# Configuration words (F05/F06, confirmed by approved contract)
_CFG_SHUTDOWN: bytes = b"\x06\x00"    # 0x0600 shutdown, AVG=00
_CFG_ONE_SHOT: bytes = b"\x0E\x00"    # 0x0E00 one-shot, AVG=00
_CFG_READY: bytes = b"\x26\x00"       # 0x2600 Data_Ready | shutdown (F05/F08)
_CFG_NOT_READY: bytes = b"\x0E\x00"   # 0x0E00 still converting, no ready bit

# Device-ID bytes — literal; lower 12 bits = 0x117 (F10)
_DEV_ID_REV0: bytes = b"\x01\x17"     # 0x0117  revision nibble = 0
_DEV_ID_REV1: bytes = b"\x11\x17"     # 0x1117  revision nibble = 1
_DEV_ID_REVA: bytes = b"\xA1\x17"     # 0xA117  revision nibble = 0xA
_DEV_ID_WRONG: bytes = b"\x02\x18"    # 0x0218  wrong part — lower 12 = 0x218

# Temperature raw bytes (F04, independently verified)
_TEMP_25C: bytes = b"\x0C\x80"        # 0x0C80 → 3200 / 128 = 25.0 °C
_TEMP_NEG1C: bytes = b"\xFF\x80"      # 0xFF80 → (65408-65536)/128 = -1.0 °C


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_driver(bus: ScriptedBus, clock: StepClock | None = None) -> TMP117Driver:
    if clock is None:
        clock = StepClock(0)
    return TMP117Driver(bus=bus, clock=clock, address_7bit=_ADDR)


# ===========================================================================
# ScriptedBus unit tests
# ===========================================================================

class TestScriptedBus:
    """Verify the ScriptedBus itself behaves correctly."""

    def test_TB01_read_returns_scripted_bytes(self) -> None:
        bus = ScriptedBus([ScriptedBus.step_read(_ADDR, _REG_ID, _DEV_ID_REV0)])
        result = bus.read_register(_ADDR, _REG_ID, 2)
        assert result == _DEV_ID_REV0

    def test_TB02_write_succeeds_matching_payload(self) -> None:
        bus = ScriptedBus([ScriptedBus.step_write(_ADDR, _REG_CONFIG, _CFG_SHUTDOWN)])
        bus.write_register(_ADDR, _REG_CONFIG, _CFG_SHUTDOWN)
        bus.assert_exhausted()

    def test_TB03_write_mismatch_raises(self) -> None:
        bus = ScriptedBus([ScriptedBus.step_write(_ADDR, _REG_CONFIG, _CFG_SHUTDOWN)])
        with pytest.raises(ScriptedBusStepMismatch):
            bus.write_register(_ADDR, _REG_CONFIG, _CFG_ONE_SHOT)

    def test_TB04_extra_call_raises_exhausted(self) -> None:
        bus = ScriptedBus([ScriptedBus.step_read(_ADDR, _REG_ID, _DEV_ID_REV0)])
        bus.read_register(_ADDR, _REG_ID, 2)
        with pytest.raises(ScriptedBusExhausted):
            bus.read_register(_ADDR, _REG_ID, 2)

    def test_TB05_assert_exhausted_raises_if_steps_remain(self) -> None:
        bus = ScriptedBus([ScriptedBus.step_read(_ADDR, _REG_ID, _DEV_ID_REV0)])
        with pytest.raises(AssertionError):
            bus.assert_exhausted()

    def test_TB06_operation_mismatch_raises(self) -> None:
        bus = ScriptedBus([ScriptedBus.step_read(_ADDR, _REG_CONFIG, _CFG_SHUTDOWN)])
        with pytest.raises(ScriptedBusStepMismatch):
            bus.write_register(_ADDR, _REG_CONFIG, _CFG_SHUTDOWN)

    def test_TB07_nack_on_read_raises_bus_nack(self) -> None:
        bus = ScriptedBus([ScriptedBus.step_read(_ADDR, _REG_ID, b"", nack=True)])
        with pytest.raises(BusNackError):
            bus.read_register(_ADDR, _REG_ID, 2)

    def test_TB08_nack_on_write_raises_bus_nack(self) -> None:
        bus = ScriptedBus([ScriptedBus.step_write(_ADDR, _REG_CONFIG, _CFG_SHUTDOWN, nack=True)])
        with pytest.raises(BusNackError):
            bus.write_register(_ADDR, _REG_CONFIG, _CFG_SHUTDOWN)

    def test_TB09_register_mismatch_raises(self) -> None:
        bus = ScriptedBus([ScriptedBus.step_read(_ADDR, _REG_TEMP, _TEMP_25C)])
        with pytest.raises(ScriptedBusStepMismatch):
            bus.read_register(_ADDR, _REG_CONFIG, 2)

    def test_TB10_steps_remaining_count(self) -> None:
        bus = ScriptedBus([
            ScriptedBus.step_read(_ADDR, _REG_ID, _DEV_ID_REV0),
            ScriptedBus.step_write(_ADDR, _REG_CONFIG, _CFG_SHUTDOWN),
        ])
        assert bus.steps_remaining == 2
        bus.read_register(_ADDR, _REG_ID, 2)
        assert bus.steps_remaining == 1


# ===========================================================================
# StepClock unit tests
# ===========================================================================

class TestStepClock:
    """Verify the StepClock behaves correctly."""

    def test_TC01_initial_time_zero(self) -> None:
        clock = StepClock()
        assert clock.now_us() == 0

    def test_TC02_initial_time_nonzero(self) -> None:
        clock = StepClock(5000)
        assert clock.now_us() == 5000

    def test_TC03_advance_increments_time(self) -> None:
        clock = StepClock()
        clock.advance_us(1000)
        assert clock.now_us() == 1000

    def test_TC04_multiple_advances_cumulative(self) -> None:
        clock = StepClock()
        clock.advance_us(1000)
        clock.advance_us(2000)
        assert clock.now_us() == 3000

    def test_TC05_advance_zero_raises(self) -> None:
        clock = StepClock()
        with pytest.raises(ValueError):
            clock.advance_us(0)

    def test_TC06_advance_negative_raises(self) -> None:
        clock = StepClock()
        with pytest.raises(ValueError):
            clock.advance_us(-1)

    def test_TC07_negative_start_raises(self) -> None:
        with pytest.raises(ValueError):
            StepClock(-1)


# ===========================================================================
# identify() tests
# ===========================================================================

class TestIdentify:
    """Driver identify() against scripted bus."""

    def test_TI01_revision_zero_returns_correct_identity(self) -> None:
        # Raw 0x0117: part_id lower-12 = 0x117, revision = 0 (F10)
        bus = ScriptedBus([ScriptedBus.step_read(_ADDR, _REG_ID, _DEV_ID_REV0)])
        driver = _make_driver(bus)
        identity = driver.identify()
        assert identity.part_id == 0x117
        assert identity.revision == 0
        assert identity.raw_bytes == _DEV_ID_REV0
        bus.assert_exhausted()

    def test_TI02_revision_one_accepted(self) -> None:
        # Raw 0x1117: revision nibble = 1 (any revision accepted per F10)
        bus = ScriptedBus([ScriptedBus.step_read(_ADDR, _REG_ID, _DEV_ID_REV1)])
        driver = _make_driver(bus)
        identity = driver.identify()
        assert identity.part_id == 0x117
        assert identity.revision == 1
        bus.assert_exhausted()

    def test_TI03_revision_0xA_accepted(self) -> None:
        # Raw 0xA117: revision nibble = 0xA
        bus = ScriptedBus([ScriptedBus.step_read(_ADDR, _REG_ID, _DEV_ID_REVA)])
        driver = _make_driver(bus)
        identity = driver.identify()
        assert identity.part_id == 0x117
        assert identity.revision == 0xA
        bus.assert_exhausted()

    def test_TI04_wrong_part_id_raises_device_identity_error(self) -> None:
        # Raw 0x0218: lower-12 = 0x218, not 0x117 → DeviceIdentityError (F10)
        bus = ScriptedBus([ScriptedBus.step_read(_ADDR, _REG_ID, _DEV_ID_WRONG)])
        driver = _make_driver(bus)
        with pytest.raises(DeviceIdentityError):
            driver.identify()

    def test_TI05_nack_on_identity_read_raises_bus_nack(self) -> None:
        bus = ScriptedBus([ScriptedBus.step_read(_ADDR, _REG_ID, b"", nack=True)])
        driver = _make_driver(bus)
        with pytest.raises(BusNackError):
            driver.identify()

    def test_TI06_raw_bytes_preserved_in_identity(self) -> None:
        bus = ScriptedBus([ScriptedBus.step_read(_ADDR, _REG_ID, _DEV_ID_REV1)])
        driver = _make_driver(bus)
        identity = driver.identify()
        assert identity.raw_bytes == _DEV_ID_REV1

    def test_TI07_address_0x48_used_for_read(self) -> None:
        # The scripted bus will raise ScriptedBusStepMismatch if wrong address is used.
        bus = ScriptedBus([ScriptedBus.step_read(0x48, _REG_ID, _DEV_ID_REV0)])
        driver = _make_driver(bus)
        identity = driver.identify()
        assert identity.part_id == 0x117
        bus.assert_exhausted()


# ===========================================================================
# configure() tests
# ===========================================================================

class TestConfigure:
    """Driver configure() writes shutdown config to register 0x01."""

    def test_TC01_configure_writes_shutdown_config(self) -> None:
        # configure() must write 0x0600 (shutdown, AVG=00) to reg 0x01 (F03/F06)
        bus = ScriptedBus([ScriptedBus.step_write(_ADDR, _REG_CONFIG, _CFG_SHUTDOWN)])
        driver = _make_driver(bus)
        driver.configure()
        bus.assert_exhausted()

    def test_TC02_configure_writes_exactly_two_bytes(self) -> None:
        # The write payload must be exactly b"\x06\x00" (2 bytes MSB first, F02)
        bus = ScriptedBus([ScriptedBus.step_write(_ADDR, _REG_CONFIG, _CFG_SHUTDOWN)])
        driver = _make_driver(bus)
        driver.configure()
        bus.assert_exhausted()

    def test_TC03_configure_issues_single_write_only(self) -> None:
        # Only one bus operation expected; extra calls would raise ScriptedBusExhausted.
        bus = ScriptedBus([ScriptedBus.step_write(_ADDR, _REG_CONFIG, _CFG_SHUTDOWN)])
        driver = _make_driver(bus)
        driver.configure()
        # Confirm nothing extra was issued
        assert bus.steps_remaining == 0

    def test_TC04_configure_nack_raises_bus_nack(self) -> None:
        bus = ScriptedBus([
            ScriptedBus.step_write(_ADDR, _REG_CONFIG, _CFG_SHUTDOWN, nack=True)
        ])
        driver = _make_driver(bus)
        with pytest.raises(BusNackError):
            driver.configure()


# ===========================================================================
# measure() tests
# ===========================================================================

class TestMeasure:
    """Driver measure() scripted bus tests."""

    def test_TM01_ready_after_one_poll_25c(self) -> None:
        """
        Fixture: already in shutdown (0x0600).
        measure() writes one-shot (0x0E00), then polls once; poll returns ready
        (0x2600 = Data_Ready | shutdown).  The single configuration read
        consumes Data_Ready (F07); no extra config read issued.
        Then reads temperature register returning 0x0C80 = 25 °C (F04).

        Transaction sequence:
          write reg 0x01  b"\\x0E\\x00"  (one-shot trigger)
          read  reg 0x01  b"\\x26\\x00"  (config poll — returns ready)
          read  reg 0x00  b"\\x0C\\x80"  (temperature read)

        Literal: 25 °C = 0x0C80 = 3200/128 — verified independently.
        """
        bus = ScriptedBus([
            ScriptedBus.step_write(_ADDR, _REG_CONFIG, _CFG_ONE_SHOT),
            ScriptedBus.step_read(_ADDR, _REG_CONFIG, _CFG_READY),
            ScriptedBus.step_read(_ADDR, _REG_TEMP, _TEMP_25C),
        ])
        clock = StepClock(0)
        driver = _make_driver(bus, clock)
        result = driver.measure()
        assert result.raw_bytes == _TEMP_25C
        assert result.celsius == 25.0          # literal: 3200/128 = 25.0
        assert result.virtual_time_us == 1000  # one poll × 1000 µs
        bus.assert_exhausted()

    def test_TM02_ready_after_one_poll_neg1c(self) -> None:
        """
        Temperature -1 °C: raw 0xFF80 = (65408-65536)/128 = -1.0 °C.
        Verified independently; see test module header.
        """
        bus = ScriptedBus([
            ScriptedBus.step_write(_ADDR, _REG_CONFIG, _CFG_ONE_SHOT),
            ScriptedBus.step_read(_ADDR, _REG_CONFIG, _CFG_READY),
            ScriptedBus.step_read(_ADDR, _REG_TEMP, _TEMP_NEG1C),
        ])
        driver = _make_driver(bus, StepClock(0))
        result = driver.measure()
        assert result.raw_bytes == _TEMP_NEG1C
        assert result.celsius == -1.0           # literal: -128/128 = -1.0
        bus.assert_exhausted()

    def test_TM03_waiting_two_polls_before_ready(self) -> None:
        """
        First poll returns not-ready (0x0E00, no Data_Ready bit).
        Second poll returns ready (0x2600).
        Temperature: 25 °C.
        virtual_time_us after two 1000 µs polls = 2000 µs.
        """
        bus = ScriptedBus([
            ScriptedBus.step_write(_ADDR, _REG_CONFIG, _CFG_ONE_SHOT),
            ScriptedBus.step_read(_ADDR, _REG_CONFIG, _CFG_NOT_READY),  # poll 1 — not ready
            ScriptedBus.step_read(_ADDR, _REG_CONFIG, _CFG_READY),       # poll 2 — ready
            ScriptedBus.step_read(_ADDR, _REG_TEMP, _TEMP_25C),
        ])
        clock = StepClock(0)
        driver = _make_driver(bus, clock)
        result = driver.measure()
        assert result.celsius == 25.0
        assert result.virtual_time_us == 2000   # two polls × 1000 µs
        bus.assert_exhausted()

    def test_TM04_timeout_raises_conversion_timeout(self) -> None:
        """
        All polls return not-ready; ConversionTimeout raised.
        Timeout is 3000 µs (3 polls).  All three return 0x0E00.

        Note: the driver polls in a bounded loop; at most
        timeout_us // 1000 + 2 = 5 polls here.  We script three
        not-ready responses followed by the script running out — the
        driver will raise ConversionTimeout from deadline logic.
        """
        # Provide just enough not-ready responses to fill the 3000 µs window:
        # 3 polls of 1000 µs; after the 3rd advance, now_us = 3000 = deadline,
        # the loop body checks now_us > deadline before reading, so 3 polls execute.
        not_ready_steps = [
            ScriptedBus.step_write(_ADDR, _REG_CONFIG, _CFG_ONE_SHOT),
            ScriptedBus.step_read(_ADDR, _REG_CONFIG, _CFG_NOT_READY),  # t=1000
            ScriptedBus.step_read(_ADDR, _REG_CONFIG, _CFG_NOT_READY),  # t=2000
            ScriptedBus.step_read(_ADDR, _REG_CONFIG, _CFG_NOT_READY),  # t=3000
        ]
        bus = ScriptedBus(not_ready_steps)
        clock = StepClock(0)
        driver = _make_driver(bus, clock)
        with pytest.raises(ConversionTimeout):
            driver.measure(timeout_us=3000)

    def test_TM05_ready_observation_not_followed_by_extra_config_read(self) -> None:
        """
        F07: reading configuration clears Data_Ready.
        Once a config read returns ready, the next operation must be the
        temperature read, not another config read.  The scripted bus enforces
        this — if the driver issued an extra config read it would hit a
        write step and raise ScriptedBusStepMismatch.
        """
        bus = ScriptedBus([
            ScriptedBus.step_write(_ADDR, _REG_CONFIG, _CFG_ONE_SHOT),
            ScriptedBus.step_read(_ADDR, _REG_CONFIG, _CFG_READY),
            ScriptedBus.step_read(_ADDR, _REG_TEMP, _TEMP_25C),
        ])
        clock = StepClock(0)
        driver = _make_driver(bus, clock)
        result = driver.measure()
        assert result.raw_bytes == _TEMP_25C
        bus.assert_exhausted()

    def test_TM06_virtual_time_recorded_at_ready_observation(self) -> None:
        """
        Two not-ready polls, then ready.
        Clock starts at 5000 µs; after two polls = 7000 µs, after third = 8000 µs
        when ready is seen; virtual_time_us must be 8000.
        """
        bus = ScriptedBus([
            ScriptedBus.step_write(_ADDR, _REG_CONFIG, _CFG_ONE_SHOT),
            ScriptedBus.step_read(_ADDR, _REG_CONFIG, _CFG_NOT_READY),  # t=6000
            ScriptedBus.step_read(_ADDR, _REG_CONFIG, _CFG_NOT_READY),  # t=7000
            ScriptedBus.step_read(_ADDR, _REG_CONFIG, _CFG_READY),       # t=8000
            ScriptedBus.step_read(_ADDR, _REG_TEMP, _TEMP_25C),
        ])
        clock = StepClock(5000)
        driver = _make_driver(bus, clock)
        result = driver.measure()
        assert result.virtual_time_us == 8000
        bus.assert_exhausted()

    def test_TM07_nack_on_one_shot_write_raises_bus_nack(self) -> None:
        bus = ScriptedBus([
            ScriptedBus.step_write(_ADDR, _REG_CONFIG, _CFG_ONE_SHOT, nack=True)
        ])
        driver = _make_driver(bus, StepClock(0))
        with pytest.raises(BusNackError):
            driver.measure()

    def test_TM08_nack_on_config_poll_raises_bus_nack(self) -> None:
        bus = ScriptedBus([
            ScriptedBus.step_write(_ADDR, _REG_CONFIG, _CFG_ONE_SHOT),
            ScriptedBus.step_read(_ADDR, _REG_CONFIG, b"", nack=True),
        ])
        driver = _make_driver(bus, StepClock(0))
        with pytest.raises(BusNackError):
            driver.measure()

    def test_TM09_nack_on_temperature_read_raises_bus_nack(self) -> None:
        bus = ScriptedBus([
            ScriptedBus.step_write(_ADDR, _REG_CONFIG, _CFG_ONE_SHOT),
            ScriptedBus.step_read(_ADDR, _REG_CONFIG, _CFG_READY),
            ScriptedBus.step_read(_ADDR, _REG_TEMP, b"", nack=True),
        ])
        driver = _make_driver(bus, StepClock(0))
        with pytest.raises(BusNackError):
            driver.measure()

    def test_TM10_two_consecutive_conversions(self) -> None:
        """
        Two sequential calls to measure() on the same driver instance.
        First conversion: 25 °C; second conversion: -1 °C.
        Each produces an independent transaction sequence.
        virtual_time_us of second result = 2000 (one poll, clock continues from 1000).
        """
        bus = ScriptedBus([
            # First measure()
            ScriptedBus.step_write(_ADDR, _REG_CONFIG, _CFG_ONE_SHOT),
            ScriptedBus.step_read(_ADDR, _REG_CONFIG, _CFG_READY),
            ScriptedBus.step_read(_ADDR, _REG_TEMP, _TEMP_25C),
            # Second measure() — clock continues from t=1000
            ScriptedBus.step_write(_ADDR, _REG_CONFIG, _CFG_ONE_SHOT),
            ScriptedBus.step_read(_ADDR, _REG_CONFIG, _CFG_READY),
            ScriptedBus.step_read(_ADDR, _REG_TEMP, _TEMP_NEG1C),
        ])
        clock = StepClock(0)
        driver = _make_driver(bus, clock)

        first = driver.measure()
        assert first.celsius == 25.0
        assert first.virtual_time_us == 1000

        second = driver.measure()
        assert second.celsius == -1.0
        assert second.virtual_time_us == 2000   # clock continues: 1000 + 1000 = 2000

        bus.assert_exhausted()


# ===========================================================================
# Full identify + configure + measure sequence
# ===========================================================================

class TestFullSequence:
    """
    One-shot identify → configure → measure scripted sequence.

    This demonstrates the complete transaction sequence in the Task 04 spec:
    a realistic interaction showing identify, shutdown fixture write, then
    one-shot measurement.
    """

    def test_TS01_identify_configure_measure_25c(self) -> None:
        """
        Complete single-device session:
          identify  → read  reg 0x0F → 0x0117 (rev 0)
          configure → write reg 0x01 → 0x0600 (shutdown fixture)
          measure   → write reg 0x01 → 0x0E00 (one-shot)
                   → read  reg 0x01 → 0x2600 (ready)
                   → read  reg 0x00 → 0x0C80 (25 °C)
        """
        bus = ScriptedBus([
            ScriptedBus.step_read(_ADDR, _REG_ID, _DEV_ID_REV0),      # identify
            ScriptedBus.step_write(_ADDR, _REG_CONFIG, _CFG_SHUTDOWN), # configure
            ScriptedBus.step_write(_ADDR, _REG_CONFIG, _CFG_ONE_SHOT), # measure step 1
            ScriptedBus.step_read(_ADDR, _REG_CONFIG, _CFG_READY),     # measure step 2
            ScriptedBus.step_read(_ADDR, _REG_TEMP, _TEMP_25C),        # measure step 3
        ])
        clock = StepClock(0)
        driver = _make_driver(bus, clock)

        identity = driver.identify()
        assert identity.part_id == 0x117
        assert identity.revision == 0

        driver.configure()

        result = driver.measure()
        assert result.celsius == 25.0
        assert result.virtual_time_us == 1000

        bus.assert_exhausted()
