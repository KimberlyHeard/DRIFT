"""
Task 06 fault-scenario and runner tests.

Covers:
  FR01  FaultBus NACK on identity read → driver raises BusNackError.
  FR02  FaultBus never-ready → driver raises ConversionTimeout.
  FR03  FaultBus wrong ID bits → driver raises DeviceIdentityError.
  FR04  FaultBus short temperature read → driver raises ProtocolReadError.
  FR05  Byte-swap driver on 25.0 °C fixture → celsius ≠ 25.0 (FAIL report).
  FR06  Byte-swap driver: raw_bytes preserved as original (0x0c80).
  FR07  execute_scenario baseline_25c → PASS, celsius == 25.0.
  FR08  execute_scenario baseline_neg1c → PASS, celsius == −1.0.
  FR09  execute_scenario fault_nack_identity → PASS (exception observed).
  FR10  execute_scenario fault_never_ready → PASS (timeout observed).
  FR11  execute_scenario fault_wrong_id_bits → PASS (identity error observed).
  FR12  execute_scenario fault_short_temp → PASS (protocol error observed).
  FR13  Runner rejects unknown profile.
  FR14  Runner rejects unknown scenario.
  FR15  Runner rejects invalid driver/scenario combination.
  FR16  Fault trace records injected outcome label.
  FR17  Deterministic replay: five identical baseline_25c runs produce
        identical normalised report dicts.
  FR18  build_report baseline_25c: verification_status == "pass".
  FR19  build_report byte_swap: verification_status == "fail".
  FR20  Fault scenarios: execution_status == "completed", not "infrastructure_error".

Independent expected values (literal, not derived from production code):
  - 25.0 °C: 0x0C80 = 3200 counts; 3200 / 128 = 25.0   (F04, SNOSD82D p26)
  - −1.0 °C: 0xFF80 signed = −128; −128 / 128 = −1.0   (F04)
  - byte-swap of 0x0C80: bytes [0x80, 0x0C] = 0x800C;
    0x800C as signed16 = 0x800C − 0x10000 = −32756;
    −32756 / 128 = −255.90625 °C                         (STATUS.md)
"""

from __future__ import annotations

import pytest

from drift.bus import VirtualDeviceBus
from drift.clock import VirtualClock
from drift.devices.tmp117 import TMP117VirtualDevice
from drift.drivers.tmp117 import TMP117Driver
from drift.drivers.tmp117_variants import ByteSwapDriver
from drift.fault_bus import FaultBus, FaultSpec
from drift.interfaces import (
    BusNackError,
    ConversionTimeout,
    DeviceIdentityError,
    ProtocolReadError,
)
from drift.reporting import (
    build_report,
    build_verification_summary,
    normalise_for_replay,
    report_to_dict,
)
from drift.runner import execute_scenario, execute_verify


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_stack(temperature_raw: int = 0x0C80):
    """Return (clock, device, virtual_bus) for direct FaultBus tests."""
    clock = VirtualClock()
    device = TMP117VirtualDevice(clock, temperature_raw=temperature_raw)
    vbus = VirtualDeviceBus(device, address_7bit=0x48)
    return clock, device, vbus


# ---------------------------------------------------------------------------
# FR01 — NACK on identity read
# ---------------------------------------------------------------------------

class TestFaultNackIdentity:

    def test_FR01_nack_on_identity_raises_bus_nack(self):
        """
        FaultBus injects NACK on the device-ID register read.
        identify() must raise BusNackError.
        Fault is at the bus layer; the normal virtual device is not modified.
        """
        clock, device, vbus = _make_stack()
        spec = FaultSpec(kind="nack", match_register=0x0F, match_operation="read", trigger_count=1)
        fbus = FaultBus(vbus, clock, spec)
        driver = TMP117Driver(fbus, clock, address_7bit=0x48)

        with pytest.raises(BusNackError):
            driver.identify()

    def test_FR16_fault_trace_records_injected_label(self):
        """FaultBus trace for NACK contains outcome 'nack_injected'."""
        clock, device, vbus = _make_stack()
        spec = FaultSpec(kind="nack", match_register=0x0F, match_operation="read", trigger_count=1)
        fbus = FaultBus(vbus, clock, spec)
        driver = TMP117Driver(fbus, clock, address_7bit=0x48)

        try:
            driver.identify()
        except BusNackError:
            pass

        outcomes = [ev.outcome for ev in fbus.fault_trace]
        assert "nack_injected" in outcomes, (
            f"Expected 'nack_injected' in fault trace outcomes; got {outcomes}"
        )

    def test_fault_does_not_alter_virtual_device(self):
        """
        After a faulted NACK, the virtual device trace is empty (the fault
        was intercepted before reaching the device model).
        """
        clock, device, vbus = _make_stack()
        spec = FaultSpec(kind="nack", match_register=0x0F, match_operation="read", trigger_count=1)
        fbus = FaultBus(vbus, clock, spec)
        driver = TMP117Driver(fbus, clock, address_7bit=0x48)

        try:
            driver.identify()
        except BusNackError:
            pass

        # The device-ID NACK was intercepted before reaching the virtual device.
        device_regs = [ev.register for ev in device.trace]
        assert 0x0F not in device_regs, (
            "Virtual device should not have seen the faulted identity read"
        )


# ---------------------------------------------------------------------------
# FR02 — Conversion never ready
# ---------------------------------------------------------------------------

class TestFaultNeverReady:

    def test_FR02_never_ready_raises_conversion_timeout(self):
        """
        FaultBus injects not-ready config word on every config read.
        measure() must raise ConversionTimeout within the short timeout.
        """
        clock, device, vbus = _make_stack()
        spec = FaultSpec(kind="never_ready", match_register=0x01, match_operation="read", trigger_count=1)
        fbus = FaultBus(vbus, clock, spec)
        driver = TMP117Driver(fbus, clock, address_7bit=0x48)

        driver.identify()
        driver.configure()
        with pytest.raises(ConversionTimeout):
            driver.measure(timeout_us=20_000)


# ---------------------------------------------------------------------------
# FR03 — Wrong lower device-ID bits
# ---------------------------------------------------------------------------

class TestFaultWrongIdBits:

    def test_FR03_wrong_id_bits_raises_device_identity_error(self):
        """
        FaultBus returns 0x0118 as device ID (lower 12 bits 0x118 ≠ 0x117).
        identify() must raise DeviceIdentityError.

        Independent literal: expected part ID = 0x117 (F10, SNOSD82D p32).
        Injected: 0x01 0x18 → lower 12 bits = 0x118.
        """
        clock, device, vbus = _make_stack()
        spec = FaultSpec(kind="wrong_id_bits", match_register=0x0F, match_operation="read", trigger_count=1)
        fbus = FaultBus(vbus, clock, spec)
        driver = TMP117Driver(fbus, clock, address_7bit=0x48)

        with pytest.raises(DeviceIdentityError) as exc_info:
            driver.identify()

        # The error message should reference the wrong part ID.
        assert "0x118" in str(exc_info.value) or "118" in str(exc_info.value), (
            f"Expected part ID mismatch in message; got: {exc_info.value}"
        )


# ---------------------------------------------------------------------------
# FR04 — Short temperature read
# ---------------------------------------------------------------------------

class TestFaultShortTempRead:

    def test_FR04_short_temp_read_raises_protocol_error(self):
        """
        FaultBus returns 1 byte for the temperature register read.
        measure() must raise ProtocolReadError.
        """
        clock, device, vbus = _make_stack()
        spec = FaultSpec(kind="short_read", match_register=0x00, match_operation="read", trigger_count=1)
        fbus = FaultBus(vbus, clock, spec)
        driver = TMP117Driver(fbus, clock, address_7bit=0x48)

        driver.identify()
        driver.configure()
        with pytest.raises(ProtocolReadError):
            driver.measure()

    def test_identity_and_configure_not_affected_by_short_temp_fault(self):
        """
        The short-read fault targets register 0x00 only; identify() (0x0F)
        and configure() (write 0x01) must complete successfully.
        """
        clock, device, vbus = _make_stack()
        spec = FaultSpec(kind="short_read", match_register=0x00, match_operation="read", trigger_count=1)
        fbus = FaultBus(vbus, clock, spec)
        driver = TMP117Driver(fbus, clock, address_7bit=0x48)

        identity = driver.identify()
        driver.configure()
        # identity must succeed with correct part ID.
        assert identity.part_id == 0x117, (
            f"Expected part_id=0x117; got {identity.part_id:#05x}"
        )


# ---------------------------------------------------------------------------
# FR05, FR06 — Byte-swap driver
# ---------------------------------------------------------------------------

class TestByteSwapDriver:

    def test_FR05_byte_swap_celsius_is_wrong(self):
        """
        ByteSwapDriver on 25.0 °C fixture must NOT return 25.0 °C.

        Independent literal for swapped 0x0C80:
          swap → bytes [0x80, 0x0C] = unsigned 0x800C
          signed16: 0x800C − 0x10000 = −32756
          −32756 / 128 = −255.90625 °C
        The assertion celsius == 25.0 must FAIL.
        """
        clock = VirtualClock()
        device = TMP117VirtualDevice(clock, temperature_raw=0x0C80)
        bus = VirtualDeviceBus(device, address_7bit=0x48)
        driver = ByteSwapDriver(bus, clock, address_7bit=0x48)

        driver.identify()
        driver.configure()
        measurement = driver.measure()

        # This assertion must FAIL — the byte-swap defect produces wrong output.
        assert measurement.celsius != 25.0, (
            "ByteSwapDriver should NOT return 25.0 °C; the byte-swap defect "
            f"must be detectable. Got celsius={measurement.celsius}"
        )
        # Independent literal: −255.90625 °C (STATUS.md; not derived from code).
        assert measurement.celsius == -255.90625, (
            f"Expected −255.90625 °C for byte-swapped 0x0C80; got {measurement.celsius}"
        )

    def test_FR06_byte_swap_preserves_original_raw_bytes(self):
        """
        ByteSwapDriver must store the original (un-swapped) raw bytes in the
        Measurement so the report shows what the device actually sent.
        """
        clock = VirtualClock()
        device = TMP117VirtualDevice(clock, temperature_raw=0x0C80)
        bus = VirtualDeviceBus(device, address_7bit=0x48)
        driver = ByteSwapDriver(bus, clock, address_7bit=0x48)

        driver.identify()
        driver.configure()
        measurement = driver.measure()

        # Original bytes from device: 0x0C 0x80 (independent literal).
        assert measurement.raw_bytes == b"\x0c\x80", (
            f"Expected raw b'\\x0c\\x80'; got {measurement.raw_bytes.hex()}"
        )


# ---------------------------------------------------------------------------
# FR07–FR12 — execute_scenario integration
# ---------------------------------------------------------------------------

class TestExecuteScenario:

    def test_FR07_baseline_25c_passes(self):
        """execute_scenario baseline_25c with baseline driver: PASS, celsius=25.0."""
        result = execute_scenario("baseline_25c", "baseline")
        assert result.execution_status == "completed"
        assert result.measurement is not None
        assert result.measurement.celsius == 25.0, (
            f"Expected 25.0 °C; got {result.measurement.celsius}"
        )
        assert result.expected_behavior_observed is True
        assert all(a.passed for a in result.assertions), (
            f"Some assertions failed: {[(a.assertion_id, a.passed) for a in result.assertions]}"
        )

    def test_FR08_baseline_neg1c_passes(self):
        """execute_scenario baseline_neg1c with baseline driver: PASS, celsius=−1.0."""
        result = execute_scenario("baseline_neg1c", "baseline")
        assert result.execution_status == "completed"
        assert result.measurement is not None
        assert result.measurement.celsius == -1.0, (
            f"Expected −1.0 °C; got {result.measurement.celsius}"
        )
        assert result.expected_behavior_observed is True

    def test_FR09_fault_nack_identity_observed(self):
        """execute_scenario fault_nack_identity: BusNackError raised, expected_behavior_observed=True."""
        result = execute_scenario("fault_nack_identity", "baseline")
        assert result.execution_status == "completed"
        assert result.device_outcome == "BusNackError"
        assert result.expected_behavior_observed is True
        assert result.raised_exception is not None
        assert isinstance(result.raised_exception, BusNackError)

    def test_FR10_fault_never_ready_observed(self):
        """execute_scenario fault_never_ready: ConversionTimeout raised."""
        result = execute_scenario("fault_never_ready", "baseline")
        assert result.execution_status == "completed"
        assert result.device_outcome == "ConversionTimeout"
        assert result.expected_behavior_observed is True
        assert isinstance(result.raised_exception, ConversionTimeout)

    def test_FR11_fault_wrong_id_bits_observed(self):
        """execute_scenario fault_wrong_id_bits: DeviceIdentityError raised."""
        result = execute_scenario("fault_wrong_id_bits", "baseline")
        assert result.execution_status == "completed"
        assert result.device_outcome == "DeviceIdentityError"
        assert result.expected_behavior_observed is True
        assert isinstance(result.raised_exception, DeviceIdentityError)

    def test_FR12_fault_short_temp_observed(self):
        """execute_scenario fault_short_temp: ProtocolReadError raised."""
        result = execute_scenario("fault_short_temp", "baseline")
        assert result.execution_status == "completed"
        assert result.device_outcome == "ProtocolReadError"
        assert result.expected_behavior_observed is True
        assert isinstance(result.raised_exception, ProtocolReadError)

    def test_FR20_fault_scenarios_not_infrastructure_error(self):
        """Fault scenarios produce execution_status 'completed', not 'infrastructure_error'."""
        for scenario_id in (
            "fault_nack_identity",
            "fault_never_ready",
            "fault_wrong_id_bits",
            "fault_short_temp",
        ):
            result = execute_scenario(scenario_id, "baseline")
            assert result.execution_status == "completed", (
                f"{scenario_id}: expected execution_status='completed'; "
                f"got {result.execution_status!r}"
            )


# ---------------------------------------------------------------------------
# FR13–FR15 — Input validation
# ---------------------------------------------------------------------------

class TestInputValidation:

    def test_FR13_unknown_profile_rejected(self):
        """execute_scenario raises ValueError for unknown profile."""
        with pytest.raises(ValueError, match="Unknown profile"):
            execute_scenario("baseline_25c", "baseline", profile_id="nonexistent_profile")

    def test_FR14_unknown_scenario_rejected(self):
        """execute_scenario raises ValueError for unknown scenario."""
        with pytest.raises(ValueError, match="Unknown scenario"):
            execute_scenario("unknown_scenario_xyz", "baseline")

    def test_FR15_invalid_driver_scenario_combo_rejected(self):
        """execute_scenario raises ValueError when driver variant is not applicable."""
        # byte_swap is not applicable for fault scenarios; fault_nack_identity
        # accepts only "baseline".
        with pytest.raises(ValueError, match="not applicable"):
            execute_scenario("fault_nack_identity", "byte_swap")

    def test_unknown_driver_variant_rejected(self):
        """execute_scenario raises ValueError for unknown driver variant."""
        with pytest.raises(ValueError, match="Unknown driver variant"):
            execute_scenario("baseline_25c", "not_a_driver")


# ---------------------------------------------------------------------------
# FR17 — Deterministic replay
# ---------------------------------------------------------------------------

class TestDeterministicReplay:

    def test_FR17_five_runs_produce_identical_normalised_reports(self):
        """
        Five independent baseline_25c runs must produce identical normalised
        report dicts (excluding run_id and wall_time_s).
        """
        normalised = []
        for _ in range(5):
            result = execute_scenario("baseline_25c", "baseline")
            report = build_report(result)
            d = report_to_dict(report, result)
            normalised.append(normalise_for_replay(d))

        reference = normalised[0]
        for i, nd in enumerate(normalised[1:], 1):
            assert nd == reference, (
                f"Run {i + 1} normalised report differs from run 1.\n"
                f"  run 1 keys: {list(reference.keys())}\n"
                f"  run {i + 1} keys: {list(nd.keys())}"
            )


# ---------------------------------------------------------------------------
# FR18, FR19 — Report verification_status
# ---------------------------------------------------------------------------

class TestReportVerificationStatus:

    def test_FR18_baseline_report_is_pass(self):
        """build_report for baseline_25c must have verification_status='pass'."""
        result = execute_scenario("baseline_25c", "baseline")
        report = build_report(result)
        assert report.verification_status == "pass", (
            f"Expected 'pass'; got {report.verification_status!r}"
        )

    def test_FR19_byte_swap_report_is_fail(self):
        """
        build_report for baseline_25c with byte_swap driver must have
        verification_status='fail'.

        The literal 25.0 °C expectation does not change; only the seeded
        defect in ByteSwapDriver causes the celsius assertion to fail.
        """
        result = execute_scenario("baseline_25c", "byte_swap")
        report = build_report(result)
        assert report.verification_status == "fail", (
            f"Expected 'fail' for byte_swap driver; got {report.verification_status!r}"
        )
        # Confirm the celsius assertion specifically failed.
        celsius_assertion = next(
            (a for a in result.assertions if a.assertion_id == "celsius"), None
        )
        assert celsius_assertion is not None
        assert celsius_assertion.passed is False, (
            "The celsius assertion must fail for the byte-swap variant"
        )
        assert celsius_assertion.expected == 25.0
        # Independent literal: −255.90625 °C (STATUS.md).
        assert celsius_assertion.actual == -255.90625, (
            f"Expected actual celsius −255.90625; got {celsius_assertion.actual}"
        )

    def test_byte_swap_execution_status_is_completed(self):
        """ByteSwapDriver measurement completes without infrastructure error."""
        result = execute_scenario("baseline_25c", "byte_swap")
        assert result.execution_status == "completed"
        assert result.measurement is not None


# ---------------------------------------------------------------------------
# Trace content checks
# ---------------------------------------------------------------------------

class TestTraceContent:

    def test_baseline_trace_has_identity_config_temp_reads(self):
        """
        Baseline trace must contain reads of registers 0x0F, 0x01 (≥1), and 0x00.
        """
        result = execute_scenario("baseline_25c", "baseline")
        regs_read = {ev.register for ev in result.trace if ev.operation == "read"}
        assert 0x0F in regs_read, "Device-ID register read missing from trace"
        assert 0x01 in regs_read, "Config register poll missing from trace"
        assert 0x00 in regs_read, "Temperature register read missing from trace"

    def test_fault_nack_trace_has_injected_outcome(self):
        """fault_nack_identity trace contains 'nack_injected' outcome."""
        result = execute_scenario("fault_nack_identity", "baseline")
        outcomes = {ev.outcome for ev in result.trace}
        assert "nack_injected" in outcomes, (
            f"Expected 'nack_injected' in trace outcomes; got {outcomes}"
        )

    def test_fault_wrong_id_trace_has_wrong_id_injected(self):
        """fault_wrong_id_bits trace contains 'wrong_id_injected' outcome."""
        result = execute_scenario("fault_wrong_id_bits", "baseline")
        outcomes = {ev.outcome for ev in result.trace}
        assert "wrong_id_injected" in outcomes, (
            f"Expected 'wrong_id_injected'; got {outcomes}"
        )

    def test_fault_short_temp_trace_has_short_read_injected(self):
        """fault_short_temp trace contains 'short_read_injected' outcome."""
        result = execute_scenario("fault_short_temp", "baseline")
        outcomes = {ev.outcome for ev in result.trace}
        assert "short_read_injected" in outcomes, (
            f"Expected 'short_read_injected'; got {outcomes}"
        )


# ---------------------------------------------------------------------------
# Approval boundary tests — missing/stale contract, applied policy timeout
# ---------------------------------------------------------------------------

class TestApprovalBoundary:
    """
    Tests for the contract approval gate enforced by the runner.

    FA01  _load_approved_contract raises ApprovalMissingError for a contract
          file that has no approval block.
    FA02  _load_approved_contract raises StaleApprovalError for a contract
          file whose content has been modified after approval.
    FA03  execute_scenario fault_never_ready uses the approved policy timeout
          (100 000 µs); the virtual clock advances to at least 100 000 µs
          before ConversionTimeout is raised.
    FA04  report_to_dict provenance block carries policy_timeout_us == 100000.
    """

    def test_FA01_missing_approval_rejected(self, tmp_path):
        """
        A contract file with approval: null must raise ApprovalMissingError.
        No bus operations may proceed without a valid approval block.
        """
        import json
        from drift.contract import ApprovalMissingError
        from drift.runner import _load_approved_contract

        no_approval = {
            "contract": {
                "schema_version": "draft-0",
                "device": "tmp117",
                "profile_id": "tmp117-oneshot-noavg-0x48",
                "status": "reviewed",
                "approval": None,
                "source": {
                    "id": "tmp117",
                    "document": "SNOSD82D",
                    "revision": "D",
                    "sha256": None,
                },
                "facts": [
                    {
                        "id": "F01",
                        "claim": "ADD0 tied to ground selects 0x48.",
                        "page": 21,
                        "pages": None,
                        "section": "Table 7-2",
                    }
                ],
                "selected_profile": {
                    "address7": 72,
                    "mode": "one_shot",
                    "averaging": "none",
                    "initial_fixture_state": "shutdown_after_explicit_configuration",
                },
                "policies_not_vendor_facts": {
                    "timeout_us": 100000,
                    "poll_interval_us": 1000,
                    "virtual_conversion_us": 15500,
                    "clock": "deterministic_integer_microseconds",
                    "physical_hardware_validated": False,
                },
                "derived_candidates": {
                    "shutdown_config_hex": "0600",
                    "start_config_hex": "0E00",
                    "completed_config_snapshot_hex": "2600",
                    "after_ready_consumed_hex": "0600",
                    "derivation": "test",
                },
                "model_limits": ["Selected profile only"],
                "review_instructions": "test",
            },
            "approval": None,
        }
        p = tmp_path / "no_approval.json"
        p.write_text(json.dumps(no_approval), encoding="utf-8")

        with pytest.raises(ApprovalMissingError):
            _load_approved_contract(p)

    def test_FA02_stale_approval_rejected(self, tmp_path):
        """
        A contract file whose content has been modified after approval must
        raise StaleApprovalError.  The source PDF does not need to be present.
        """
        import json
        import pathlib
        from drift.contract import StaleApprovalError
        from drift.runner import _load_approved_contract

        # Load the real approved contract to get a valid structure, then
        # tamper with the contract content so the hash no longer matches.
        real_path = (
            pathlib.Path(__file__).parent.parent
            / "contracts"
            / "tmp117.approved.json"
        )
        raw = json.loads(real_path.read_text(encoding="utf-8"))
        # Tamper: change a fact claim without re-approving.
        raw["contract"]["facts"][0]["claim"] = "TAMPERED claim — hash must fail."
        stale_path = tmp_path / "stale.json"
        stale_path.write_text(json.dumps(raw), encoding="utf-8")

        with pytest.raises(StaleApprovalError):
            _load_approved_contract(stale_path)

    def test_FA03_never_ready_uses_policy_timeout(self):
        """
        execute_scenario fault_never_ready must use the approved 100 000 µs
        policy timeout.  The virtual clock must advance to at least 100 000 µs
        before ConversionTimeout is raised.

        Independent check: the policy value comes from the approved contract
        (policies_not_vendor_facts.timeout_us = 100 000).
        """
        result = execute_scenario("fault_never_ready", "baseline")
        assert result.execution_status == "completed"
        assert isinstance(result.raised_exception, ConversionTimeout), (
            f"Expected ConversionTimeout; got {type(result.raised_exception).__name__}"
        )
        # Virtual clock must have advanced to at least the policy timeout.
        assert result.virtual_end_us >= 100_000, (
            f"Expected virtual_end_us >= 100 000 µs (approved policy); "
            f"got {result.virtual_end_us} µs"
        )

    def test_FA04_provenance_carries_policy_timeout(self):
        """
        report_to_dict provenance block must carry policy_timeout_us == 100000
        derived from the approved contract.
        """
        from drift.reporting import build_report, report_to_dict

        result = execute_scenario("baseline_25c", "baseline")
        report = build_report(result)
        d = report_to_dict(report, result)
        assert "policy_timeout_us" in d["provenance"], (
            "provenance block is missing policy_timeout_us"
        )
        assert d["provenance"]["policy_timeout_us"] == 100_000, (
            f"Expected policy_timeout_us=100000; "
            f"got {d['provenance']['policy_timeout_us']}"
        )
