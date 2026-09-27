"""
DRIFT BME280 report assembly and JSON serialisation.

Builds JSON-serialisable report dicts from BME280RunResult instances.
Mirrors the structure of reporting.py for TMP117 with BME280-specific provenance.
"""

from __future__ import annotations

import json
import pathlib
from typing import Any

from drift.interfaces import (
    AssertionRecord,
    RunReport,
    TraceEvent,
)
from drift.runner_bme280 import (
    BME280_REPORT_SCHEMA_VERSION,
    BME280RunResult,
    _BME280_APPROVED_CONTRACT,
    _BME280_CONTRACT_SHA256,
    _BME280_SOURCE_SHA256,
    _BME280_REVIEWER,
    _BME280_APPROVED_UTC,
    _BME280_POLICY_TIMEOUT_US,
)
from drift.scenarios_bme280 import BME280_CLI_PROFILE_ID, BME280_APPROVED_PROFILE_ID


# ---------------------------------------------------------------------------
# Serialisation helpers
# ---------------------------------------------------------------------------

def _trace_event_to_dict(ev: TraceEvent) -> dict[str, Any]:
    return {
        "sequence": ev.sequence,
        "virtual_time_us": ev.virtual_time_us,
        "address_7bit": f"0x{ev.address_7bit:02X}",
        "register": f"0x{ev.register:02X}",
        "operation": ev.operation,
        "sent_bytes": ev.sent_bytes.hex() if ev.sent_bytes else "",
        "received_bytes": ev.received_bytes.hex() if ev.received_bytes else "",
        "outcome": ev.outcome,
        "fact_ids": list(ev.fact_ids),
    }


def _assertion_to_dict(rec: AssertionRecord) -> dict[str, Any]:
    expected = rec.expected
    if isinstance(expected, bytes):
        expected = expected.hex()
    actual = rec.actual
    if isinstance(actual, bytes):
        actual = actual.hex()
    return {
        "assertion_id": rec.assertion_id,
        "expected": expected,
        "actual": actual,
        "passed": rec.passed,
        "fact_ids": list(rec.fact_ids),
        "trace_indices": list(rec.trace_indices),
    }


# ---------------------------------------------------------------------------
# BME280RunResult → JSON dict
# ---------------------------------------------------------------------------

def bme280_report_to_dict(result: BME280RunResult) -> dict[str, Any]:
    """
    Assemble the full JSON-serialisable BME280 report dict.

    Includes provenance block with contract/source hashes and approval metadata.
    """
    all_passed = all(a.passed for a in result.assertions)
    verification_status = "pass" if all_passed else "fail"

    provenance = {
        "contract_sha256": _BME280_CONTRACT_SHA256,
        "source_sha256": _BME280_SOURCE_SHA256,
        "approved_profile_id": BME280_APPROVED_PROFILE_ID,
        "reviewer": _BME280_REVIEWER,
        "approved_utc": _BME280_APPROVED_UTC,
        "source_document": (
            f"Bosch {_BME280_APPROVED_CONTRACT.contract.source.document} "
            f"Rev. {_BME280_APPROVED_CONTRACT.contract.source.revision}"
        ),
        "policy_timeout_us": _BME280_POLICY_TIMEOUT_US,
    }

    limitations = (
        "Temperature-only forced mode profile (bme280-forced-temp-0x76). "
        "Pressure and humidity not implemented. "
        "No IIR filter. No electrical, timing accuracy, or physical validation. "
        "Virtual clock; no real sleeps."
    )

    return {
        "schema_version": BME280_REPORT_SCHEMA_VERSION,
        "run_id": result.run_id,
        "scenario_id": result.scenario_id,
        "profile_id": BME280_CLI_PROFILE_ID,
        "driver_variant": result.driver_variant,
        "execution_status": result.execution_status,
        "device_outcome": result.device_outcome,
        "verification_status": verification_status,
        "expected_behavior_observed": result.expected_behavior_observed,
        "assertions": [_assertion_to_dict(a) for a in result.assertions],
        "trace": [_trace_event_to_dict(ev) for ev in result.trace],
        "provenance": provenance,
        "run_metadata": {
            "wall_time_s": round(result.wall_time_s, 6),
            "virtual_end_us": result.virtual_end_us,
        },
        "limitations": limitations,
    }


def save_bme280_report(report_dict: dict[str, Any], path: str | pathlib.Path) -> None:
    """Write the BME280 report dict as indented JSON to ``path``."""
    p = pathlib.Path(path)
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(
        json.dumps(report_dict, indent=2, default=str),
        encoding="utf-8",
    )


def build_bme280_verification_summary(
    results: list[BME280RunResult],
) -> dict[str, Any]:
    """
    Build a JSON-serialisable BME280 verification summary.

    Used by the runner to produce artifacts/bme280_verification.json.
    """
    reports = [bme280_report_to_dict(r) for r in results]
    total = len(reports)
    passed = sum(1 for r in reports if r["verification_status"] == "pass")
    failed = total - passed

    provenance = {
        "contract_sha256": _BME280_CONTRACT_SHA256,
        "source_sha256": _BME280_SOURCE_SHA256,
        "approved_profile_id": BME280_APPROVED_PROFILE_ID,
        "reviewer": _BME280_REVIEWER,
        "approved_utc": _BME280_APPROVED_UTC,
        "source_document": (
            f"Bosch {_BME280_APPROVED_CONTRACT.contract.source.document} "
            f"Rev. {_BME280_APPROVED_CONTRACT.contract.source.revision}"
        ),
        "policy_timeout_us": _BME280_POLICY_TIMEOUT_US,
    }

    return {
        "schema_version": BME280_REPORT_SCHEMA_VERSION,
        "profile_id": BME280_CLI_PROFILE_ID,
        "provenance": provenance,
        "summary": {
            "total": total,
            "passed": passed,
            "failed": failed,
        },
        "runs": reports,
    }
