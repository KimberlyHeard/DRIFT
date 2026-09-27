"""
DRIFT BME280 scenario definitions — temperature-only forced-mode profile.

A scenario is a named, validated fixture definition that the BME280 runner
uses to construct a fresh execution stack (clock + device + bus + driver).
Public execution is limited to this registry of reviewed, named scenarios.

Scenario IDs
------------
  bme280_25c         — 25.08 °C fixture (raw 7E ED 00), no fault.
  bme280_neg8c       — -7.86 °C fixture (raw 65 5A C0), no fault.
  bme280_short_temp  — temperature read returns 2 bytes; driver raises ProtocolReadError.

Independent expected values for assertions (literal, not derived from code):
  bme280_25c:    celsius=25.08  raw=7e ed 00  time_us=4_000
  bme280_neg8c:  celsius=-7.86  raw=65 5a c0  time_us=4_000

  Derivation of 4 000 µs expected time:
    virtual_conversion_us = 3 600 µs (DRIFT policy, above 3.55 ms Bosch max).
    poll_interval = 1 000 µs.
    Poll 1 at t=1 000 µs: t < 3 600 → busy.
    Poll 2 at t=2 000 µs: t < 3 600 → busy.
    Poll 3 at t=3 000 µs: t < 3 600 → busy.
    Poll 4 at t=4 000 µs: t ≥ 3 600 → idle.
    Driver records virtual_time_us = 4 000.

  Calibration: dig_T1=27504, dig_T2=26435, dig_T3=-1000
    Bytes (LSB-first): 70 6B 43 67 18 FC.

  Raw 7E ED 00: adc_T = (0x7E<<12)|(0xED<<4)|(0x00>>4) = 519888 → 25.08 °C.
  Raw 65 5A C0: adc_T = (0x65<<12)|(0x5A<<4)|(0xC0>>4) = 415148 → -7.86 °C.
  Both values hand-verified against Bosch BST-BME280-DS001-24 §4.2.3 integer formula.

Source contract: contracts/bme280.approved.json
  profile_id: bme280-forced-temp-0x76
  approval: 2026-09-27T10:03:17Z by Kimberly Heard
  contract_sha256: 5b1ef2802b99e0e708dafae30de96f0bdacc5a349c0e9e6504d65a5f7f3bfa13
"""

from __future__ import annotations

import dataclasses
from typing import Optional, Type


# Approved BME280 profile and contract identifiers.
BME280_APPROVED_PROFILE_ID: str = "bme280-forced-temp-0x76"
BME280_CLI_PROFILE_ID: str = "bme280_forced_temp"

# Approved contract hash (from contracts/bme280.approved.json).
BME280_CONTRACT_SHA256: str = (
    "5b1ef2802b99e0e708dafae30de96f0bdacc5a349c0e9e6504d65a5f7f3bfa13"
)

# BME280 device address (SDO=GND, F02).
_BME280_ADDR: int = 0x76

# Calibration bytes fixture (dig_T1=27504, dig_T2=26435, dig_T3=-1000, LSB-first F03).
_CALIB_BYTES: bytes = bytes([0x70, 0x6B, 0x43, 0x67, 0x18, 0xFC])

# DRIFT policy: conversion time 3 600 µs (above 3.55 ms Bosch max, F12).
_CONVERSION_US: int = 3_600

# Raw temperature bytes (F04/F05 hand-verified).
_RAW_25C: bytes = bytes([0x7E, 0xED, 0x00])    # → 25.08 °C
_RAW_NEG8C: bytes = bytes([0x65, 0x5A, 0xC0])  # → -7.86 °C

# Supported driver variant names for BME280 scenarios.
BME280_SUPPORTED_DRIVER_VARIANTS: frozenset[str] = frozenset({"baseline"})


@dataclasses.dataclass(frozen=True)
class BME280ScenarioExpectation:
    """
    Independently prepared expected outcome for one BME280 scenario.

    Fields are literal values reviewed by a human; never derived from driver.
    """
    expected_celsius: Optional[float]
    expected_raw_bytes: Optional[bytes]
    expected_virtual_time_us: Optional[int]
    expected_exception: Optional[Type[Exception]]
    expected_behavior_description: str


@dataclasses.dataclass(frozen=True)
class BME280ScenarioDef:
    """Full definition of one named BME280 scenario."""
    scenario_id: str
    description: str
    calib_bytes: bytes
    temp_raw_bytes: bytes
    conversion_us: int
    fault_spec: Optional[object]          # BME280FaultSpec | None
    expectation: BME280ScenarioExpectation
    applicable_drivers: frozenset[str]


# ---------------------------------------------------------------------------
# Scenario registry
# ---------------------------------------------------------------------------

def _make_bme280_registry() -> dict[str, BME280ScenarioDef]:
    """Build and return the BME280 scenario registry."""
    from drift.interfaces import ProtocolReadError

    registry: dict[str, BME280ScenarioDef] = {}

    # ------------------------------------------------------------------
    # bme280_25c
    # Independent literals: Bosch BST-BME280-DS001-24 §4.2.3, hand-verified.
    #   adc_T = 519888; formula produces T=2508 (0.01 °C) → 25.08 °C.
    #   Poll timing: 4th poll at t=4000 µs clears status.
    # ------------------------------------------------------------------
    registry["bme280_25c"] = BME280ScenarioDef(
        scenario_id="bme280_25c",
        description="Baseline: 25.08 °C fixture (raw 7E ED 00), no fault.",
        calib_bytes=_CALIB_BYTES,
        temp_raw_bytes=_RAW_25C,
        conversion_us=_CONVERSION_US,
        fault_spec=None,
        expectation=BME280ScenarioExpectation(
            expected_celsius=25.08,
            expected_raw_bytes=_RAW_25C,
            expected_virtual_time_us=4_000,
            expected_exception=None,
            expected_behavior_description=(
                "Driver returns Measurement(celsius=25.08, "
                "raw_bytes=b'\\x7e\\xed\\x00', virtual_time_us=4000)."
            ),
        ),
        applicable_drivers=frozenset({"baseline"}),
    )

    # ------------------------------------------------------------------
    # bme280_neg8c
    # Independent literals: Bosch BST-BME280-DS001-24 §4.2.3, hand-verified.
    #   adc_T = 415148; formula produces T=-786 (0.01 °C) → -7.86 °C.
    # ------------------------------------------------------------------
    registry["bme280_neg8c"] = BME280ScenarioDef(
        scenario_id="bme280_neg8c",
        description="Baseline: -7.86 °C fixture (raw 65 5A C0), no fault.",
        calib_bytes=_CALIB_BYTES,
        temp_raw_bytes=_RAW_NEG8C,
        conversion_us=_CONVERSION_US,
        fault_spec=None,
        expectation=BME280ScenarioExpectation(
            expected_celsius=-7.86,
            expected_raw_bytes=_RAW_NEG8C,
            expected_virtual_time_us=4_000,
            expected_exception=None,
            expected_behavior_description=(
                "Driver returns Measurement(celsius=-7.86, "
                "raw_bytes=b'\\x65\\x5a\\xc0', virtual_time_us=4000)."
            ),
        ),
        applicable_drivers=frozenset({"baseline"}),
    )

    # ------------------------------------------------------------------
    # bme280_short_temp
    # Fault: temperature register read returns 2 bytes instead of 3.
    # Driver must raise ProtocolReadError.
    # ------------------------------------------------------------------
    registry["bme280_short_temp"] = BME280ScenarioDef(
        scenario_id="bme280_short_temp",
        description=(
            "Fault: temperature read returns 2 bytes (short read). "
            "Driver must raise ProtocolReadError."
        ),
        calib_bytes=_CALIB_BYTES,
        temp_raw_bytes=_RAW_25C,    # irrelevant; fault fires before result is used
        conversion_us=_CONVERSION_US,
        fault_spec={"kind": "short_temp"},  # interpreted by runner
        expectation=BME280ScenarioExpectation(
            expected_celsius=None,
            expected_raw_bytes=None,
            expected_virtual_time_us=None,
            expected_exception=ProtocolReadError,
            expected_behavior_description=(
                "measure() raises ProtocolReadError after 2-byte temperature read."
            ),
        ),
        applicable_drivers=frozenset({"baseline"}),
    )

    return registry


BME280_SCENARIO_REGISTRY: dict[str, BME280ScenarioDef] = _make_bme280_registry()


def get_bme280_scenario(scenario_id: str) -> BME280ScenarioDef:
    """Look up a BME280 scenario by ID.  Raises ValueError for unknown IDs."""
    if scenario_id not in BME280_SCENARIO_REGISTRY:
        raise ValueError(
            f"Unknown BME280 scenario {scenario_id!r}. "
            f"Supported: {sorted(BME280_SCENARIO_REGISTRY)}"
        )
    return BME280_SCENARIO_REGISTRY[scenario_id]
