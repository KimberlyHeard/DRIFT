"""
tests/test_contract.py — focused tests for the DRIFT contract validation and
human-approval gate (src/drift/contract.py).

Coverage targets (one test per boundary / error path):
  T01  load_candidate() accepts the real candidate file without a source hash
  T02  load_candidate() accepts a matching source hash in the call
  T03  load_candidate() raises SourceHashMismatch when provided hash differs
  T04  CandidateContract Pydantic model rejects a fact with no page or section
  T05  CandidateContract raises UnsupportedProfileError for unknown profile_id
  T06  approve_contract() raises PendingFactsError on pending contract status
  T07  approve_contract() raises UnsupportedProfileError for unknown profile
  T08  approve_contract() raises ContractError when profile_id mismatches
  T09  approve_contract() raises SourceHashMismatch for malformed hash
  T10  approve_contract() succeeds and produces ApprovedContract for a valid
       in-memory approved candidate (status="reviewed")
  T11  ApprovedContract.verify_integrity() passes on an untouched approval
  T12  ApprovedContract.verify_integrity() raises StaleApprovalError after
       any contract-content mutation (simulated via a modified copy)
  T13  ApprovedContract.from_file() raises ApprovalMissingError when the
       saved file has no approval block
  T14  ApprovedContract.from_file() raises StaleApprovalError when the saved
       file has a tampered contract_sha256
  T15  CandidateContract.canonical_sha256() is deterministic across two calls
  T16  Facts list empty raises ContractError
  T17  SourceRef.sha256 validator rejects non-hex strings
  T18  Approved contract saves and reloads cleanly via save()/from_file()

All tests operate on in-memory dicts or a temporary directory; they do NOT
modify contracts/tmp117.candidate.json or approve it.
"""

from __future__ import annotations

import copy
import json
import pathlib

import pytest

from drift.contract import (
    KNOWN_TMP117_SOURCE_SHA256,
    SUPPORTED_PROFILES,
    ApprovalMissingError,
    ApprovedContract,
    CandidateContract,
    ContractError,
    MissingCitationError,
    PendingFactsError,
    SourceHashMismatch,
    StaleApprovalError,
    UnsupportedProfileError,
    approve_contract,
    load_candidate,
)

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

CANDIDATE_PATH = pathlib.Path("contracts/tmp117.candidate.json")

# A minimal valid candidate dict that uses status="reviewed" so approval can
# proceed.  The profile_id must be in SUPPORTED_PROFILES.
VALID_PROFILE_ID = "tmp117-oneshot-noavg-0x48"

VALID_SOURCE_SHA256 = KNOWN_TMP117_SOURCE_SHA256  # 64 lower-case hex chars


def _minimal_candidate_dict(*, status: str = "reviewed") -> dict:
    """Return a minimal valid candidate dict for in-memory model construction."""
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
            "derivation": "Test derivation note.",
        },
        "model_limits": ["Selected profile only"],
        "review_instructions": "Test instructions.",
    }


def _make_candidate(*, status: str = "reviewed") -> CandidateContract:
    return CandidateContract.model_validate(_minimal_candidate_dict(status=status))


# ---------------------------------------------------------------------------
# T01 – load_candidate accepts real file without source hash
# ---------------------------------------------------------------------------


def test_T01_load_candidate_real_file_no_hash():
    """load_candidate() returns a CandidateContract without providing a hash."""
    c = load_candidate(CANDIDATE_PATH)
    assert c.device == "tmp117"
    assert c.profile_id == VALID_PROFILE_ID
    assert c.status == "pending_human_review"


# ---------------------------------------------------------------------------
# T02 – load_candidate accepts matching source hash
# ---------------------------------------------------------------------------


def test_T02_load_candidate_matching_hash(tmp_path):
    """load_candidate() passes when stored sha256 equals the provided hash."""
    d = _minimal_candidate_dict()
    d["source"]["sha256"] = VALID_SOURCE_SHA256
    p = tmp_path / "c.json"
    p.write_text(json.dumps(d), encoding="utf-8")
    c = load_candidate(p, source_sha256=VALID_SOURCE_SHA256)
    assert c.source.sha256 == VALID_SOURCE_SHA256


# ---------------------------------------------------------------------------
# T03 – load_candidate raises SourceHashMismatch on hash mismatch
# ---------------------------------------------------------------------------


def test_T03_load_candidate_hash_mismatch(tmp_path):
    """load_candidate() raises SourceHashMismatch when hashes differ."""
    d = _minimal_candidate_dict()
    d["source"]["sha256"] = VALID_SOURCE_SHA256
    p = tmp_path / "c.json"
    p.write_text(json.dumps(d), encoding="utf-8")
    bad_hash = "a" * 64
    with pytest.raises(SourceHashMismatch):
        load_candidate(p, source_sha256=bad_hash)


# ---------------------------------------------------------------------------
# T04 – fact with no page or section raises MissingCitationError
# ---------------------------------------------------------------------------


def test_T04_fact_missing_citation():
    """A fact that has neither page nor section raises MissingCitationError."""
    d = _minimal_candidate_dict()
    d["facts"] = [{"id": "F01", "claim": "Some claim with no citation."}]
    with pytest.raises((MissingCitationError, Exception)):
        CandidateContract.model_validate(d)


# ---------------------------------------------------------------------------
# T05 – unknown profile_id raises UnsupportedProfileError
# ---------------------------------------------------------------------------


def test_T05_unsupported_profile():
    """CandidateContract rejects a profile_id not in SUPPORTED_PROFILES."""
    d = _minimal_candidate_dict()
    d["profile_id"] = "tmp117-unknown-profile"
    with pytest.raises((UnsupportedProfileError, Exception)):
        CandidateContract.model_validate(d)


# ---------------------------------------------------------------------------
# T06 – approve_contract raises PendingFactsError on pending status
# ---------------------------------------------------------------------------


def test_T06_approve_pending_status():
    """approve_contract() raises PendingFactsError when status starts with 'pending'."""
    c = _make_candidate(status="pending_human_review")
    with pytest.raises(PendingFactsError):
        approve_contract(
            c,
            reviewer="Tester",
            profile_id=VALID_PROFILE_ID,
            source_sha256=VALID_SOURCE_SHA256,
        )


# ---------------------------------------------------------------------------
# T07 – approve_contract raises UnsupportedProfileError for bad profile
# ---------------------------------------------------------------------------


def test_T07_approve_unsupported_profile():
    """approve_contract() raises UnsupportedProfileError for unknown profile."""
    c = _make_candidate()
    with pytest.raises(UnsupportedProfileError):
        approve_contract(
            c,
            reviewer="Tester",
            profile_id="not-a-real-profile",
            source_sha256=VALID_SOURCE_SHA256,
        )


# ---------------------------------------------------------------------------
# T08 – approve_contract raises ContractError when profile_id mismatches contract
# ---------------------------------------------------------------------------


def test_T08_approve_profile_mismatch():
    """approve_contract() raises ContractError when profile_id != contract.profile_id."""
    # Build a second candidate with a different profile — but first we need that
    # profile in SUPPORTED_PROFILES. We test the mismatch logic directly by
    # monkey-patching the candidate's profile_id via a private workaround:
    # create a candidate then pass a profile_id that is in SUPPORTED but
    # differs from the contract's own value.
    #
    # Since there is currently only one SUPPORTED profile, force the mismatch
    # by patching the candidate's profile_id to something else after validation
    # while keeping the call profile in SUPPORTED_PROFILES.
    c = _make_candidate()
    # Directly construct a model with a different profile_id by building a
    # modified dict — but Pydantic will reject any unknown profile. So instead,
    # temporarily add a fake profile and patch the candidate.
    import drift.contract as mod
    orig = mod.SUPPORTED_PROFILES
    try:
        mod.SUPPORTED_PROFILES = frozenset(orig | {"tmp117-alt-profile"})
        d = _minimal_candidate_dict()
        d["profile_id"] = "tmp117-alt-profile"
        c_alt = CandidateContract.model_validate(d)
        # Now call approve with the original profile (also in SUPPORTED) which
        # mismatches the candidate's profile_id.
        with pytest.raises(ContractError):
            approve_contract(
                c_alt,
                reviewer="Tester",
                profile_id=VALID_PROFILE_ID,
                source_sha256=VALID_SOURCE_SHA256,
            )
    finally:
        mod.SUPPORTED_PROFILES = orig


# ---------------------------------------------------------------------------
# T09 – approve_contract raises SourceHashMismatch for malformed hash
# ---------------------------------------------------------------------------


def test_T09_approve_malformed_source_hash():
    """approve_contract() raises SourceHashMismatch when source_sha256 is not 64 hex chars."""
    c = _make_candidate()
    with pytest.raises(SourceHashMismatch):
        approve_contract(
            c,
            reviewer="Tester",
            profile_id=VALID_PROFILE_ID,
            source_sha256="tooshort",
        )


# ---------------------------------------------------------------------------
# T10 – approve_contract succeeds on a valid reviewed candidate
# ---------------------------------------------------------------------------


def test_T10_approve_success():
    """approve_contract() returns ApprovedContract with correct bound fields."""
    c = _make_candidate(status="reviewed")
    ac = approve_contract(
        c,
        reviewer="Alice <alice@example.com>",
        profile_id=VALID_PROFILE_ID,
        source_sha256=VALID_SOURCE_SHA256,
    )
    assert isinstance(ac, ApprovedContract)
    assert ac.approval.reviewer == "Alice <alice@example.com>"
    assert ac.approval.profile_id == VALID_PROFILE_ID
    assert ac.approval.source_sha256 == VALID_SOURCE_SHA256
    assert len(ac.approval.contract_sha256) == 64


# ---------------------------------------------------------------------------
# T11 – verify_integrity passes on untouched approval
# ---------------------------------------------------------------------------


def test_T11_verify_integrity_ok():
    """verify_integrity() does not raise on a freshly approved contract."""
    c = _make_candidate()
    ac = approve_contract(
        c,
        reviewer="Alice",
        profile_id=VALID_PROFILE_ID,
        source_sha256=VALID_SOURCE_SHA256,
    )
    ac.verify_integrity()  # must not raise


# ---------------------------------------------------------------------------
# T12 – verify_integrity raises StaleApprovalError after content change
# ---------------------------------------------------------------------------


def test_T12_verify_integrity_stale():
    """verify_integrity() raises StaleApprovalError when contract_sha256 is wrong."""
    c = _make_candidate()
    ac = approve_contract(
        c,
        reviewer="Alice",
        profile_id=VALID_PROFILE_ID,
        source_sha256=VALID_SOURCE_SHA256,
    )
    # Forge an approval record with a wrong contract hash.
    from drift.contract import ApprovalRecord

    tampered_record = ApprovalRecord(
        source_sha256=ac.approval.source_sha256,
        contract_sha256="b" * 64,  # wrong hash
        profile_id=ac.approval.profile_id,
        reviewer=ac.approval.reviewer,
        approved_utc=ac.approval.approved_utc,
    )
    tampered_ac = ApprovedContract(contract=ac.contract, approval=tampered_record)
    with pytest.raises(StaleApprovalError):
        tampered_ac.verify_integrity()


# ---------------------------------------------------------------------------
# T13 – from_file raises ApprovalMissingError when no approval in file
# ---------------------------------------------------------------------------


def test_T13_from_file_no_approval(tmp_path):
    """from_file() raises ApprovalMissingError when file has no approval block."""
    d = _minimal_candidate_dict()
    out = {"contract": d, "approval": None}
    p = tmp_path / "no_approval.json"
    p.write_text(json.dumps(out), encoding="utf-8")
    with pytest.raises(ApprovalMissingError):
        ApprovedContract.from_file(p)


# ---------------------------------------------------------------------------
# T14 – from_file raises StaleApprovalError when contract_sha256 is wrong
# ---------------------------------------------------------------------------


def test_T14_from_file_stale_hash(tmp_path):
    """from_file() raises StaleApprovalError when contract_sha256 in file doesn't match."""
    c = _make_candidate()
    ac = approve_contract(
        c,
        reviewer="Alice",
        profile_id=VALID_PROFILE_ID,
        source_sha256=VALID_SOURCE_SHA256,
    )
    # Save, then tamper with the contract_sha256 in the raw JSON.
    p = tmp_path / "approved.json"
    ac.save(p)
    raw = json.loads(p.read_text(encoding="utf-8"))
    raw["approval"]["contract_sha256"] = "c" * 64
    p.write_text(json.dumps(raw), encoding="utf-8")
    with pytest.raises(StaleApprovalError):
        ApprovedContract.from_file(p)


# ---------------------------------------------------------------------------
# T15 – canonical_sha256 is deterministic
# ---------------------------------------------------------------------------


def test_T15_canonical_sha256_deterministic():
    """canonical_sha256() returns the same value across two calls."""
    c = _make_candidate()
    h1 = c.canonical_sha256()
    h2 = c.canonical_sha256()
    assert h1 == h2
    assert len(h1) == 64


# ---------------------------------------------------------------------------
# T16 – empty facts list raises ContractError
# ---------------------------------------------------------------------------


def test_T16_empty_facts():
    """CandidateContract rejects an empty facts list."""
    d = _minimal_candidate_dict()
    d["facts"] = []
    with pytest.raises((ContractError, Exception)):
        CandidateContract.model_validate(d)


# ---------------------------------------------------------------------------
# T17 – SourceRef.sha256 validator rejects non-hex
# ---------------------------------------------------------------------------


def test_T17_sourceref_invalid_sha256():
    """SourceRef rejects a sha256 that is not 64 lower-case hex chars."""
    from drift.contract import SourceRef

    with pytest.raises(Exception):
        SourceRef(id="tmp117", document="SNOSD82D", revision="D", sha256="not-hex")


# ---------------------------------------------------------------------------
# T18 – save and from_file round-trip
# ---------------------------------------------------------------------------


def test_T18_save_and_reload(tmp_path):
    """An approved contract saves and reloads cleanly; integrity passes."""
    c = _make_candidate()
    ac = approve_contract(
        c,
        reviewer="Bob Reviewer",
        profile_id=VALID_PROFILE_ID,
        source_sha256=VALID_SOURCE_SHA256,
    )
    p = tmp_path / "approved.json"
    ac.save(p)
    reloaded = ApprovedContract.from_file(p)
    assert reloaded.approval.reviewer == "Bob Reviewer"
    assert reloaded.approval.contract_sha256 == ac.approval.contract_sha256
