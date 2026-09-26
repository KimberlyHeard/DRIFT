# DRIFT current status

Updated: Task 03 (source review + approval CLI) completed — Bob Agent.

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
- **[Task 03]** Source review document and human-approval CLI:
  - `docs/TMP117_SOURCE_REVIEW.md` — judge reference linking F01–F10 to printed SNOSD82D Rev. D pages; distinguishes TI facts, derived values, and DRIFT policies; cites official TI URL and PDF SHA-256.
  - `scripts/approve_contract.py` — interactive CLI gate: hashes PDF, validates candidate, displays full contract for review, requires explicit reviewer name and `YES` confirmation, writes `contracts/tmp117.approved.json` bound with source hash, contract hash, reviewer, and UTC timestamp; refuses missing citations, changed hashes, pending facts, and unsupported profiles.
  - `tests/test_approve_contract_script.py` — 11 focused tests (TA01–TA11) covering every exit path.
  - `contracts/tmp117.candidate.json` — restored F08 `"pages"` key (was incorrectly changed externally to `"page": [15]`).

## Not yet implemented or verified

- Bob source extraction/review, human approval of TMP117 F01–F10, application driver/model/runner/generator/API/UI.
- Actual project pytest suite beyond Task 01–03, fault runs, generated artifacts, Bob repair recording, public deployment/submission.
- BME280 device adapter and its reviewed contract/oracle.

## Test results — Task 01

Command: `.\.venv\Scripts\python.exe -m pytest tests/test_interfaces.py -v`
Exit code: 0
Result: **31 passed in 0.11s** (Python 3.12.10, pytest 9.1.1, win32)

## Test results — Task 02

Command: `.\.venv\Scripts\python.exe -m pytest tests/test_contract.py -v`
Exit code: 0
Result: **18 passed in 0.76s** (Python 3.12.10, pytest 9.1.1, pydantic 2.13.5, win32)

## Test results — Task 03

Command: `.\.venv\Scripts\python.exe -m pytest tests/test_approve_contract_script.py -v`
Exit code: 0
Result: **11 passed in 0.37s** (Python 3.12.10, pytest 9.1.1, pydantic 2.13.5, win32)

Full suite: `.\.venv\Scripts\python.exe -m pytest -v`
Exit code: 0
Result: **60 passed in 0.54s**

Checked (Task 03 — TA01–TA11):
- TA01 PDF hash mismatch → exit 3, no output file
- TA02 candidate file missing → exit 2
- TA03 source PDF missing → exit 2
- TA04 contract status "pending_*" → exit 5, no output file
- TA05 empty reviewer name → exit 6, no output file
- TA06 confirmation not "YES" → exit 6, no output file
- TA07 full approval flow (reviewed + YES) → exit 0, approved JSON with correct fields
- TA08 --output flag controls destination path
- TA09 written approved.json passes ApprovedContract.from_file() integrity check
- TA10 structurally invalid candidate JSON → exit 4
- TA11 candidate stored sha256 differs from PDF hash → exit 3

## Source approval still needed

All TMP117 candidate facts F01–F10 remain **PENDING**.  
`contracts/tmp117.candidate.json` status: `"pending_human_review"` — unchanged.  
The approval gate exists and works; no approval has been issued.  
Human reviewer must verify F01–F10 against printed TI SNOSD82D Rev. D pages,
update status to `"reviewed"`, and run:

```
.\.venv\Scripts\python.exe scripts\approve_contract.py \
    --candidate contracts\tmp117.candidate.json \
    --source local_sources\tmp117.pdf
```

## Next action

Execute Task 04: implement TMP117 virtual model (virtual device) and the bus
adapter so simulated bus transactions can be exercised against the driver stub.

## Task handoff

Current task/time: Task 03 — source review document and approval CLI  
Files changed:
  - `docs/TMP117_SOURCE_REVIEW.md` (new)
  - `scripts/approve_contract.py` (new)
  - `tests/test_approve_contract_script.py` (new)
  - `contracts/tmp117.candidate.json` (restored F08 pages key)
Commands / exit codes / results:
  `.\.venv\Scripts\python.exe -m pytest tests/test_approve_contract_script.py -v` → exit 0, 11 passed
  `.\.venv\Scripts\python.exe -m pytest -v` → exit 0, 60 passed
Source approval still needed: TMP117 F01–F10 (all pending; gate implemented but not invoked)
Known failures: none
Next exact command/action: Task 04 — virtual TMP117 device model and bus adapter
