"""
DRIFT human-approval gate for a candidate device contract.

CLI usage (PowerShell)::

    .venv/Scripts/python.exe scripts/approve_contract.py
        --candidate contracts/tmp117.candidate.json
        --source   local_sources/tmp117.pdf

What this script does
---------------------
1. Hash the supplied PDF and compare it to the known value recorded in
   ``src/drift/contract.py:KNOWN_TMP117_SOURCE_SHA256``.  Refuse on mismatch.
2. Load and validate the candidate contract via ``drift.contract.load_candidate()``.
   Refuse if any citation is missing, the profile is unsupported, or the JSON
   is structurally invalid.
3. Display every fact, the selected profile, all DRIFT policies, and the
   canonical contract hash so the reviewer can verify them on screen.
4. Refuse if the contract status is still ``"pending_*"`` — the reviewer must
   change it to ``"reviewed"`` manually before running this script.
5. Prompt the reviewer to enter their name and an explicit ``YES`` confirmation.
   Any other input aborts without writing any output.
6. Call ``approve_contract()`` and write ``contracts/tmp117.approved.json``
   containing source hash, contract hash, reviewer name, and UTC timestamp.

This script MUST NOT be used to approve a contract without human review.
The script itself NEVER supplies the confirmation or reviewer name.
"""

from __future__ import annotations

import argparse
import hashlib
import pathlib
import sys
import textwrap

# Ensure the src/ tree is importable when run directly from the repo root.
ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from pydantic import ValidationError as _PydanticValidationError  # noqa: E402

from drift.contract import (  # noqa: E402
    KNOWN_TMP117_SOURCE_SHA256,
    SUPPORTED_PROFILES,
    ContractError,
    MissingCitationError,
    PendingFactsError,
    SourceHashMismatch,
    UnsupportedProfileError,
    approve_contract,
    load_candidate,
)

# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------


def _hash_file(path: pathlib.Path) -> str:
    """Return the lower-case hex SHA-256 of a file."""
    h = hashlib.sha256()
    with path.open("rb") as fh:
        for chunk in iter(lambda: fh.read(65536), b""):
            h.update(chunk)
    return h.hexdigest()


def _hr(char: str = "─", width: int = 72) -> str:
    return char * width


def _section(title: str) -> None:
    print()
    print(_hr())
    print(f"  {title}")
    print(_hr())


def _display_contract(candidate) -> None:
    """Print a structured summary of the candidate contract for review."""
    _section("SOURCE")
    src = candidate.source
    print(f"  Document  : {src.document} Rev. {src.revision}")
    print(f"  Source ID : {src.id}")
    print(f"  SHA-256   : {src.sha256 or '(not embedded in contract)'}")

    _section("FACTS  [TI facts — verified against printed pages]")
    for f in candidate.facts:
        page_str = ""
        if f.page is not None:
            page_str = f"p.{f.page}"
        elif f.pages:
            page_str = "p." + ",".join(str(p) for p in f.pages)
        section_str = f"  §{f.section}" if f.section else ""
        citation = f"[{page_str}{section_str}]" if (page_str or section_str) else "[NO CITATION]"
        print(f"  {f.id}  {citation}")
        for line in textwrap.wrap(f.claim, width=66, initial_indent="       ", subsequent_indent="       "):
            print(line)

    _section("SELECTED PROFILE  [derived from TI facts + DRIFT policy]")
    sp = candidate.selected_profile
    print(f"  profile_id            : {candidate.profile_id}")
    print(f"  address7              : 0x{sp.address7:02X}  ({sp.address7})")
    print(f"  mode                  : {sp.mode}")
    print(f"  averaging             : {sp.averaging}")
    print(f"  initial_fixture_state : {sp.initial_fixture_state}")

    _section("DERIVED REGISTER CANDIDATES  [derived — NOT vendor facts]")
    dc = candidate.derived_candidates
    print(f"  shutdown_config_hex             : {dc.shutdown_config_hex}")
    print(f"  start_config_hex                : {dc.start_config_hex}")
    print(f"  completed_config_snapshot_hex   : {dc.completed_config_snapshot_hex}")
    print(f"  after_ready_consumed_hex        : {dc.after_ready_consumed_hex}")
    print()
    for line in textwrap.wrap(dc.derivation, width=68, initial_indent="  Note: ", subsequent_indent="        "):
        print(line)

    _section("DRIFT POLICIES  [project decisions — NOT vendor facts]")
    pol = candidate.policies_not_vendor_facts
    print(f"  timeout_us                  : {pol.timeout_us}")
    print(f"  poll_interval_us            : {pol.poll_interval_us}")
    print(f"  virtual_conversion_us       : {pol.virtual_conversion_us}")
    print(f"  clock                       : {pol.clock}")
    print(f"  physical_hardware_validated : {pol.physical_hardware_validated}")

    _section("MODEL LIMITS")
    for limit in candidate.model_limits:
        print(f"  • {limit}")


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------


def main(argv: list[str] | None = None) -> int:
    """Entry point; returns exit code."""
    parser = argparse.ArgumentParser(
        description=__doc__,
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument(
        "--candidate",
        required=True,
        metavar="PATH",
        help="Path to the candidate contract JSON file.",
    )
    parser.add_argument(
        "--source",
        required=True,
        metavar="PATH",
        help="Path to the local vendor PDF to hash-verify.",
    )
    parser.add_argument(
        "--output",
        metavar="PATH",
        default=None,
        help=(
            "Where to write the approved contract JSON. "
            "Default: same directory as --candidate, name changed to *.approved.json."
        ),
    )
    args = parser.parse_args(argv)

    candidate_path = pathlib.Path(args.candidate)
    source_path = pathlib.Path(args.source)

    # ------------------------------------------------------------------ step 1
    # Verify paths exist.
    # ------------------------------------------------------------------
    if not candidate_path.exists():
        print(f"ERROR: candidate file not found: {candidate_path}", file=sys.stderr)
        return 2
    if not source_path.exists():
        print(f"ERROR: source PDF not found: {source_path}", file=sys.stderr)
        return 2

    print()
    print("DRIFT Contract Approval Gate")
    print(_hr("═"))
    print(f"  Candidate : {candidate_path}")
    print(f"  Source PDF: {source_path}")

    # ------------------------------------------------------------------ step 2
    # Hash the PDF and compare to the known value.
    # ------------------------------------------------------------------
    print()
    print("Hashing source PDF …", end=" ", flush=True)
    actual_hash = _hash_file(source_path)
    print("done.")
    print(f"  Computed SHA-256 : {actual_hash}")
    print(f"  Expected SHA-256 : {KNOWN_TMP117_SOURCE_SHA256}")

    if actual_hash != KNOWN_TMP117_SOURCE_SHA256:
        print()
        print("ERROR: PDF hash does not match the expected value.", file=sys.stderr)
        print(
            "  The file may have changed, or this is a different revision.\n"
            "  Update KNOWN_TMP117_SOURCE_SHA256 in src/drift/contract.py\n"
            "  only after re-reading the source pages.",
            file=sys.stderr,
        )
        return 3

    print("  ✓ Hash matches.")

    # ------------------------------------------------------------------ step 3
    # Load and validate the candidate contract.
    # ------------------------------------------------------------------
    print()
    print("Loading candidate contract …", end=" ", flush=True)
    try:
        candidate = load_candidate(candidate_path, source_sha256=actual_hash)
    except SourceHashMismatch as exc:
        print()
        print(f"ERROR (SourceHashMismatch): {exc}", file=sys.stderr)
        return 3
    except MissingCitationError as exc:
        print()
        print(f"ERROR (MissingCitationError): {exc}", file=sys.stderr)
        return 4
    except UnsupportedProfileError as exc:
        print()
        print(f"ERROR (UnsupportedProfileError): {exc}", file=sys.stderr)
        return 4
    except ContractError as exc:
        print()
        print(f"ERROR (ContractError): {exc}", file=sys.stderr)
        return 4
    except _PydanticValidationError as exc:
        print()
        print(f"ERROR (ValidationError): {exc}", file=sys.stderr)
        return 4
    print("done.")
    print(f"  Profile  : {candidate.profile_id}")
    print(f"  Status   : {candidate.status}")
    print(f"  Facts    : {len(candidate.facts)}")

    # ------------------------------------------------------------------ step 4
    # Refuse pending status — human must update the candidate first.
    # ------------------------------------------------------------------
    if candidate.status.startswith("pending"):
        print()
        print("ERROR: Contract status is still pending.", file=sys.stderr)
        print(
            f"  Status value: {candidate.status!r}\n"
            "  The reviewer must:\n"
            "    1. Open the source PDF and verify all facts against the printed pages.\n"
            "    2. Update the contract 'status' field to \"reviewed\".\n"
            "    3. Re-run this script.",
            file=sys.stderr,
        )
        return 5

    # ------------------------------------------------------------------ step 5
    # Display the full contract for review.
    # ------------------------------------------------------------------
    _display_contract(candidate)

    # ------------------------------------------------------------------ step 6
    # Compute and display the canonical contract hash.
    # ------------------------------------------------------------------
    contract_hash = candidate.canonical_sha256()
    _section("CANONICAL CONTRACT HASH")
    print(f"  SHA-256 : {contract_hash}")
    print()
    print("  This hash covers the entire contract content (excluding the approval")
    print("  block). It will be bound into the approved output. Any subsequent")
    print("  change to the contract JSON will invalidate the approval.")

    # ------------------------------------------------------------------ step 7
    # Interactive confirmation.
    # ------------------------------------------------------------------
    _section("REVIEWER CONFIRMATION REQUIRED")
    print(
        "  You are about to sign this contract approval.  By proceeding you\n"
        "  confirm that:\n"
        "    • You have read the source PDF and verified F01–F10 against the\n"
        "      cited pages.\n"
        "    • The derived register values are correct.\n"
        "    • The canonical contract hash above matches what you intend to bind.\n"
    )

    try:
        reviewer = input("  Enter your reviewer name (or press Enter to abort): ").strip()
    except (EOFError, KeyboardInterrupt):
        print()
        print("\nAborted — no approval written.")
        return 6

    if not reviewer:
        print("\nAborted — no reviewer name provided. No approval written.")
        return 6

    print()
    print(f"  Reviewer : {reviewer!r}")
    print()

    try:
        confirmation = input(
            "  Type YES (exactly) to approve, or anything else to abort: "
        ).strip()
    except (EOFError, KeyboardInterrupt):
        print()
        print("\nAborted — no approval written.")
        return 6

    if confirmation != "YES":
        print(f"\nAborted — received {confirmation!r}, not 'YES'. No approval written.")
        return 6

    # ------------------------------------------------------------------ step 8
    # Call approve_contract() and write the output file.
    # ------------------------------------------------------------------
    try:
        approved = approve_contract(
            candidate=candidate,
            reviewer=reviewer,
            profile_id=candidate.profile_id,
            source_sha256=actual_hash,
        )
    except PendingFactsError as exc:
        print(f"\nERROR (PendingFactsError): {exc}", file=sys.stderr)
        return 5
    except ContractError as exc:
        print(f"\nERROR (ContractError): {exc}", file=sys.stderr)
        return 4

    # Determine output path.
    if args.output:
        output_path = pathlib.Path(args.output)
    else:
        # Replace a trailing ".candidate" suffix in the stem; fall back to
        # appending ".approved" so the name is always predictable.
        # e.g. "tmp117.candidate" → "tmp117.approved"
        #      "tmp117"          → "tmp117.approved"
        base = candidate_path.stem  # e.g. "tmp117.candidate"
        if base.endswith(".candidate"):
            approved_stem = base[: -len(".candidate")] + ".approved"
        else:
            approved_stem = base + ".approved"
        output_path = candidate_path.parent / f"{approved_stem}.json"

    approved.save(output_path)

    # ------------------------------------------------------------------ step 9
    # Summary.
    # ------------------------------------------------------------------
    _section("APPROVAL WRITTEN")
    print(f"  Output file   : {output_path}")
    print(f"  Reviewer      : {approved.approval.reviewer}")
    print(f"  Profile       : {approved.approval.profile_id}")
    print(f"  Source SHA-256: {approved.approval.source_sha256}")
    print(f"  Contract hash : {approved.approval.contract_sha256}")
    print(f"  Approved UTC  : {approved.approval.approved_utc}")
    print()
    print("  Review the output file before committing.")
    print("  Do NOT commit local_sources/tmp117.pdf to Git.")
    print()

    return 0


if __name__ == "__main__":
    sys.exit(main())
