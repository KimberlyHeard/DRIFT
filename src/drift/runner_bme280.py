"""
DRIFT BME280 scenario runner — temperature-only forced-mode profile.

Responsibilities
----------------
- Load and validate the approved BME280 contract before any bus operations.
- Accept only reviewed named scenarios.
- Construct a fresh stack (clock + device + bus + driver) for every run.
- Invoke identify() and measure() in correct order.
- Catch exceptions produced by fault scenarios and record the outcome.
- Evaluate assertions using independent literal expectations.
- Collect the complete ordered bus trace for the report.

AGENTS.md boundaries:
  - Driver uses bus/clock interfaces only; cannot inspect device internals.
  - Expected values stay literal; this module never derives them from production.
  - Trace/report inspection cannot read device registers or mutate device state.
  - Provenance and runtime policy are derived from the validated approved contract.
"""

from __future__ import annotations

import dataclasses
import pathlib
import time
import uuid
from typing import Any, Optional

from drift.bus import ScriptedBus, VirtualDeviceBus
from drift.clock import VirtualClock
from drift.contract import ApprovedContract
from drift.devices.bme280 import BME280VirtualDevice
from drift.drivers.bme280 import BME280Driver
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
from drift.scenarios_bme280 import (
    BME280_CLI_PROFILE_ID,
    BME280_APPROVED_PROFILE_ID,
    BME280_CONTRACT_SHA256,
    BME280ScenarioDef,
    BME280ScenarioExpectation,
    get_bme280_scenario,
)

# ---------------------------------------------------------------------------
# Approved BME280 contract — loaded and validated once at import time.
# ---------------------------------------------------------------------------

_BME280_CONTRACT_PATH: pathlib.Path = (
    pathlib.Path(__file__).parent.parent.parent / "contracts" / "bme280.approved.json"
)

_BME280_APPROVED_CONTRACT: ApprovedContract = ApprovedContract.from_file(
    _BME280_CONTRACT_PATH
)

_BME280_CONTRACT_SHA256: str = _BME280_APPROVED_CONTRACT.approval.contract_sha256
_BME280_SOURCE_SHA256: str = _BME280_APPROVED_CONTRACT.approval.source_sha256
_BME280_REVIEWER: str = _BME280_APPROVED_CONTRACT.approval.reviewer
_BME280_APPROVED_UTC: str = _BME280_APPROVED_CONTRACT.approval.approved_utc
_BME280_POLICY_TIMEOUT_US: int = (
    _BME280_APPROVED_CONTRACT.contract.policies_not_vendor_facts.timeout_us
)

# Schema version for BME280 runner output.
BME280_REPORT_SCHEMA_VERSION: str = "1.0"

# DRIFT policy limits.
_BME280_MAX_VIRTUAL_US: int = 200_000

# BME280 address (SDO=GND, F02).
_BME280_ADDR: int = 0x76

# Calibration bytes (dig_T1=27504, dig_T2=26435, dig_T3=-1000 — F03).
_CALIB_BYTES: bytes = bytes([0x70, 0x6B, 0x43, 0x67, 0x18, 0xFC])

# DRIFT policy: short-read fault delivers only 2 bytes for the 3-byte temp read.
_SHORT_TEMP_RESPONSE: bytes = bytes([0x7E, 0xED])  # 2 bytes only


@dataclasses.dataclass
class BME280RunResult:
    """
    Mutable working state for one BME280 scenario execution.

    Converted to report dict by reporting_bme280.
    """
    run_id: str
    scenario_id: str
    driver_variant: str
    execution_status: str
    device_outcome: str
    measurement: Optional[Measurement]
    raised_exception: Optional[Exception]
    assertions: list[AssertionRecord]
    trace: tuple[TraceEvent, ...]
    wall_time_s: float
    virtual_end_us: int
    expected_behavior_observed: bool


class _TracedShortTempBus(ScriptedBus):
    """Scripted fault bus whose trace records the bytes delivered to the driver."""

    def __init__(self, steps, clock: VirtualClock) -> None:
        super().__init__(steps)
        self._clock = clock
        self._events: list[TraceEvent] = []

    def _record(self, address: int, register: int, operation: str,
                sent: bytes, received: bytes, outcome: str) -> None:
        self._events.append(TraceEvent(
            sequence=len(self._events), virtual_time_us=self._clock.now_us(),
            address_7bit=address, register=register, operation=operation,
            sent_bytes=sent, received_bytes=received, outcome=outcome,
            fact_ids=("F04",) if register == 0xFA else (),
        ))

    def read_register(self, address_7bit: int, register: int, length: int) -> bytes:
        if register == 0xFA and length == 3:
            # Explicit fault: return two actual bytes to the driver. The driver
            # then raises ProtocolReadError on its three-byte length check.
            step = self._next_step("read", address_7bit, register)
            response = step.payload
            if len(response) != 2:
                raise AssertionError("short-read fixture must deliver two bytes")
            self._record(address_7bit, register, "read", b"", response,
                         "fault_short_read")
            return response
        response = super().read_register(address_7bit, register, length)
        self._record(address_7bit, register, "read", b"", response, "ok")
        return response

    def write_register(self, address_7bit: int, register: int, payload: bytes) -> None:
        super().write_register(address_7bit, register, payload)
        self._record(address_7bit, register, "write", payload, b"", "ok")

    @property
    def trace(self) -> tuple[TraceEvent, ...]:
        return tuple(self._events)


def _build_short_temp_bus(
    calib: bytes,
    conversion_us: int,
) -> tuple[ScriptedBus, VirtualClock]:
    """
    Build a scripted bus that injects a 2-byte (short) temperature read.

    Flow:
      0: identify → read 0xD0 → b'\\x60'
      1: read 0x88 → calib (6 bytes)
      2: write 0xF4 → b'\\x21'
      3: read 0xF3 → b'\\x08' (busy)  × enough polls to reach deadline
      4+: read 0xF3 → b'\\x00' (idle) on 4th poll
      last: read 0xFA → 2 bytes only (short read fault)
    """
    # With conversion_us=3600 and poll_interval=1000 µs, idle appears at poll 4
    # (t=4000 µs).  Provide 3 busy polls then 1 idle poll.
    steps = [
        ScriptedBus.step_read(_BME280_ADDR, 0xD0, b"\x60"),          # identify
        ScriptedBus.step_read(_BME280_ADDR, 0x88, calib),            # calibration
        ScriptedBus.step_write(_BME280_ADDR, 0xF4, b"\x21"),         # forced write
        ScriptedBus.step_read(_BME280_ADDR, 0xF3, b"\x08"),          # busy poll 1
        ScriptedBus.step_read(_BME280_ADDR, 0xF3, b"\x08"),          # busy poll 2
        ScriptedBus.step_read(_BME280_ADDR, 0xF3, b"\x08"),          # busy poll 3
        ScriptedBus.step_read(_BME280_ADDR, 0xF3, b"\x00"),          # idle poll 4
        ScriptedBus.step_read(_BME280_ADDR, 0xFA, _SHORT_TEMP_RESPONSE),  # short!
    ]
    clock = VirtualClock(0)
    return _TracedShortTempBus(steps, clock), clock


def _evaluate_bme280_assertions(
    scenario: BME280ScenarioDef,
    measurement: Optional[Measurement],
    raised_exception: Optional[Exception],
    trace: tuple[TraceEvent, ...],
) -> tuple[list[AssertionRecord], bool]:
    """
    Evaluate assertions for one BME280 scenario run.

    Returns (assertions, expected_behavior_observed).
    Expected values are literals from BME280ScenarioExpectation.
    This function never derives them from driver, decoder, or model code.
    """
    exp: BME280ScenarioExpectation = scenario.expectation
    assertions: list[AssertionRecord] = []

    # ---- Fault scenarios: assert the expected exception was raised ----
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
                fact_ids=("F04",),
                trace_indices=(),
            )
        )
        return assertions, passed

    # ---- Baseline scenarios ----
    if measurement is None:
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

    # Celsius
    celsius_passed = measurement.celsius == exp.expected_celsius
    assertions.append(
        AssertionRecord(
            assertion_id="celsius",
            expected=exp.expected_celsius,
            actual=measurement.celsius,
            passed=celsius_passed,
            fact_ids=("F04", "F05"),
            trace_indices=_indices_for_reg(trace, 0xFA),
        )
    )

    # Raw bytes
    raw_passed = measurement.raw_bytes == exp.expected_raw_bytes
    assertions.append(
        AssertionRecord(
            assertion_id="raw_bytes",
            expected=exp.expected_raw_bytes.hex() if exp.expected_raw_bytes else None,
            actual=measurement.raw_bytes.hex(),
            passed=raw_passed,
            fact_ids=("F04",),
            trace_indices=_indices_for_reg(trace, 0xFA),
        )
    )

    # Virtual time
    time_passed = measurement.virtual_time_us == exp.expected_virtual_time_us
    assertions.append(
        AssertionRecord(
            assertion_id="virtual_time_us",
            expected=exp.expected_virtual_time_us,
            actual=measurement.virtual_time_us,
            passed=time_passed,
            fact_ids=("F07", "F12"),
            trace_indices=_indices_for_reg(trace, 0xF3),
        )
    )

    all_passed = celsius_passed and raw_passed and time_passed
    return assertions, all_passed


def _indices_for_reg(
    trace: tuple[TraceEvent, ...], register: int
) -> tuple[int, ...]:
    """Return sequence indices for all trace events touching register."""
    return tuple(ev.sequence for ev in trace if ev.register == register)


def execute_bme280_scenario(
    scenario_id: str,
    driver_variant: str = "baseline",
) -> BME280RunResult:
    """
    Execute one named BME280 scenario with the specified driver variant.

    A fresh clock, virtual device (or scripted bus for fault scenarios),
    bus, and driver are constructed for every call.

    Parameters
    ----------
    scenario_id:
        One of the reviewed scenario IDs in BME280_SCENARIO_REGISTRY.
    driver_variant:
        "baseline" (only supported variant).

    Returns
    -------
    BME280RunResult
        Complete run result including trace, assertions, and outcome.
    """
    scenario: BME280ScenarioDef = get_bme280_scenario(scenario_id)
    if driver_variant not in scenario.applicable_drivers:
        raise ValueError(
            f"Driver variant {driver_variant!r} is not applicable for "
            f"BME280 scenario {scenario_id!r}. "
            f"Applicable: {sorted(scenario.applicable_drivers)}"
        )

    run_id = str(uuid.uuid4())
    wall_start = time.monotonic()

    # ------------------------------------------------------------------
    # Build the stack for this scenario.
    # ------------------------------------------------------------------
    device_ref: Optional[BME280VirtualDevice] = None

    if scenario.fault_spec is not None:
        # Fault scenario: use a scripted bus that injects the fault.
        fault = scenario.fault_spec
        if isinstance(fault, dict) and fault.get("kind") == "short_temp":
            bus, clock = _build_short_temp_bus(
                calib=scenario.calib_bytes,
                conversion_us=scenario.conversion_us,
            )
        else:
            raise ValueError(
                f"BME280 runner: unknown fault spec {fault!r} "
                f"for scenario {scenario_id!r}"
            )
        driver = BME280Driver(bus=bus, clock=clock, address_7bit=_BME280_ADDR)
        device_ref = None
    else:
        # Baseline scenario: virtual device.
        clock = VirtualClock(0)
        device = BME280VirtualDevice(
            clock=clock,
            calib_bytes=scenario.calib_bytes,
            temp_raw_bytes=scenario.temp_raw_bytes,
            conversion_us=scenario.conversion_us,
            address_7bit=_BME280_ADDR,
        )
        device_ref = device
        bus = VirtualDeviceBus(device, address_7bit=_BME280_ADDR)
        driver = BME280Driver(bus=bus, clock=clock, address_7bit=_BME280_ADDR)

    # ------------------------------------------------------------------
    # Execute the driver flow.
    # ------------------------------------------------------------------
    measurement: Optional[Measurement] = None
    raised_exception: Optional[Exception] = None
    execution_status = "completed"
    device_outcome = "measurement"

    try:
        driver.identify()
        measurement = driver.measure(timeout_us=_BME280_POLICY_TIMEOUT_US)
    except (BusNackError, DeviceIdentityError, ProtocolReadError,
            ConversionTimeout) as exc:
        raised_exception = exc
        device_outcome = type(exc).__name__
    except Exception as exc:
        raised_exception = exc
        device_outcome = type(exc).__name__
        execution_status = "infrastructure_error"

    wall_end = time.monotonic()

    # ------------------------------------------------------------------
    # Collect trace.
    # ------------------------------------------------------------------
    if device_ref is not None:
        device_trace: tuple[TraceEvent, ...] = device_ref.trace
    else:
        device_trace = bus.trace

    # ------------------------------------------------------------------
    # Evaluate assertions.
    # ------------------------------------------------------------------
    assertions, expected_behavior_observed = _evaluate_bme280_assertions(
        scenario, measurement, raised_exception, device_trace
    )

    return BME280RunResult(
        run_id=run_id,
        scenario_id=scenario_id,
        driver_variant=driver_variant,
        execution_status=execution_status,
        device_outcome=device_outcome,
        measurement=measurement,
        raised_exception=raised_exception,
        assertions=assertions,
        trace=device_trace,
        wall_time_s=wall_end - wall_start,
        virtual_end_us=clock.now_us(),
        expected_behavior_observed=expected_behavior_observed,
    )


def execute_bme280_verify() -> list[BME280RunResult]:
    """
    Execute all BME280 scenarios and return results.

    Runs both baselines (25 °C and -7.86 °C) plus the short-temp fault.
    """
    plan = [
        ("bme280_25c", "baseline"),
        ("bme280_neg8c", "baseline"),
        ("bme280_short_temp", "baseline"),
    ]
    results = []
    for scenario_id, variant in plan:
        results.append(execute_bme280_scenario(scenario_id, variant))
    return results
