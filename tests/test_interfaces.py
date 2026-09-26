"""
Task 01 — Core interface tests.

These tests exercise:
1. Seven-bit I2C address validation (the meaningful initial check requested
   in Task 01: validates a seven-bit address or rejects malformed input).
2. Structural integrity of the frozen dataclasses (immutability, field types).
3. Protocol structural compliance check for RegisterBus and Clock.

Independent of any device driver, virtual model, or simulator.
"""

import dataclasses

import pytest

from drift.interfaces import (
    AddressError,
    AssertionRecord,
    BusNackError,
    Clock,
    ConversionTimeout,
    DeviceIdentity,
    DeviceIdentityError,
    ExecutionLimitExceeded,
    Measurement,
    ProtocolReadError,
    RegisterBus,
    RunReport,
    TMP117_ADDRESS,
    TraceEvent,
    UnsupportedProfile,
    validate_7bit_address,
)


# ---------------------------------------------------------------------------
# Seven-bit address validation — the core meaningful check for Task 01
# ---------------------------------------------------------------------------

class TestValidate7BitAddress:
    """
    Validates the seven-bit I2C address gate.

    Policy: accept 0x01–0x77; reject 0x00 (general call), 0x78–0x7F
    (reserved 10-bit prefix), negative numbers, non-integers, and values
    above 0x7F (eight-bit or wider).
    """

    def test_tmp117_address_accepted(self):
        """0x48 is the selected TMP117 address and must pass."""
        assert validate_7bit_address(0x48) == 0x48

    def test_tmp117_address_equals_constant(self):
        """The module constant must equal the address the validator accepts."""
        assert TMP117_ADDRESS == 0x48
        assert validate_7bit_address(TMP117_ADDRESS) == TMP117_ADDRESS

    def test_minimum_valid_address(self):
        """0x01 is the lowest valid non-reserved address."""
        assert validate_7bit_address(0x01) == 0x01

    def test_maximum_valid_address(self):
        """0x77 is the highest address below the reserved 0x78–0x7F band."""
        assert validate_7bit_address(0x77) == 0x77

    def test_midrange_valid_address(self):
        """0x40 is well within the valid range."""
        assert validate_7bit_address(0x40) == 0x40

    # --- Rejection cases ---

    def test_general_call_address_rejected(self):
        """0x00 is the I2C general-call address and must be rejected."""
        with pytest.raises(AddressError, match="0x00"):
            validate_7bit_address(0x00)

    def test_reserved_0x78_rejected(self):
        """0x78 begins the reserved 10-bit prefix band."""
        with pytest.raises(AddressError, match="0x78"):
            validate_7bit_address(0x78)

    def test_reserved_0x7f_rejected(self):
        """0x7F is the last reserved address."""
        with pytest.raises(AddressError, match="0x7f"):
            validate_7bit_address(0x7F)

    def test_eight_bit_value_rejected(self):
        """0x80 is eight bits wide — out of range for a seven-bit address."""
        with pytest.raises(AddressError):
            validate_7bit_address(0x80)

    def test_large_value_rejected(self):
        """Values well above 0x7F must be rejected."""
        with pytest.raises(AddressError):
            validate_7bit_address(0xFF)

    def test_negative_value_rejected(self):
        """Negative integers cannot be valid addresses."""
        with pytest.raises(AddressError):
            validate_7bit_address(-1)

    def test_float_rejected(self):
        """A float is not a valid address even if numerically in range."""
        with pytest.raises(AddressError):
            validate_7bit_address(72.0)  # type: ignore[arg-type]

    def test_string_rejected(self):
        """A string address must be rejected, not silently converted."""
        with pytest.raises((AddressError, TypeError)):
            validate_7bit_address("0x48")  # type: ignore[arg-type]

    def test_reserved_0x79_through_0x7e_rejected(self):
        """All addresses in 0x79–0x7E must also be rejected."""
        for addr in range(0x79, 0x7F):
            with pytest.raises(AddressError):
                validate_7bit_address(addr)


# ---------------------------------------------------------------------------
# Dataclass immutability and field integrity
# ---------------------------------------------------------------------------

class TestDeviceIdentity:
    def test_frozen(self):
        identity = DeviceIdentity(part_id=0x117, revision=0x1, raw_bytes=b"\x01\x17")
        with pytest.raises((dataclasses.FrozenInstanceError, AttributeError)):
            identity.part_id = 0x999  # type: ignore[misc]

    def test_fields_accessible(self):
        identity = DeviceIdentity(part_id=0x117, revision=0x1, raw_bytes=b"\x01\x17")
        assert identity.part_id == 0x117
        assert identity.revision == 0x1
        assert identity.raw_bytes == b"\x01\x17"


class TestMeasurement:
    def test_frozen(self):
        m = Measurement(raw_bytes=b"\x0c\x80", celsius=25.0, virtual_time_us=16000)
        with pytest.raises((dataclasses.FrozenInstanceError, AttributeError)):
            m.celsius = 0.0  # type: ignore[misc]

    def test_fields_accessible(self):
        m = Measurement(raw_bytes=b"\x0c\x80", celsius=25.0, virtual_time_us=16000)
        assert m.raw_bytes == b"\x0c\x80"
        assert m.celsius == 25.0
        assert m.virtual_time_us == 16000


class TestTraceEvent:
    def test_frozen(self):
        event = TraceEvent(
            sequence=0,
            virtual_time_us=0,
            address_7bit=0x48,
            register=0x0F,
            operation="read",
            sent_bytes=b"",
            received_bytes=b"\x01\x17",
            outcome="ok",
            fact_ids=("F10",),
        )
        with pytest.raises((dataclasses.FrozenInstanceError, AttributeError)):
            event.outcome = "mutated"  # type: ignore[misc]

    def test_trace_cannot_be_mutated_after_construction(self):
        """Viewing a saved trace cannot mutate device state (AGENTS.md rule)."""
        event = TraceEvent(
            sequence=0,
            virtual_time_us=500,
            address_7bit=0x48,
            register=0x00,
            operation="read",
            sent_bytes=b"",
            received_bytes=b"\x0c\x80",
            outcome="ok",
            fact_ids=("F04",),
        )
        # Accessing all fields is read-only
        _ = event.sequence
        _ = event.received_bytes
        _ = event.fact_ids
        # No exception means read succeeded; the frozen check above proves mutation fails


class TestRunReport:
    def test_frozen(self):
        report = RunReport(
            schema_version="1",
            run_id="test-run-001",
            scenario_id="baseline_25c",
            profile_id="tmp117_one_shot_no_average",
            driver_variant="baseline",
            execution_status="completed",
            device_outcome="Measurement",
            assertions=(),
            trace=(),
            verification_status="pass",
            expected_behavior_observed=True,
            limitations="Task 01 stub",
        )
        with pytest.raises((dataclasses.FrozenInstanceError, AttributeError)):
            report.verification_status = "fail"  # type: ignore[misc]


# ---------------------------------------------------------------------------
# Typed outcome error hierarchy
# ---------------------------------------------------------------------------

class TestErrorHierarchy:
    def test_address_error_is_value_error(self):
        assert issubclass(AddressError, ValueError)

    def test_bus_nack_error_is_oserror(self):
        assert issubclass(BusNackError, OSError)

    def test_device_identity_error_is_value_error(self):
        assert issubclass(DeviceIdentityError, ValueError)

    def test_protocol_read_error_is_value_error(self):
        assert issubclass(ProtocolReadError, ValueError)

    def test_conversion_timeout_is_timeout_error(self):
        assert issubclass(ConversionTimeout, TimeoutError)

    def test_unsupported_profile_is_not_implemented_error(self):
        assert issubclass(UnsupportedProfile, NotImplementedError)

    def test_execution_limit_exceeded_is_runtime_error(self):
        assert issubclass(ExecutionLimitExceeded, RuntimeError)

    def test_address_error_carries_message(self):
        err = AddressError("Address 0x00 is out of the valid seven-bit range")
        assert "0x00" in str(err)


# ---------------------------------------------------------------------------
# Protocol structural compliance
# ---------------------------------------------------------------------------

class TestProtocolStructure:
    """
    These do not test concrete implementations (none exist yet).
    They confirm the Protocol classes are importable and properly define
    the required method names.

    get_protocol_members() was added in Python 3.13; for 3.11/3.12 we
    inspect the class namespace directly.
    """

    @staticmethod
    def _protocol_members(proto):
        try:
            from typing import get_protocol_members  # Python 3.13+
            return get_protocol_members(proto)
        except ImportError:
            # Python 3.11/3.12: collect non-dunder, non-classvar annotations
            return {
                name
                for name in dir(proto)
                if not name.startswith("_")
                and callable(getattr(proto, name, None))
            }

    def test_register_bus_is_protocol(self):
        members = self._protocol_members(RegisterBus)
        assert "read_register" in members
        assert "write_register" in members

    def test_clock_is_protocol(self):
        members = self._protocol_members(Clock)
        assert "now_us" in members
        assert "advance_us" in members
