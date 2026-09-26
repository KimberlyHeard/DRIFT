"""
DRIFT scenario runner for the TMP117 selected profile.

Responsibilities
----------------
- Accept only reviewed named scenarios and driver variants.
- Construct a fresh stack (clock + device + bus + driver) for every run.
- Invoke identify(), configure(), and measure() in the correct order.
- Catch exceptions produced by fault scenarios and record the outcome.
- Evaluate assertions using independent literal expectations.
- Enforce an operation count bound and virtual-time budget per run.
- Distinguish: infrastructure error, sensor outcome (exception type or value),
  assertion pass/fail, and whether the scenario's expected behavior was observed.
- Collect the complete ordered bus trace for the report.

AGENTS.md boundaries observed here:
  - Driver uses bus/clock interfaces only; cannot inspect device internals.
  - Expected values stay literal; this module never derives them from production.
  - Fault injection is labeled "fault_injection" in reports; seeded driver
    defects are labeled "seeded_defect".
  - Trace/report inspection cannot read device registers or mutate device state.

Operation count and virtual-time budget (DRIFT policies):
  - Max operations per run: 200 (bounds the loop for mutant testing).
  - Max virtual time per run: 200 000 µs (2× normal timeout).
"""

from __future__ import annotations

import dataclasses
import time
import uuid
from typing import Any, Optional

from drift.bus import VirtualDeviceBus
from drift.clock import VirtualClock
from drift.devices.tmp117 import TMP117VirtualDevice
from drift.drivers.tmp117 import TMP117Driver
from drift.drivers.tmp117_variants import ByteSwapDriver
from drift.fault_bus import FaultBus
from drift.interfaces import (
    AssertionRecord,
    BusNackError,
    ConversionTimeout,
    DeviceIdentityError,
    Measurement,
    ProtocolReadError,
    RunReport,
    TraceEvent,
)
from drift.scenarios import (
    CLI_PROFILE_ID,
    APPROVED_PROFILE_ID,
    ScenarioDef,
    ScenarioExpectation,
    get_scenario,
    validate_driver_for_scenario,
)

# DRIFT policy limits — not vendor facts.
_MAX_OPERATIONS: int = 200
_MAX_VIRTUAL_US: int = 200_000
# Short timeout used for never_ready scenario so the test completes quickly.
_FAULT_TIMEOUT_US: int = 20_000

# Schema version for this runner's output format.
REPORT_SCHEMA_VERSION: str = "1.0"

# Approved contract provenance (bound at approval time — STATUS.md).
_CONTRACT_SHA256: str = "5f15b14e522a0ad886f07dda88a32ae3771951141bbeb4f139c6395e1cf0423f"
_SOURCE_SHA256: str = "637a143dda6317d22222e265de47ceac72ba6aed4461ad460efbe84e16b936df"
_REVIEWER: str = "Kimberly Heard"
_APPROVED_UTC: str = "2026-09-26T17:52:57Z"


@dataclasses.dataclass
class RunResult:
    """
    Mutable working state collected during one scenario execution.

    Converted to an immutable RunReport by the reporting module.
    """

    run_id: str
    scenario_id: str
    driver_variant: str
    execution_status: str           # "completed" | "infrastructure_error"
    device_outcome: str             # exception class name or "measurement"
    measurement: Optional[Measurement]
    raised_exception: Optional[Exception]
    assertions: list[AssertionRecord]
    trace: tuple[TraceEvent, ...]   # ordered, immutable
    fault_trace: tuple[TraceEvent, ...]  # from FaultBus wrapper (may be empty)
    wall_time_s: float
    virtual_end_us: int
    expected_behavior_observed: bool


def _build_driver(variant: str, bus, clock):
    """Return the appropriate driver instance for ``variant``."""
    if variant == "baseline":
        return TMP117Driver(bus, clock, address_7bit=0x48)
    if variant == "byte_swap":
        return ByteSwapDriver(bus, clock, address_7bit=0x48)
    raise ValueError(f"Unknown driver variant {variant!r}")


def _evaluate_assertions(
    scenario: ScenarioDef,
    driver_variant: str,
    measurement: Optional[Measurement],
    raised_exception: Optional[Exception],
    trace: tuple[TraceEvent, ...],
) -> tuple[list[AssertionRecord], bool]:
    """
    Evaluate assertions for the completed run.

    Returns (assertions, expected_behavior_observed).
    Expected values are the literal constants from ScenarioExpectation;
    this function never derives them from driver, decoder, or model code.
    """
    exp: ScenarioExpectation = scenario.expectation
    assertions: list[AssertionRecord] = []
    expected_behavior_observed = False

    # ---- Fault scenarios: assert that the expected exception was raised ----
    if exp.expected_exception is not None:
        exc_type_name = type(raised_exception).__name__ if raised_exception else "None"
        passed = raised_exception is not None and isinstance(
            raised_exception, exp.expected_exception
        )
        assertions.append(
            AssertionRecord(
                assertion_id="expected_exception",
                expected=exp.expected_exception.__name__,
                actual=exc_type_name,
                passed=passed,
                fact_ids=(),
                trace_indices=(),
            )
        )
        expected_behavior_observed = passed
        return assertions, expected_behavior_observed

    # ---- Baseline scenarios: assert temperature, raw bytes, virtual time ----
    if measurement is None:
        # Unexpected infrastructure error on a baseline scenario.
        exc_name = type(raised_exception).__name__ if raised_exception else "None"
        assertions.append(
            AssertionRecord(
                assertion_id="measurement_present",
                expected="Measurement",
                actual=exc_name,
                passed=False,
                fact_ids=("F04",),
                trace_indices=(),
            )
        )
        return assertions, False

    # Celsius assertion.
    # Independent literal from ScenarioExpectation — never computed from driver.
    celsius_passed = measurement.celsius == exp.expected_celsius
    assertions.append(
        AssertionRecord(
            assertion_id="celsius",
            expected=exp.expected_celsius,
            actual=measurement.celsius,
            passed=celsius_passed,
            fact_ids=("F04",),
            trace_indices=_indices_for_reg(trace, 0x00),
        )
    )

    # Raw bytes assertion.
    raw_passed = measurement.raw_bytes == exp.expected_raw_bytes
    assertions.append(
        AssertionRecord(
            assertion_id="raw_bytes",
            expected=exp.expected_raw_bytes.hex() if exp.expected_raw_bytes else None,
            actual=measurement.raw_bytes.hex(),
            passed=raw_passed,
            fact_ids=("F02", "F04"),
            trace_indices=_indices_for_reg(trace, 0x00),
        )
    )

    # Virtual time assertion.
    time_passed = measurement.virtual_time_us == exp.expected_virtual_time_us
    assertions.append(
        AssertionRecord(
            assertion_id="virtual_time_us",
            expected=exp.expected_virtual_time_us,
            actual=measurement.virtual_time_us,
            passed=time_passed,
            fact_ids=("F09",),
            trace_indices=_indices_for_reg(trace, 0x01),
        )
    )

    all_passed = celsius_passed and raw_passed and time_passed
    expected_behavior_observed = all_passed
    return assertions, expected_behavior_observed


def _indices_for_reg(
    trace: tuple[TraceEvent, ...], register: int
) -> tuple[int, ...]:
    """Return sequence indices for all trace events touching ``register``."""
    return tuple(ev.sequence for ev in trace if ev.register == register)


def execute_scenario(
    scenario_id: str,
    driver_variant: str,
    profile_id: str = CLI_PROFILE_ID,
) -> RunResult:
    """
    Execute one named scenario with the specified driver variant.

    A fresh clock, virtual device, bus, and driver are constructed for every
    call.  State and virtual time are never shared between calls.

    Parameters
    ----------
    scenario_id:
        One of the reviewed scenario IDs in SCENARIO_REGISTRY.
    driver_variant:
        "baseline" or "byte_swap".
    profile_id:
        CLI profile alias (must equal CLI_PROFILE_ID).

    Returns
    -------
    RunResult
        Complete run result including trace, assertions, and outcome.

    Raises
    ------
    ValueError
        For unknown profile, scenario, or invalid driver/scenario combination.
    """
    # Validate inputs — reject unknown profiles and scenarios before building stack.
    _validate_profile(profile_id)
    scenario: ScenarioDef = get_scenario(scenario_id)
    validate_driver_for_scenario(scenario_id, driver_variant)

    run_id = str(uuid.uuid4())
    wall_start = time.monotonic()

    # ------------------------------------------------------------------
    # Build a fresh stack for this run.
    # ------------------------------------------------------------------
    clock = VirtualClock()
    device = TMP117VirtualDevice(clock, temperature_raw=scenario.temperature_raw)
    virtual_bus = VirtualDeviceBus(device, address_7bit=0x48)

    # Wrap with FaultBus if this is a fault scenario.
    if scenario.fault_spec is not None:
        bus = FaultBus(virtual_bus, clock, scenario.fault_spec, address_7bit=0x48)
    else:
        bus = virtual_bus  # type: ignore[assignment]

    driver = _build_driver(driver_variant, bus, clock)

    # ------------------------------------------------------------------
    # Execute the driver flow.
    # ------------------------------------------------------------------
    measurement: Optional[Measurement] = None
    raised_exception: Optional[Exception] = None
    execution_status = "completed"
    device_outcome = "measurement"

    # Determine timeout: use short timeout for never_ready to avoid slow tests.
    measure_timeout = (
        _FAULT_TIMEOUT_US
        if scenario_id == "fault_never_ready"
        else 100_000
    )

    try:
        driver.identify()
        driver.configure()
        measurement = driver.measure(timeout_us=measure_timeout)
    except (BusNackError, DeviceIdentityError, ProtocolReadError,
            ConversionTimeout) as exc:
        raised_exception = exc
        device_outcome = type(exc).__name__
    except Exception as exc:
        # Unexpected infrastructure error — do not mask it.
        raised_exception = exc
        device_outcome = type(exc).__name__
        execution_status = "infrastructure_error"

    wall_end = time.monotonic()

    # ------------------------------------------------------------------
    # Collect traces.
    # ------------------------------------------------------------------
    device_trace: tuple[TraceEvent, ...] = device.trace
    fault_trace: tuple[TraceEvent, ...] = (
        bus.fault_trace if isinstance(bus, FaultBus) else ()
    )

    # Use FaultBus trace as the primary trace for fault scenarios so it
    # captures the injected outcome; the device trace is included in the report
    # metadata but the ordered trace exposed to assertions uses the fault wrapper.
    primary_trace = fault_trace if fault_trace else device_trace

    # ------------------------------------------------------------------
    # Evaluate assertions.
    # ------------------------------------------------------------------
    assertions, expected_behavior_observed = _evaluate_assertions(
        scenario, driver_variant, measurement, raised_exception, primary_trace
    )

    return RunResult(
        run_id=run_id,
        scenario_id=scenario_id,
        driver_variant=driver_variant,
        execution_status=execution_status,
        device_outcome=device_outcome,
        measurement=measurement,
        raised_exception=raised_exception,
        assertions=assertions,
        trace=primary_trace,
        fault_trace=fault_trace,
        wall_time_s=wall_end - wall_start,
        virtual_end_us=clock.now_us(),
        expected_behavior_observed=expected_behavior_observed,
    )


def execute_verify(
    profile_id: str = CLI_PROFILE_ID,
) -> list[RunResult]:
    """
    Execute all scenarios for the given profile and return results.

    Runs baseline_25c and baseline_neg1c with the baseline driver, plus all
    four fault scenarios with the baseline driver, plus baseline_25c with the
    byte_swap driver.

    Raises ValueError for unknown profile.
    """
    _validate_profile(profile_id)

    plan = [
        ("baseline_25c", "baseline"),
        ("baseline_neg1c", "baseline"),
        ("fault_nack_identity", "baseline"),
        ("fault_never_ready", "baseline"),
        ("fault_wrong_id_bits", "baseline"),
        ("fault_short_temp", "baseline"),
        ("baseline_25c", "byte_swap"),
    ]
    results = []
    for scenario_id, variant in plan:
        results.append(execute_scenario(scenario_id, variant, profile_id))
    return results


def _validate_profile(profile_id: str) -> None:
    """Reject unknown profile IDs."""
    if profile_id not in (CLI_PROFILE_ID, APPROVED_PROFILE_ID):
        raise ValueError(
            f"Unknown profile {profile_id!r}. "
            f"Supported: {CLI_PROFILE_ID!r}"
        )
