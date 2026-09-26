"""
DRIFT report assembly and JSON serialisation.

Responsibilities
----------------
- Convert a RunResult (mutable working state) to an immutable RunReport.
- Assemble JSON-serialisable report dicts with:
    - schema version
    - run ID, scenario ID, profile ID, driver variant
    - execution status (separate from assertion status)
    - device outcome (exception name or "measurement")
    - ordered assertions with expected/actual and fact IDs
    - ordered bus trace with all fields
    - verification status ("pass", "fail", "unsupported")
    - expected_behavior_observed flag
    - provenance block: contract hash, source hash, approval metadata
    - limitations caveat
- Support deterministic replay comparison: strip run_id and wall_time_s,
  then compare normalised trace dicts.

AGENTS.md boundaries:
  - Trace/report inspection cannot read device registers or mutate device state.
  - UI metrics and outcomes come from real reports.
  - Execution outcome is kept separate from assertion pass/fail.
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
from drift.runner import (
    REPORT_SCHEMA_VERSION,
    RunResult,
    _APPROVED_CONTRACT,
    _CONTRACT_SHA256,
    _SOURCE_SHA256,
    _REVIEWER,
    _APPROVED_UTC,
    _POLICY_TIMEOUT_US,
)
from drift.scenarios import CLI_PROFILE_ID, APPROVED_PROFILE_ID


# ---------------------------------------------------------------------------
# Serialisation helpers
# ---------------------------------------------------------------------------

def _trace_event_to_dict(ev: TraceEvent) -> dict[str, Any]:
    """Convert one TraceEvent to a JSON-serialisable dict."""
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
    """Convert one AssertionRecord to a JSON-serialisable dict."""
    # bytes expected values serialise as hex strings.
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
# RunResult → RunReport
# ---------------------------------------------------------------------------

def build_report(result: RunResult) -> RunReport:
    """
    Build an immutable RunReport from a RunResult.

    The verification_status is derived from assertions:
      - "pass"  if all assertions passed
      - "fail"  if any assertion failed
    The execution_status is kept separate (infrastructure error ≠ assertion fail).
    """
    all_passed = all(a.passed for a in result.assertions)
    verification_status = "pass" if all_passed else "fail"

    limitations = (
        "Selected profile only (one-shot, AVG=00, 0x48). "
        "No electrical, timing accuracy, or physical validation. "
        "Virtual clock; no real sleeps."
    )

    return RunReport(
        schema_version=REPORT_SCHEMA_VERSION,
        run_id=result.run_id,
        scenario_id=result.scenario_id,
        profile_id=CLI_PROFILE_ID,
        driver_variant=result.driver_variant,
        execution_status=result.execution_status,
        device_outcome=result.device_outcome,
        assertions=tuple(result.assertions),
        trace=result.trace,
        verification_status=verification_status,
        expected_behavior_observed=result.expected_behavior_observed,
        limitations=limitations,
    )


# ---------------------------------------------------------------------------
# RunReport → JSON dict
# ---------------------------------------------------------------------------

def report_to_dict(report: RunReport, result: RunResult) -> dict[str, Any]:
    """
    Assemble the full JSON-serialisable report dict.

    Includes a ``provenance`` block with contract/source hashes and approval
    metadata so every report is self-describing.

    ``result`` supplies wall_time_s and virtual_end_us (not in the frozen
    RunReport dataclass; kept separate to support normalisation).
    """
    provenance = {
        "contract_sha256": _CONTRACT_SHA256,
        "source_sha256": _SOURCE_SHA256,
        "approved_profile_id": APPROVED_PROFILE_ID,
        "reviewer": _REVIEWER,
        "approved_utc": _APPROVED_UTC,
        "source_document": (
            f"TI {_APPROVED_CONTRACT.contract.source.document} "
            f"Rev. {_APPROVED_CONTRACT.contract.source.revision}"
        ),
        "policy_timeout_us": _POLICY_TIMEOUT_US,
    }

    assertions_list = [_assertion_to_dict(a) for a in report.assertions]
    trace_list = [_trace_event_to_dict(ev) for ev in report.trace]

    return {
        "schema_version": report.schema_version,
        "run_id": report.run_id,
        "scenario_id": report.scenario_id,
        "profile_id": report.profile_id,
        "driver_variant": report.driver_variant,
        "execution_status": report.execution_status,
        "device_outcome": report.device_outcome,
        "verification_status": report.verification_status,
        "expected_behavior_observed": report.expected_behavior_observed,
        "assertions": assertions_list,
        "trace": trace_list,
        "provenance": provenance,
        "run_metadata": {
            "wall_time_s": round(result.wall_time_s, 6),
            "virtual_end_us": result.virtual_end_us,
        },
        "limitations": report.limitations,
    }


def save_report(report_dict: dict[str, Any], path: str | pathlib.Path) -> None:
    """Write the report dict as indented JSON to ``path``."""
    p = pathlib.Path(path)
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(
        json.dumps(report_dict, indent=2, default=str),
        encoding="utf-8",
    )


# ---------------------------------------------------------------------------
# Deterministic replay comparison
# ---------------------------------------------------------------------------

def normalise_for_replay(report_dict: dict[str, Any]) -> dict[str, Any]:
    """
    Return a copy of ``report_dict`` with run-specific fields stripped.

    The following fields vary between runs and are excluded from the
    deterministic-replay comparison:
      - run_id
      - run_metadata.wall_time_s

    The normalised dict can be compared with ``==`` across two fresh runs to
    verify deterministic replay.
    """
    import copy
    d = copy.deepcopy(report_dict)
    d.pop("run_id", None)
    d.get("run_metadata", {}).pop("wall_time_s", None)
    return d


# ---------------------------------------------------------------------------
# Verification summary (for --verify output)
# ---------------------------------------------------------------------------

def build_verification_summary(
    results: list[RunResult],
) -> dict[str, Any]:
    """
    Build a JSON-serialisable verification summary from a list of RunResults.

    Used by `drift.cli verify` to produce artifacts/verification.json.
    """
    reports = []
    for result in results:
        report = build_report(result)
        d = report_to_dict(report, result)
        reports.append(d)

    total = len(reports)
    passed = sum(1 for r in reports if r["verification_status"] == "pass")
    failed = total - passed

    provenance = {
        "contract_sha256": _CONTRACT_SHA256,
        "source_sha256": _SOURCE_SHA256,
        "approved_profile_id": APPROVED_PROFILE_ID,
        "reviewer": _REVIEWER,
        "approved_utc": _APPROVED_UTC,
        "source_document": (
            f"TI {_APPROVED_CONTRACT.contract.source.document} "
            f"Rev. {_APPROVED_CONTRACT.contract.source.revision}"
        ),
        "policy_timeout_us": _POLICY_TIMEOUT_US,
    }

    return {
        "schema_version": REPORT_SCHEMA_VERSION,
        "profile_id": CLI_PROFILE_ID,
        "provenance": provenance,
        "summary": {
            "total": total,
            "passed": passed,
            "failed": failed,
        },
        "runs": reports,
    }
