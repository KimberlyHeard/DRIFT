"""
DRIFT scenario definitions for the TMP117 selected profile.

A scenario is a named, validated fixture/fault definition that the runner
uses to construct a fresh execution stack (clock + device + bus + driver).
Public execution is limited to this registry of reviewed, named scenarios.
Unknown scenario IDs are explicitly rejected (AGENTS.md: public execution
accepts only reviewed named variants/fixtures).

Scenario IDs
------------
  baseline_25c        — fresh stack, 25.0 °C fixture (raw 0x0C80), no fault.
  baseline_neg1c      — fresh stack, −1.0 °C fixture (raw 0xFF80), no fault.
  fault_nack_identity — NACK injected on the identity (device-ID) read.
  fault_never_ready   — conversion never reports ready; driver times out.
  fault_wrong_id_bits — device-ID lower 12 bits are wrong (0x118 ≠ 0x117).
  fault_short_temp    — temperature read returns 1 byte instead of 2.

Independent expected values for assertions (literal, not derived from code):
  baseline_25c:     celsius = 25.0    raw_bytes = b'\\x0c\\x80'  time_us = 16_000
  baseline_neg1c:   celsius = −1.0    raw_bytes = b'\\xff\\x80'  time_us = 16_000
  (F04: 0x0C80 = 3200/128 = 25.0; 0xFF80 signed = −128, −128/128 = −1.0)

For fault scenarios the expected outcome is an exception type; temperature
assertions are not applicable.

Source contract: contracts/tmp117.approved.json
  profile_id: tmp117-oneshot-noavg-0x48
  approval: 2026-09-26T17:52:57Z by Kimberly Heard
  contract_sha256: 5f15b14e522a0ad886f07dda88a32ae3771951141bbeb4f139c6395e1cf0423f
"""

from __future__ import annotations

import dataclasses
from typing import Any, Optional, Type

# Register constants used in fault specs — mirrored from driver/model.
_REG_TEMPERATURE: int = 0x00
_REG_CONFIGURATION: int = 0x01
_REG_DEVICE_ID: int = 0x0F

# Approved profile ID (must match contracts/tmp117.approved.json).
APPROVED_PROFILE_ID: str = "tmp117-oneshot-noavg-0x48"

# Runner-facing profile alias used in the CLI (maps to APPROVED_PROFILE_ID).
CLI_PROFILE_ID: str = "tmp117_one_shot_no_average"

# Set of driver variant names accepted by public execution.
SUPPORTED_DRIVER_VARIANTS: frozenset[str] = frozenset({"baseline", "byte_swap"})


@dataclasses.dataclass(frozen=True)
class ScenarioExpectation:
    """
    Independently prepared expected outcome for one scenario.

    Fields are literal values reviewed by a human; they must never be derived
    from production driver, decoder, or model code (AGENTS.md boundary).

    For fault scenarios ``expected_celsius`` and ``expected_raw_bytes`` are
    None because the driver raises before returning a measurement.
    ``expected_exception`` names the exception type the driver must raise.
    """

    # Temperature assertions (baseline only)
    expected_celsius: Optional[float]          # literal, e.g. 25.0
    expected_raw_bytes: Optional[bytes]        # literal, e.g. b'\x0c\x80'
    expected_virtual_time_us: Optional[int]    # literal, e.g. 16_000

    # Fault assertion (fault scenarios only)
    expected_exception: Optional[Type[Exception]]  # e.g. BusNackError

    # Narrative description of what "expected behavior observed" means.
    expected_behavior_description: str


@dataclasses.dataclass(frozen=True)
class ScenarioDef:
    """
    Full definition of one named scenario.

    Parameters
    ----------
    scenario_id:
        Unique short identifier, used in CLI and report filenames.
    description:
        Human-readable description for reports.
    temperature_raw:
        Raw 16-bit temperature word for the virtual device fixture.
    fault_spec:
        FaultSpec to inject, or None for baseline runs.
    expectation:
        Independently prepared expected outcome.
    applicable_drivers:
        Set of driver variant names that are valid for this scenario.
        "byte_swap" is only valid for baseline_25c (demonstrates the fail path).
    """

    scenario_id: str
    description: str
    temperature_raw: int
    fault_spec: Optional[Any]                  # FaultSpec | None
    expectation: ScenarioExpectation
    applicable_drivers: frozenset[str]


# ---------------------------------------------------------------------------
# Scenario registry
# ---------------------------------------------------------------------------

def _make_registry() -> dict[str, ScenarioDef]:
    """Build and return the scenario registry."""
    # Import here to avoid circular imports at module level.
    from drift.fault_bus import FaultSpec
    from drift.interfaces import (
        BusNackError,
        ConversionTimeout,
        DeviceIdentityError,
        ProtocolReadError,
    )

    registry: dict[str, ScenarioDef] = {}

    # ------------------------------------------------------------------
    # baseline_25c
    # Independent literals: F04 SNOSD82D p26 §7.6.2
    #   0x0C80 = 3200 counts; 3200 / 128 = 25.0 °C
    #   poll at 1 000 µs steps; Data_Ready at 15 500 µs → first observed at 16 000 µs
    # ------------------------------------------------------------------
    registry["baseline_25c"] = ScenarioDef(
        scenario_id="baseline_25c",
        description="Baseline: 25.0 °C fixture, no fault injected.",
        temperature_raw=0x0C80,
        fault_spec=None,
        expectation=ScenarioExpectation(
            expected_celsius=25.0,
            expected_raw_bytes=b"\x0c\x80",
            expected_virtual_time_us=16_000,
            expected_exception=None,
            expected_behavior_description=(
                "Driver returns Measurement(celsius=25.0, raw_bytes=b'\\x0c\\x80', "
                "virtual_time_us=16_000)."
            ),
        ),
        applicable_drivers=frozenset({"baseline", "byte_swap"}),
    )

    # ------------------------------------------------------------------
    # baseline_neg1c
    # Independent literals: F04 SNOSD82D p26 §7.6.2
    #   0xFF80 as signed 16-bit = −128; −128 / 128 = −1.0 °C
    # ------------------------------------------------------------------
    registry["baseline_neg1c"] = ScenarioDef(
        scenario_id="baseline_neg1c",
        description="Baseline: −1.0 °C fixture, no fault injected.",
        temperature_raw=0xFF80,
        fault_spec=None,
        expectation=ScenarioExpectation(
            expected_celsius=-1.0,
            expected_raw_bytes=b"\xff\x80",
            expected_virtual_time_us=16_000,
            expected_exception=None,
            expected_behavior_description=(
                "Driver returns Measurement(celsius=-1.0, raw_bytes=b'\\xff\\x80', "
                "virtual_time_us=16_000)."
            ),
        ),
        applicable_drivers=frozenset({"baseline"}),
    )

    # ------------------------------------------------------------------
    # fault_nack_identity
    # Fault: NACK on the identity (device-ID register 0x0F) read.
    # Driver must raise BusNackError (or DeviceIdentityError wrapping it).
    # The virtual device is not modified; the fault is at the bus layer.
    # ------------------------------------------------------------------
    registry["fault_nack_identity"] = ScenarioDef(
        scenario_id="fault_nack_identity",
        description=(
            "Fault: NACK injected on identity read (register 0x0F). "
            "Driver must raise BusNackError."
        ),
        temperature_raw=0x0C80,          # irrelevant; driver never reaches measure()
        fault_spec=FaultSpec(
            kind="nack",
            match_register=_REG_DEVICE_ID,
            match_operation="read",
            trigger_count=1,
        ),
        expectation=ScenarioExpectation(
            expected_celsius=None,
            expected_raw_bytes=None,
            expected_virtual_time_us=None,
            expected_exception=BusNackError,
            expected_behavior_description=(
                "identify() raises BusNackError on the first read of register 0x0F."
            ),
        ),
        applicable_drivers=frozenset({"baseline"}),
    )

    # ------------------------------------------------------------------
    # fault_never_ready
    # Fault: configuration register read that would show Data_Ready instead
    # returns the one-shot-active word, so the driver times out.
    # We use a very short timeout (20 000 µs) to keep the test fast.
    # The fault fires on every config read (trigger_count=1 fires on first
    # matching read; subsequent reads pass through, but they also return
    # not-ready from the device because conversion_us > 20 000).
    # ------------------------------------------------------------------
    registry["fault_never_ready"] = ScenarioDef(
        scenario_id="fault_never_ready",
        description=(
            "Fault: configuration register reads return not-ready word; "
            "driver times out with ConversionTimeout."
        ),
        temperature_raw=0x0C80,
        fault_spec=FaultSpec(
            kind="never_ready",
            match_register=_REG_CONFIGURATION,
            match_operation="read",
            trigger_count=1,
        ),
        expectation=ScenarioExpectation(
            expected_celsius=None,
            expected_raw_bytes=None,
            expected_virtual_time_us=None,
            expected_exception=ConversionTimeout,
            expected_behavior_description=(
                "measure() raises ConversionTimeout after all polls return not-ready."
            ),
        ),
        applicable_drivers=frozenset({"baseline"}),
    )

    # ------------------------------------------------------------------
    # fault_wrong_id_bits
    # Fault: device-ID read returns 0x0118 (lower 12 bits 0x118 ≠ 0x117).
    # Driver's identify() must raise DeviceIdentityError.
    # ------------------------------------------------------------------
    registry["fault_wrong_id_bits"] = ScenarioDef(
        scenario_id="fault_wrong_id_bits",
        description=(
            "Fault: device-ID lower 12 bits are 0x118 instead of 0x117. "
            "Driver must raise DeviceIdentityError."
        ),
        temperature_raw=0x0C80,
        fault_spec=FaultSpec(
            kind="wrong_id_bits",
            match_register=_REG_DEVICE_ID,
            match_operation="read",
            trigger_count=1,
        ),
        expectation=ScenarioExpectation(
            expected_celsius=None,
            expected_raw_bytes=None,
            expected_virtual_time_us=None,
            expected_exception=DeviceIdentityError,
            expected_behavior_description=(
                "identify() raises DeviceIdentityError because part ID 0x118 ≠ 0x117."
            ),
        ),
        applicable_drivers=frozenset({"baseline"}),
    )

    # ------------------------------------------------------------------
    # fault_short_temp
    # Fault: temperature register read returns 1 byte instead of 2.
    # Driver must raise ProtocolReadError.
    # The fault fires on the first read of register 0x00.
    # identify() and configure() read registers 0x0F and 0x01 — not affected.
    # ------------------------------------------------------------------
    registry["fault_short_temp"] = ScenarioDef(
        scenario_id="fault_short_temp",
        description=(
            "Fault: temperature register read returns 1 byte (short read). "
            "Driver must raise ProtocolReadError."
        ),
        temperature_raw=0x0C80,
        fault_spec=FaultSpec(
            kind="short_read",
            match_register=_REG_TEMPERATURE,
            match_operation="read",
            trigger_count=1,
        ),
        expectation=ScenarioExpectation(
            expected_celsius=None,
            expected_raw_bytes=None,
            expected_virtual_time_us=None,
            expected_exception=ProtocolReadError,
            expected_behavior_description=(
                "measure() raises ProtocolReadError after the short temperature read."
            ),
        ),
        applicable_drivers=frozenset({"baseline"}),
    )

    return registry


# Module-level registry — built once on first import.
SCENARIO_REGISTRY: dict[str, ScenarioDef] = _make_registry()


def get_scenario(scenario_id: str) -> ScenarioDef:
    """
    Look up a scenario by ID.

    Raises
    ------
    ValueError
        If ``scenario_id`` is not in the registry.
    """
    if scenario_id not in SCENARIO_REGISTRY:
        raise ValueError(
            f"Unknown scenario {scenario_id!r}. "
            f"Supported: {sorted(SCENARIO_REGISTRY)}"
        )
    return SCENARIO_REGISTRY[scenario_id]


def validate_driver_for_scenario(scenario_id: str, driver_variant: str) -> None:
    """
    Verify that ``driver_variant`` is applicable for ``scenario_id``.

    Raises
    ------
    ValueError
        If the combination is not supported.
    """
    if driver_variant not in SUPPORTED_DRIVER_VARIANTS:
        raise ValueError(
            f"Unknown driver variant {driver_variant!r}. "
            f"Supported: {sorted(SUPPORTED_DRIVER_VARIANTS)}"
        )
    scenario = get_scenario(scenario_id)
    if driver_variant not in scenario.applicable_drivers:
        raise ValueError(
            f"Driver variant {driver_variant!r} is not applicable for "
            f"scenario {scenario_id!r}. "
            f"Applicable: {sorted(scenario.applicable_drivers)}"
        )
