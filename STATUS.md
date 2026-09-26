# DRIFT current status

Updated: Task 02 completed — Bob Agent.

## Environment

- Python: 3.12.10 (via `py` / `.venv\Scripts\python.exe`)
- pytest: 9.1.1
- pydantic: 2.13.5 (added Task 02)
- Git: 2.46.0.windows.1
- Node: v24.19.0 / npm 11.17.0
- Venv: `.venv\Scripts\python.exe` installed and editable package confirmed

## Exists

- Current playbook, Bob task cards, candidate TMP117 contract, independent arithmetic fixture table.
- Environment checker, vendor-source download/hash utility, educational decoder demonstration.
- Python package scaffold and provenance/work-log templates.
- **[Task 01]** Core package module boundaries created:
  - `src/drift/interfaces.py` — RegisterBus, Clock Protocols; DeviceIdentity, Measurement, TraceEvent, AssertionRecord, RunReport frozen dataclasses; AddressError, BusNackError, DeviceIdentityError, ProtocolReadError, ConversionTimeout, UnsupportedProfile, ExecutionLimitExceeded; `validate_7bit_address()`.
  - `src/drift/bus.py`, `clock.py`, `scenarios.py`, `runner.py`, `reporting.py` — module stubs with docstrings.
  - `src/drift/drivers/__init__.py`, `src/drift/drivers/tmp117.py` — driver stubs with register constants and DRIFT policy values.
  - `src/drift/devices/__init__.py`, `src/drift/devices/tmp117.py` — virtual device stubs.
  - `tests/__init__.py`, `tests/test_interfaces.py` — 31 passing tests.
- **[Task 02]** Pydantic contract validation and human-approval gate:
  - `src/drift/contract.py` — full Pydantic v2 models (SourceRef, FactEntry, SelectedProfile, PoliciesBlock, DerivedCandidates, CandidateContract, ApprovalRecord, ApprovedContract) plus `load_candidate()` and `approve_contract()` API.
  - Error classes: ContractError, SourceHashMismatch, PendingFactsError, MissingCitationError, UnsupportedProfileError, StaleApprovalError, ApprovalMissingError.
  - `tests/test_contract.py` — 18 focused tests (T01–T18) covering every gate boundary.

## Not yet implemented or verified

- Bob source extraction/review, human approval of TMP117 F01–F10, application driver/model/runner/generator/API/UI.
- Actual project pytest suite beyond Task 01–02, fault runs, generated artifacts, Bob repair recording, public deployment/submission.
- BME280 device adapter and its reviewed contract/oracle.

## Test results — Task 01

Command: `.\.venv\Scripts\python.exe -m pytest tests/test_interfaces.py -v`
Exit code: 0
Result: **31 passed in 0.11s** (Python 3.12.10, pytest 9.1.1, win32)

## Test results — Task 02

Command: `.\.venv\Scripts\python.exe -m pytest tests/test_contract.py -v`
Exit code: 0
Result: **18 passed in 0.76s** (Python 3.12.10, pytest 9.1.1, pydantic 2.13.5, win32)

Full suite: `.\.venv\Scripts\python.exe -m pytest -v`
Exit code: 0
Result: **49 passed in 0.31s**

Checked (Task 02):
- T01 load_candidate() real file, no hash → CandidateContract returned
- T02 matching stored sha256 → accepted
- T03 mismatched hash → SourceHashMismatch
- T04 fact with no page/section → MissingCitationError
- T05 unknown profile_id → UnsupportedProfileError
- T06 pending status → PendingFactsError on approve_contract()
- T07 unknown profile in approve call → UnsupportedProfileError
- T08 profile_id mismatch → ContractError
- T09 malformed source_sha256 → SourceHashMismatch
- T10 valid reviewed candidate → ApprovedContract with all bound fields
- T11 verify_integrity on fresh approval → no raise
- T12 tampered contract_sha256 → StaleApprovalError
- T13 from_file with no approval block → ApprovalMissingError
- T14 from_file with wrong contract_sha256 → StaleApprovalError
- T15 canonical_sha256 deterministic across two calls
- T16 empty facts list → ContractError
- T17 non-hex SourceRef sha256 → rejected
- T18 save()/from_file() round-trip → integrity passes

## Source approval still needed

All TMP117 candidate facts F01–F10 remain **PENDING**.  
`contracts/tmp117.candidate.json` status: `"pending_human_review"` — unchanged.  
The approval gate exists and works; no approval has been issued.  
Human reviewer must verify F01–F10 against printed TI SNOSD82D Rev. D pages before calling `approve_contract()`.

## Next action

Execute Task 03: implement TMP117 virtual model (virtual device) and the bus
adapter so simulated bus transactions can be exercised against the driver stub.

## Task handoff

Current task/time: Task 02 — Pydantic contract validation and human-approval gate  
Files changed: src/drift/contract.py, tests/test_contract.py, pyproject.toml  
Commands / exit codes / results:  
  `.\.venv\Scripts\python.exe -m pytest tests/test_contract.py -v` → exit 0, 18 passed  
  `.\.venv\Scripts\python.exe -m pytest -v` → exit 0, 49 passed  
Source approval still needed: TMP117 F01–F10 (all pending; gate implemented but not invoked)  
Known failures: none  
Next exact command/action: Task 03 — virtual TMP117 device model and bus adapter
