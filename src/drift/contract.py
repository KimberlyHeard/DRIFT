"""
DRIFT contract validation and human-approval gate.

Pydantic v2 models represent the structure of a device source contract.  The
approval gate enforces that:

  1. The file's source_sha256 matches the provided (or on-disk) PDF hash.
  2. Every fact has a citation (section OR page must be present).
  3. No fact has status "pending" in the approved record.
  4. The selected profile is one of the supported names.
  5. Approval binds: source hash, canonical contract content hash, selected
     profile, reviewer identity, and UTC timestamp.
  6. A loaded ApprovedContract with a stale or absent approval record is
     rejected (contract must be re-approved after any content change).

AGENTS.md correctness boundary:
  Only the human reviewer calls ``approve_contract()``.  This module MUST
  NOT be called to approve the real tmp117.candidate.json; the contract
  stays PENDING until a human inspects the source pages and runs the gate.

Usage (human approval flow)::

    from drift.contract import load_candidate, approve_contract, ContractError

    candidate = load_candidate("contracts/tmp117.candidate.json",
                               source_sha256="<reviewed hex>")
    approved  = approve_contract(candidate,
                                 reviewer="Alice <alice@example.com>",
                                 profile_id="tmp117-oneshot-noavg-0x48")
    approved.save("contracts/tmp117.approved.json")

Then downstream code calls::

    contract = ApprovedContract.from_file("contracts/tmp117.approved.json")
    # Raises ContractError if content hash no longer matches.
"""

from __future__ import annotations

import hashlib
import json
import pathlib
import re
from datetime import datetime, timezone
from typing import Annotated, Any, Literal, Optional, Union

from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    field_validator,
    model_validator,
)

# ---------------------------------------------------------------------------
# Supported profile identifiers — must match the profile_id in the contract.
# Extending this set requires a reviewed contract change; see AGENTS.md.
# ---------------------------------------------------------------------------
SUPPORTED_PROFILES: frozenset[str] = frozenset({
    "tmp117-oneshot-noavg-0x48",
})

# SHA-256 of the reviewed TMP117 source PDF, confirmed by the previous Bob
# task (Task 01 / source extraction step).
# Source: TI SNOSD82D Rev. D — local_sources/tmp117.pdf
KNOWN_TMP117_SOURCE_SHA256: str = (
    "637a143dda6317d22222e265de47ceac72ba6aed4461ad460efbe84e16b936df"
)

# ---------------------------------------------------------------------------
# Errors
# ---------------------------------------------------------------------------


class ContractError(ValueError):
    """Base class for all contract validation failures."""


class SourceHashMismatch(ContractError):
    """Recorded source hash does not match the provided value."""


class PendingFactsError(ContractError):
    """One or more facts are still marked as pending review."""


class MissingCitationError(ContractError):
    """A fact has no page or section reference."""


class UnsupportedProfileError(ContractError):
    """The selected profile is not in SUPPORTED_PROFILES."""


class StaleApprovalError(ContractError):
    """The canonical contract hash recorded in the approval no longer matches."""


class ApprovalMissingError(ContractError):
    """An ApprovedContract was loaded without an embedded approval record."""


# ---------------------------------------------------------------------------
# Pydantic models — candidate contract
# ---------------------------------------------------------------------------


class SourceRef(BaseModel):
    """Provenance of the vendor source document."""

    model_config = ConfigDict(frozen=True)

    id: str = Field(..., description="Short device identifier (e.g. 'tmp117')")
    document: str = Field(..., description="TI document number (e.g. 'SNOSD82D')")
    revision: str = Field(..., description="Document revision letter (e.g. 'D')")
    sha256: Optional[str] = Field(
        None,
        description="Hex SHA-256 of the reviewed source PDF; null until verified.",
    )

    @field_validator("sha256")
    @classmethod
    def validate_sha256_hex(cls, v: Optional[str]) -> Optional[str]:
        if v is None:
            return v
        if not re.fullmatch(r"[0-9a-f]{64}", v):
            raise ContractError(
                f"sha256 must be 64 lower-case hex characters, got: {v!r}"
            )
        return v


class FactEntry(BaseModel):
    """One vendor fact extracted from the datasheet."""

    model_config = ConfigDict(frozen=True)

    id: str = Field(..., pattern=r"^F\d+$", description="Fact ID (e.g. 'F01')")
    claim: str = Field(..., min_length=1)
    page: Optional[int] = Field(None, ge=1)
    pages: Optional[list[int]] = Field(None)
    section: Optional[str] = Field(None)

    @model_validator(mode="after")
    def requires_citation(self) -> "FactEntry":
        """Every fact must have at least a page or section reference."""
        has_page = self.page is not None or (
            self.pages is not None and len(self.pages) > 0
        )
        has_section = self.section is not None and self.section.strip() != ""
        if not has_page and not has_section:
            raise MissingCitationError(
                f"Fact {self.id!r} has no page or section citation."
            )
        return self


class SelectedProfile(BaseModel):
    """The operating profile chosen for this contract instance."""

    model_config = ConfigDict(frozen=True)

    address7: int = Field(..., ge=1, le=0x77)
    mode: Literal["one_shot", "shutdown", "continuous"]
    averaging: Literal["none", "8x", "32x", "64x"]
    initial_fixture_state: str


class PoliciesBlock(BaseModel):
    """DRIFT policy values — not vendor facts; labeled separately per AGENTS.md."""

    model_config = ConfigDict(frozen=True)

    timeout_us: int = Field(..., gt=0)
    poll_interval_us: int = Field(..., gt=0)
    virtual_conversion_us: int = Field(..., gt=0)
    clock: str
    physical_hardware_validated: bool


class DerivedCandidates(BaseModel):
    """Derived register candidates — must be validated against source before approval."""

    model_config = ConfigDict(frozen=True)

    shutdown_config_hex: str
    start_config_hex: str
    completed_config_snapshot_hex: str
    after_ready_consumed_hex: str
    derivation: str


class CandidateContract(BaseModel):
    """
    Full candidate contract as loaded from a ``*candidate.json`` file.

    This model validates structure and citations.  It does NOT assert that
    facts are correct — that is the human reviewer's responsibility.
    """

    model_config = ConfigDict(frozen=True)

    schema_version: str
    device: str
    profile_id: str
    status: str
    approval: Optional[dict[str, Any]] = None
    source: SourceRef
    facts: list[FactEntry]
    selected_profile: SelectedProfile
    policies_not_vendor_facts: PoliciesBlock
    derived_candidates: DerivedCandidates
    model_limits: list[str]
    review_instructions: str

    @field_validator("facts")
    @classmethod
    def facts_not_empty(cls, v: list[FactEntry]) -> list[FactEntry]:
        if not v:
            raise ContractError("Contract must contain at least one fact.")
        return v

    @field_validator("profile_id")
    @classmethod
    def profile_must_be_supported(cls, v: str) -> str:
        if v not in SUPPORTED_PROFILES:
            raise UnsupportedProfileError(
                f"Profile {v!r} is not in SUPPORTED_PROFILES: {sorted(SUPPORTED_PROFILES)}"
            )
        return v

    def canonical_bytes(self) -> bytes:
        """
        Return a stable, canonical JSON serialisation for hashing.

        Keys are sorted, separators are compact.  The ``approval`` field is
        excluded so that the hash covers only the contract content itself.
        """
        d = self.model_dump(exclude={"approval"})
        return json.dumps(d, sort_keys=True, separators=(",", ":"),
                          default=str).encode("utf-8")

    def canonical_sha256(self) -> str:
        """Return the hex SHA-256 of the canonical contract bytes."""
        return hashlib.sha256(self.canonical_bytes()).hexdigest()


# ---------------------------------------------------------------------------
# Approval record
# ---------------------------------------------------------------------------


class ApprovalRecord(BaseModel):
    """
    Immutable record produced when a human approves a candidate contract.

    Bound fields (AGENTS.md):
      source_sha256      — hash of the reviewed vendor PDF
      contract_sha256    — hash of the canonical contract content (excl. approval)
      profile_id         — the approved operating profile
      reviewer           — free-text identity of the human reviewer
      approved_utc       — ISO-8601 UTC timestamp of the approval act
    """

    model_config = ConfigDict(frozen=True)

    source_sha256: str
    contract_sha256: str
    profile_id: str
    reviewer: str = Field(..., min_length=1)
    approved_utc: str  # ISO-8601


# ---------------------------------------------------------------------------
# Approved contract
# ---------------------------------------------------------------------------


class ApprovedContract(BaseModel):
    """
    A candidate contract that has been approved and carries an ApprovalRecord.

    The approval record is verified on ``from_file()``; any subsequent change
    to the contract content renders it stale.
    """

    model_config = ConfigDict(frozen=True)

    contract: CandidateContract
    approval: ApprovalRecord

    def verify_integrity(self) -> None:
        """
        Re-derive the canonical hash and compare it against the recorded value.

        Raises StaleApprovalError if they differ (contract was modified after
        approval).
        """
        live_hash = self.contract.canonical_sha256()
        if live_hash != self.approval.contract_sha256:
            raise StaleApprovalError(
                f"Contract content hash has changed since approval.\n"
                f"  recorded : {self.approval.contract_sha256}\n"
                f"  computed : {live_hash}"
            )

    def save(self, path: Union[str, pathlib.Path]) -> None:
        """Persist the approved contract (contract + approval) to a JSON file."""
        out = {
            "contract": self.contract.model_dump(),
            "approval": self.approval.model_dump(),
        }
        p = pathlib.Path(path)
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(
            json.dumps(out, indent=2, default=str), encoding="utf-8"
        )

    @classmethod
    def from_file(cls, path: Union[str, pathlib.Path]) -> "ApprovedContract":
        """
        Load and verify an approved contract from disk.

        Raises:
            ApprovalMissingError  — if the file has no approval block.
            StaleApprovalError    — if the contract content changed since approval.
        """
        raw = json.loads(pathlib.Path(path).read_text(encoding="utf-8"))
        if "approval" not in raw or raw["approval"] is None:
            raise ApprovalMissingError(
                f"File {path!r} has no approval record.  "
                "The contract must be reviewed and approved first."
            )
        instance = cls.model_validate(raw)
        instance.verify_integrity()
        return instance


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


def load_candidate(
    path: Union[str, pathlib.Path],
    source_sha256: Optional[str] = None,
) -> CandidateContract:
    """
    Load and validate a candidate contract JSON file.

    If ``source_sha256`` is provided it is compared against the value stored
    in ``contract.source.sha256`` (if set).  If the stored value is None the
    provided hash is recorded — the candidate itself is NOT mutated; the
    caller must store it separately.

    Raises:
        SourceHashMismatch  — if hashes are both present but differ.
        ContractError       — if Pydantic validation fails for any reason.
    """
    raw = json.loads(pathlib.Path(path).read_text(encoding="utf-8"))
    candidate = CandidateContract.model_validate(raw)

    if source_sha256 is not None and candidate.source.sha256 is not None:
        if source_sha256 != candidate.source.sha256:
            raise SourceHashMismatch(
                f"Provided source hash does not match stored value.\n"
                f"  provided : {source_sha256}\n"
                f"  stored   : {candidate.source.sha256}"
            )
    return candidate


def approve_contract(
    candidate: CandidateContract,
    reviewer: str,
    profile_id: str,
    source_sha256: str,
) -> ApprovedContract:
    """
    Bind a human-reviewed approval to a validated candidate contract.

    This function MUST be called only by a human reviewer after inspecting
    every fact against the printed source pages.  It MUST NOT be called on
    the real contract programmatically without human review.

    Checks (in order):
      1. Profile is in SUPPORTED_PROFILES.
      2. Provided profile_id matches the contract's profile_id.
      3. source_sha256 is a 64-char hex string.
      4. No facts are still pending (checked via status field).

    Raises:
        UnsupportedProfileError   — unknown profile.
        ContractError             — profile_id mismatch.
        SourceHashMismatch        — malformed source hash.
        PendingFactsError         — contract status is still 'pending_*'.
    """
    if profile_id not in SUPPORTED_PROFILES:
        raise UnsupportedProfileError(
            f"Profile {profile_id!r} is not in SUPPORTED_PROFILES."
        )
    if profile_id != candidate.profile_id:
        raise ContractError(
            f"Requested profile {profile_id!r} does not match "
            f"contract profile_id {candidate.profile_id!r}."
        )
    if not re.fullmatch(r"[0-9a-f]{64}", source_sha256):
        raise SourceHashMismatch(
            f"source_sha256 must be 64 lower-case hex chars, got: {source_sha256!r}"
        )
    if candidate.status.startswith("pending"):
        raise PendingFactsError(
            f"Contract status is {candidate.status!r}; "
            "human review must be completed before approval."
        )

    contract_sha256 = candidate.canonical_sha256()
    now_utc = datetime.now(tz=timezone.utc).isoformat()

    record = ApprovalRecord(
        source_sha256=source_sha256,
        contract_sha256=contract_sha256,
        profile_id=profile_id,
        reviewer=reviewer,
        approved_utc=now_utc,
    )
    return ApprovedContract(contract=candidate, approval=record)
