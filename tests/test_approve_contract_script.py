"""
tests/test_approve_contract_script.py — focused tests for
scripts/approve_contract.py.

Coverage targets:
  TA01  Hash mismatch on PDF → exit code 3, no output file written
  TA02  Candidate file missing → exit code 2
  TA03  Source PDF missing → exit code 2
  TA04  Contract status "pending_*" → exit code 5, no output file
  TA05  Interactive abort (empty reviewer name) → exit code 6, no output file
  TA06  Interactive abort (confirmation not "YES") → exit code 6
  TA07  Full approval flow with correct hash, reviewed status, "YES" confirmation
        → exit code 0, approved JSON written with correct fields
  TA08  --output flag controls the destination path
  TA09  Written approved.json survives ApprovedContract.from_file() integrity check
  TA10  Structurally invalid candidate JSON → exit code 4
  TA11  PDF hash matches but contract source sha256 mismatch stored value → exit code 3

All tests use tmp_path and synthetic files; they never touch the real
contracts/tmp117.candidate.json or local_sources/tmp117.pdf.
"""

from __future__ import annotations

import hashlib
import json
import pathlib
import sys
import textwrap

import pytest

# Make src/ importable when pytest is run from the repo root.
ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT / "scripts"))

from drift.contract import (  # noqa: E402
    ApprovedContract,
    KNOWN_TMP117_SOURCE_SHA256,
)

# Import the script module so we can call main() directly.
import importlib.util as _ilu  # noqa: E402

_spec = _ilu.spec_from_file_location(
    "approve_contract_script",
    ROOT / "scripts" / "approve_contract.py",
)
_mod = _ilu.module_from_spec(_spec)  # type: ignore[arg-type]
_spec.loader.exec_module(_mod)  # type: ignore[union-attr]
_main = _mod.main

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

VALID_PROFILE_ID = "tmp117-oneshot-noavg-0x48"


def _make_fake_pdf(tmp_path: pathlib.Path, content: bytes = b"%PDF-fake") -> pathlib.Path:
    """Write a tiny fake PDF and return its path."""
    p = tmp_path / "fake.pdf"
    p.write_bytes(content)
    return p


def _sha256_of(path: pathlib.Path) -> str:
    h = hashlib.sha256(path.read_bytes()).hexdigest()
    return h


def _minimal_candidate_dict(*, status: str = "reviewed") -> dict:
    return {
        "schema_version": "draft-0",
        "device": "tmp117",
        "profile_id": VALID_PROFILE_ID,
        "status": status,
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
                "page": 21,
                "section": "Table 7-2",
                "claim": "ADD0 tied to ground selects seven-bit I2C address 0x48.",
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
            "derivation": "Test derivation.",
        },
        "model_limits": ["Selected profile only"],
        "review_instructions": "Test instructions.",
    }


def _write_candidate(tmp_path: pathlib.Path, *, status: str = "reviewed") -> pathlib.Path:
    p = tmp_path / "candidate.json"
    p.write_text(json.dumps(_minimal_candidate_dict(status=status)), encoding="utf-8")
    return p


def _make_pdf_with_known_hash(tmp_path: pathlib.Path) -> pathlib.Path:
    """
    Write a file whose SHA-256 equals KNOWN_TMP117_SOURCE_SHA256 by brute-force
    is impossible, so instead we patch the constant inside the script module.
    Returns (pdf_path, actual_hash).
    """
    p = tmp_path / "source.pdf"
    p.write_bytes(b"%PDF-test-content-for-approval-tests")
    return p


# ---------------------------------------------------------------------------
# TA01 — PDF hash mismatch → exit 3
# ---------------------------------------------------------------------------


def test_TA01_hash_mismatch(tmp_path, monkeypatch):
    """Hash of supplied PDF does not match KNOWN_TMP117_SOURCE_SHA256 → exit 3."""
    candidate = _write_candidate(tmp_path)
    pdf = _make_fake_pdf(tmp_path)
    # The fake PDF will never match the known hash.
    monkeypatch.setattr(_mod, "KNOWN_TMP117_SOURCE_SHA256", "0" * 64)
    rc = _main([
        "--candidate", str(candidate),
        "--source", str(pdf),
    ])
    assert rc == 3


# ---------------------------------------------------------------------------
# TA02 — Missing candidate file → exit 2
# ---------------------------------------------------------------------------


def test_TA02_missing_candidate(tmp_path, monkeypatch):
    """Candidate file does not exist → exit 2."""
    pdf = _make_fake_pdf(tmp_path)
    rc = _main([
        "--candidate", str(tmp_path / "nonexistent.json"),
        "--source", str(pdf),
    ])
    assert rc == 2


# ---------------------------------------------------------------------------
# TA03 — Missing source PDF → exit 2
# ---------------------------------------------------------------------------


def test_TA03_missing_source(tmp_path):
    """Source PDF does not exist → exit 2."""
    candidate = _write_candidate(tmp_path)
    rc = _main([
        "--candidate", str(candidate),
        "--source", str(tmp_path / "no_such.pdf"),
    ])
    assert rc == 2


# ---------------------------------------------------------------------------
# TA04 — Pending contract status → exit 5
# ---------------------------------------------------------------------------


def test_TA04_pending_status(tmp_path, monkeypatch):
    """Contract status 'pending_*' → exit 5, no approval file written."""
    candidate = _write_candidate(tmp_path, status="pending_human_review")
    pdf = _make_pdf_with_known_hash(tmp_path)
    actual_hash = _sha256_of(pdf)
    monkeypatch.setattr(_mod, "KNOWN_TMP117_SOURCE_SHA256", actual_hash)

    output = tmp_path / "out.json"
    rc = _main([
        "--candidate", str(candidate),
        "--source", str(pdf),
        "--output", str(output),
    ])
    assert rc == 5
    assert not output.exists()


# ---------------------------------------------------------------------------
# TA05 — Empty reviewer name → exit 6
# ---------------------------------------------------------------------------


def test_TA05_abort_empty_reviewer(tmp_path, monkeypatch):
    """Empty reviewer name → exit 6, no output file written."""
    candidate = _write_candidate(tmp_path)
    pdf = _make_pdf_with_known_hash(tmp_path)
    actual_hash = _sha256_of(pdf)
    monkeypatch.setattr(_mod, "KNOWN_TMP117_SOURCE_SHA256", actual_hash)

    output = tmp_path / "out.json"
    # Simulate pressing Enter (empty string) for the reviewer name.
    inputs = iter(["", "YES"])
    monkeypatch.setattr("builtins.input", lambda _: next(inputs))

    rc = _main([
        "--candidate", str(candidate),
        "--source", str(pdf),
        "--output", str(output),
    ])
    assert rc == 6
    assert not output.exists()


# ---------------------------------------------------------------------------
# TA06 — Confirmation not "YES" → exit 6
# ---------------------------------------------------------------------------


def test_TA06_abort_wrong_confirmation(tmp_path, monkeypatch):
    """Typing 'no' instead of 'YES' → exit 6, no output file."""
    candidate = _write_candidate(tmp_path)
    pdf = _make_pdf_with_known_hash(tmp_path)
    actual_hash = _sha256_of(pdf)
    monkeypatch.setattr(_mod, "KNOWN_TMP117_SOURCE_SHA256", actual_hash)

    output = tmp_path / "out.json"
    inputs = iter(["Reviewer Name", "no"])
    monkeypatch.setattr("builtins.input", lambda _: next(inputs))

    rc = _main([
        "--candidate", str(candidate),
        "--source", str(pdf),
        "--output", str(output),
    ])
    assert rc == 6
    assert not output.exists()


# ---------------------------------------------------------------------------
# TA07 — Full successful flow → exit 0, approved JSON written
# ---------------------------------------------------------------------------


def test_TA07_full_approval_success(tmp_path, monkeypatch):
    """Correct hash + reviewed status + 'YES' → exit 0, approved JSON written."""
    candidate = _write_candidate(tmp_path, status="reviewed")
    pdf = _make_pdf_with_known_hash(tmp_path)
    actual_hash = _sha256_of(pdf)
    monkeypatch.setattr(_mod, "KNOWN_TMP117_SOURCE_SHA256", actual_hash)

    output = tmp_path / "approved.json"
    inputs = iter(["Alice Reviewer", "YES"])
    monkeypatch.setattr("builtins.input", lambda _: next(inputs))

    rc = _main([
        "--candidate", str(candidate),
        "--source", str(pdf),
        "--output", str(output),
    ])
    assert rc == 0
    assert output.exists()

    data = json.loads(output.read_text(encoding="utf-8"))
    approval = data["approval"]
    assert approval["reviewer"] == "Alice Reviewer"
    assert approval["profile_id"] == VALID_PROFILE_ID
    assert approval["source_sha256"] == actual_hash
    assert len(approval["contract_sha256"]) == 64
    assert "approved_utc" in approval


# ---------------------------------------------------------------------------
# TA08 — --output flag controls destination
# ---------------------------------------------------------------------------


def test_TA08_custom_output_path(tmp_path, monkeypatch):
    """--output flag places the approved contract at the specified path."""
    candidate = _write_candidate(tmp_path)
    pdf = _make_pdf_with_known_hash(tmp_path)
    actual_hash = _sha256_of(pdf)
    monkeypatch.setattr(_mod, "KNOWN_TMP117_SOURCE_SHA256", actual_hash)

    custom_output = tmp_path / "subdir" / "custom_name.json"
    inputs = iter(["Reviewer B", "YES"])
    monkeypatch.setattr("builtins.input", lambda _: next(inputs))

    rc = _main([
        "--candidate", str(candidate),
        "--source", str(pdf),
        "--output", str(custom_output),
    ])
    assert rc == 0
    assert custom_output.exists()


# ---------------------------------------------------------------------------
# TA09 — Written file passes ApprovedContract.from_file() integrity check
# ---------------------------------------------------------------------------


def test_TA09_integrity_after_write(tmp_path, monkeypatch):
    """Approved JSON passes ApprovedContract.from_file() integrity verification."""
    candidate = _write_candidate(tmp_path)
    pdf = _make_pdf_with_known_hash(tmp_path)
    actual_hash = _sha256_of(pdf)
    monkeypatch.setattr(_mod, "KNOWN_TMP117_SOURCE_SHA256", actual_hash)

    output = tmp_path / "approved.json"
    inputs = iter(["Integrity Tester", "YES"])
    monkeypatch.setattr("builtins.input", lambda _: next(inputs))

    rc = _main([
        "--candidate", str(candidate),
        "--source", str(pdf),
        "--output", str(output),
    ])
    assert rc == 0

    reloaded = ApprovedContract.from_file(output)
    reloaded.verify_integrity()  # must not raise
    assert reloaded.approval.reviewer == "Integrity Tester"


# ---------------------------------------------------------------------------
# TA10 — Structurally invalid candidate JSON → exit 4
# ---------------------------------------------------------------------------


def test_TA10_invalid_candidate_json(tmp_path, monkeypatch):
    """Structurally invalid candidate (missing required fields) → exit 4."""
    bad = tmp_path / "bad.json"
    bad.write_text('{"schema_version": "draft-0"}', encoding="utf-8")
    pdf = _make_pdf_with_known_hash(tmp_path)
    actual_hash = _sha256_of(pdf)
    monkeypatch.setattr(_mod, "KNOWN_TMP117_SOURCE_SHA256", actual_hash)

    rc = _main([
        "--candidate", str(bad),
        "--source", str(pdf),
    ])
    assert rc == 4


# ---------------------------------------------------------------------------
# TA11 — Candidate has stored sha256 that differs from PDF hash → exit 3
# ---------------------------------------------------------------------------


def test_TA11_stored_sha256_mismatch(tmp_path, monkeypatch):
    """Candidate stores a sha256 that differs from the computed PDF hash → exit 3."""
    d = _minimal_candidate_dict()
    d["source"]["sha256"] = "a" * 64  # stored hash that won't match the PDF
    p = tmp_path / "candidate.json"
    p.write_text(json.dumps(d), encoding="utf-8")

    pdf = _make_pdf_with_known_hash(tmp_path)
    actual_hash = _sha256_of(pdf)
    # Make the PDF hash match KNOWN so we pass step 2,
    # but the stored sha256 in the contract differs from actual_hash.
    monkeypatch.setattr(_mod, "KNOWN_TMP117_SOURCE_SHA256", actual_hash)

    rc = _main([
        "--candidate", str(p),
        "--source", str(pdf),
    ])
    assert rc == 3


# ---------------------------------------------------------------------------
# TA12 — Default output filename: tmp117.candidate.json → tmp117.approved.json
# ---------------------------------------------------------------------------


def test_TA12_default_output_filename(tmp_path, monkeypatch):
    """Without --output, candidate 'foo.candidate.json' produces 'foo.approved.json'."""
    # Write candidate as <tmp_path>/tmp117.candidate.json so the stem is
    # "tmp117.candidate" — matching the real contract's naming convention.
    candidate = tmp_path / "tmp117.candidate.json"
    candidate.write_text(
        json.dumps(_minimal_candidate_dict(status="reviewed")), encoding="utf-8"
    )
    pdf = _make_pdf_with_known_hash(tmp_path)
    actual_hash = _sha256_of(pdf)
    monkeypatch.setattr(_mod, "KNOWN_TMP117_SOURCE_SHA256", actual_hash)

    inputs = iter(["Default Reviewer", "YES"])
    monkeypatch.setattr("builtins.input", lambda _: next(inputs))

    rc = _main([
        "--candidate", str(candidate),
        "--source", str(pdf),
        # No --output supplied.
    ])
    assert rc == 0

    expected_output = tmp_path / "tmp117.approved.json"
    assert expected_output.exists(), (
        f"Expected {expected_output.name} but it was not created. "
        f"Files present: {[f.name for f in tmp_path.iterdir()]}"
    )
    # Confirm it is a valid approved contract.
    data = json.loads(expected_output.read_text(encoding="utf-8"))
    assert data["approval"]["reviewer"] == "Default Reviewer"
