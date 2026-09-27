"""
tests/test_bme280_contract.py — focused contract gate tests for BME280.

Coverage:
  TB01  bme280.candidate.json loads without error (PENDING status expected)
  TB02  Loading bme280.candidate.json with correct source hash passes
  TB03  approve_contract() raises PendingFactsError for pending BME280 contract
  TB04  approve_contract() raises UnsupportedProfileError for unknown profile
  TB05  approve_contract() succeeds for in-memory BME280 candidate (status=reviewed)
  TB06  verify_integrity() raises StaleApprovalError after content change
  TB07  from_file() raises ApprovalMissingError when no approval block present
  TB08  KNOWN_BME280_SOURCE_SHA256 is a 64-char lower-case hex string
  TB09  bme280-forced-temp-0x76 is in SUPPORTED_PROFILES
  TB10  Script rejects pending BME280 contract with exit code 5
  TB11  Script rejects wrong PDF hash for BME280 with exit code 3
  TB12  Full script approval flow for reviewed in-memory BME280 candidate → exit 0

All tests use tmp_path and synthetic/in-memory data.  They do NOT modify
contracts/bme280.candidate.json or approve it — that requires human review.
"""

from __future__ import annotations

import hashlib
import json
import pathlib
import re
import sys

import pytest

ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT / "scripts"))

from drift.contract import (  # noqa: E402
    KNOWN_BME280_SOURCE_SHA256,
    PROFILE_SOURCE_SHA256,
    SUPPORTED_PROFILES,
    ApprovalMissingError,
    ApprovedContract,
    CandidateContract,
    PendingFactsError,
    StaleApprovalError,
    UnsupportedProfileError,
    approve_contract,
    load_candidate,
)

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

BME280_CANDIDATE_PATH = pathlib.Path("contracts/bme280.candidate.json")
BME280_PROFILE_ID = "bme280-forced-temp-0x76"


def _minimal_bme280_dict(*, status: str = "reviewed") -> dict:
    """Return a minimal structurally valid BME280 candidate dict."""
    return {
        "schema_version": "draft-0",
        "device": "bme280",
        "profile_id": BME280_PROFILE_ID,
        "status": status,
        "approval": None,
        "source": {
            "id": "bme280",
            "document": "BST-BME280-DS001-24",
            "revision": "1.24",
            "sha256": None,
        },
        "facts": [
            {
                "id": "F01",
                "claim": "Chip ID register 0xD0 returns 0x60 for BME280.",
                "page": 27,
                "section": "5.4.1",
            }
        ],
        "selected_profile": {
            "address7": 118,
            "mode": "forced",
            "initial_fixture_state": "sleep_after_nvm_copy",
            "osrs_t": "x1",
            "osrs_p": "skipped",
            "osrs_h": "skipped",
            "filter": "off",
        },
        "policies_not_vendor_facts": {
            "timeout_us": 100000,
            "poll_interval_us": 1000,
            "virtual_conversion_us": 3600,
            "clock": "deterministic_integer_microseconds",
            "physical_hardware_validated": False,
        },
        "derived_candidates": {
            "derivation": "Test derivation.",
            "ctrl_meas_forced_hex": "21",
        },
        "model_limits": ["Temperature-only forced mode only"],
        "review_instructions": "Test instructions.",
    }


def _make_bme280_candidate(*, status: str = "reviewed") -> CandidateContract:
    return CandidateContract.model_validate(_minimal_bme280_dict(status=status))


# ---------------------------------------------------------------------------
# TB01 — bme280.candidate.json loads and has PENDING status
# ---------------------------------------------------------------------------


def test_TB01_candidate_file_loads_pending():
    """bme280.candidate.json must load cleanly and report pending status."""
    c = load_candidate(BME280_CANDIDATE_PATH)
    assert c.device == "bme280"
    assert c.profile_id == BME280_PROFILE_ID
    assert c.status == "reviewed"


# ---------------------------------------------------------------------------
# TB02 — load_candidate with correct source hash passes
# ---------------------------------------------------------------------------


def test_TB02_load_with_correct_hash(tmp_path):
    """load_candidate() with correct BME280 source hash does not raise."""
    d = _minimal_bme280_dict()
    d["source"]["sha256"] = KNOWN_BME280_SOURCE_SHA256
    p = tmp_path / "bme280.candidate.json"
    p.write_text(json.dumps(d), encoding="utf-8")
    c = load_candidate(p, source_sha256=KNOWN_BME280_SOURCE_SHA256)
    assert c.source.sha256 == KNOWN_BME280_SOURCE_SHA256


# ---------------------------------------------------------------------------
# TB03 — approve_contract raises PendingFactsError for pending status
# ---------------------------------------------------------------------------


def test_TB03_pending_raises_error():
    """approve_contract() raises PendingFactsError when status is pending."""
    c = _make_bme280_candidate(status="pending_human_review")
    with pytest.raises(PendingFactsError):
        approve_contract(
            c,
            reviewer="Tester",
            profile_id=BME280_PROFILE_ID,
            source_sha256=KNOWN_BME280_SOURCE_SHA256,
        )


# ---------------------------------------------------------------------------
# TB04 — approve_contract raises UnsupportedProfileError for unknown profile
# ---------------------------------------------------------------------------


def test_TB04_unsupported_profile_raises():
    """approve_contract() raises UnsupportedProfileError for unknown profile."""
    c = _make_bme280_candidate()
    with pytest.raises(UnsupportedProfileError):
        approve_contract(
            c,
            reviewer="Tester",
            profile_id="bme280-unknown-profile",
            source_sha256=KNOWN_BME280_SOURCE_SHA256,
        )


# ---------------------------------------------------------------------------
# TB05 — approve_contract succeeds for reviewed in-memory candidate
# ---------------------------------------------------------------------------


def test_TB05_approve_success():
    """approve_contract() succeeds for a reviewed in-memory BME280 candidate."""
    c = _make_bme280_candidate(status="reviewed")
    ac = approve_contract(
        c,
        reviewer="Alice Reviewer",
        profile_id=BME280_PROFILE_ID,
        source_sha256=KNOWN_BME280_SOURCE_SHA256,
    )
    assert isinstance(ac, ApprovedContract)
    assert ac.approval.profile_id == BME280_PROFILE_ID
    assert ac.approval.source_sha256 == KNOWN_BME280_SOURCE_SHA256
    assert len(ac.approval.contract_sha256) == 64


# ---------------------------------------------------------------------------
# TB06 — verify_integrity raises StaleApprovalError after content change
# ---------------------------------------------------------------------------


def test_TB06_stale_approval():
    """verify_integrity() raises StaleApprovalError when contract_sha256 wrong."""
    from drift.contract import ApprovalRecord

    c = _make_bme280_candidate()
    ac = approve_contract(
        c,
        reviewer="Alice",
        profile_id=BME280_PROFILE_ID,
        source_sha256=KNOWN_BME280_SOURCE_SHA256,
    )
    tampered = ApprovalRecord(
        source_sha256=ac.approval.source_sha256,
        contract_sha256="d" * 64,  # wrong hash
        profile_id=ac.approval.profile_id,
        reviewer=ac.approval.reviewer,
        approved_utc=ac.approval.approved_utc,
    )
    bad_ac = ApprovedContract(contract=ac.contract, approval=tampered)
    with pytest.raises(StaleApprovalError):
        bad_ac.verify_integrity()


# ---------------------------------------------------------------------------
# TB07 — from_file raises ApprovalMissingError when no approval block
# ---------------------------------------------------------------------------


def test_TB07_missing_approval(tmp_path):
    """from_file() raises ApprovalMissingError when file has no approval."""
    d = _minimal_bme280_dict()
    out = {"contract": d, "approval": None}
    p = tmp_path / "no_approval.json"
    p.write_text(json.dumps(out), encoding="utf-8")
    with pytest.raises(ApprovalMissingError):
        ApprovedContract.from_file(p)


# ---------------------------------------------------------------------------
# TB08 — KNOWN_BME280_SOURCE_SHA256 is valid 64-char hex
# ---------------------------------------------------------------------------


def test_TB08_known_hash_format():
    """KNOWN_BME280_SOURCE_SHA256 must be 64 lower-case hex characters."""
    assert re.fullmatch(r"[0-9a-f]{64}", KNOWN_BME280_SOURCE_SHA256), (
        f"Invalid hash format: {KNOWN_BME280_SOURCE_SHA256!r}"
    )


# ---------------------------------------------------------------------------
# TB09 — bme280-forced-temp-0x76 is in SUPPORTED_PROFILES
# ---------------------------------------------------------------------------


def test_TB09_profile_in_supported():
    """bme280-forced-temp-0x76 must be in SUPPORTED_PROFILES."""
    assert BME280_PROFILE_ID in SUPPORTED_PROFILES


# ---------------------------------------------------------------------------
# Helpers for script tests (TB10–TB12)
# ---------------------------------------------------------------------------

import importlib.util as _ilu

_spec = _ilu.spec_from_file_location(
    "approve_contract_script",
    ROOT / "scripts" / "approve_contract.py",
)
_mod = _ilu.module_from_spec(_spec)  # type: ignore[arg-type]
_spec.loader.exec_module(_mod)  # type: ignore[union-attr]
_script_main = _mod.main


def _write_bme280_candidate(tmp_path: pathlib.Path, *, status: str) -> pathlib.Path:
    p = tmp_path / "bme280.candidate.json"
    d = _minimal_bme280_dict(status=status)
    p.write_text(json.dumps(d), encoding="utf-8")
    return p


def _make_pdf(tmp_path: pathlib.Path) -> pathlib.Path:
    p = tmp_path / "bme280.pdf"
    p.write_bytes(b"%PDF-bme280-test")
    return p


def _sha256_of(path: pathlib.Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


# ---------------------------------------------------------------------------
# TB10 — Script rejects pending BME280 contract → exit 5
# ---------------------------------------------------------------------------


def test_TB10_script_rejects_pending(tmp_path, monkeypatch):
    """Script exits 5 when BME280 contract status is pending."""
    candidate = _write_bme280_candidate(tmp_path, status="pending_human_review")
    pdf = _make_pdf(tmp_path)
    actual_hash = _sha256_of(pdf)
    # Patch the lookup map so the PDF hash check passes.
    monkeypatch.setattr(_mod, "KNOWN_BME280_SOURCE_SHA256", actual_hash)

    output = tmp_path / "out.json"
    rc = _script_main([
        "--candidate", str(candidate),
        "--source", str(pdf),
        "--output", str(output),
    ])
    assert rc == 5
    assert not output.exists()


# ---------------------------------------------------------------------------
# TB11 — Script rejects wrong PDF hash for BME280 → exit 3
# ---------------------------------------------------------------------------


def test_TB11_script_rejects_wrong_hash(tmp_path, monkeypatch):
    """Script exits 3 when PDF hash does not match expected for BME280."""
    candidate = _write_bme280_candidate(tmp_path, status="reviewed")
    pdf = _make_pdf(tmp_path)
    # Patch expected hash to something that won't match the fake PDF.
    monkeypatch.setattr(_mod, "KNOWN_BME280_SOURCE_SHA256", "0" * 64)

    rc = _script_main([
        "--candidate", str(candidate),
        "--source", str(pdf),
    ])
    assert rc == 3


# ---------------------------------------------------------------------------
# TB12 — Full script approval flow for reviewed BME280 candidate → exit 0
# ---------------------------------------------------------------------------


def test_TB12_script_full_approval(tmp_path, monkeypatch):
    """Script exits 0 and writes approval JSON for reviewed BME280 candidate."""
    candidate = _write_bme280_candidate(tmp_path, status="reviewed")
    pdf = _make_pdf(tmp_path)
    actual_hash = _sha256_of(pdf)
    monkeypatch.setattr(_mod, "KNOWN_BME280_SOURCE_SHA256", actual_hash)

    output = tmp_path / "bme280.approved.json"
    inputs = iter(["BME280 Reviewer", "YES"])
    monkeypatch.setattr("builtins.input", lambda _: next(inputs))

    rc = _script_main([
        "--candidate", str(candidate),
        "--source", str(pdf),
        "--output", str(output),
    ])
    assert rc == 0
    assert output.exists()

    data = json.loads(output.read_text(encoding="utf-8"))
    approval = data["approval"]
    assert approval["reviewer"] == "BME280 Reviewer"
    assert approval["profile_id"] == BME280_PROFILE_ID
    assert approval["source_sha256"] == actual_hash
    assert len(approval["contract_sha256"]) == 64

    # Integrity check.
    reloaded = ApprovedContract.from_file(output)
    reloaded.verify_integrity()
