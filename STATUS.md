# DRIFT current status

Updated: Task 01 completed — Bob Agent.

## Environment

- Python: 3.12.10 (via `py` / `.venv\Scripts\python.exe`)
- pytest: 9.1.1
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

## Not yet implemented or verified

- Bob source extraction/review, human approval, contract gate, application driver/model/runner/generator/API/UI.
- Actual project pytest suite beyond Task 01 interfaces, fault runs, generated artifacts, Bob repair recording, public deployment/submission.
- BME280 device adapter and its reviewed contract/oracle.

## Test results — Task 01

Command: `.\.venv\Scripts\python.exe -m pytest tests/test_interfaces.py -v`
Exit code: 0
Result: **31 passed in 0.11s** (Python 3.12.10, pytest 9.1.1, win32)

Checked:
- `validate_7bit_address(0x48)` → 72 (accepted)
- `validate_7bit_address(0x00)` → AddressError (general call)
- `validate_7bit_address(0x78)` → AddressError (reserved)
- `validate_7bit_address(72.0)` → AddressError (non-integer)
- All reserved range 0x78–0x7F rejected
- All frozen dataclasses raise on mutation attempt
- Protocol structural members confirmed

## Source approval still needed

All TMP117 candidate facts F01–F10 remain pending. No contract approval gate exists yet. Task 02 implements it.

## Next action

Execute Task 02: verify TMP117 source PDF (local_sources/tmp117.pdf), compute SHA-256, compare F01–F10 against printed pages, implement Pydantic contract validation and approval gate.

Exact next command:
```
.\.venv\Scripts\python.exe scripts/fetch_sources.py --device tmp117
```
Then open `local_sources/tmp117.pdf` and run Task 02 in Bob.

## Task handoff

Current task/time: Task 01 — Establish workspace and interfaces  
Files changed: src/drift/interfaces.py, src/drift/bus.py, src/drift/clock.py, src/drift/drivers/__init__.py, src/drift/drivers/tmp117.py, src/drift/devices/__init__.py, src/drift/devices/tmp117.py, src/drift/scenarios.py, src/drift/runner.py, src/drift/reporting.py, src/drift/__init__.py, tests/__init__.py, tests/test_interfaces.py  
Commands / exit codes / results: `pytest tests/test_interfaces.py -v` → exit 0, 31 passed  
Source approval still needed: TMP117 F01–F10 (all pending, no approval gate yet)  
Known failures: none  
Bobcoins remaining: (check Settings)  
Bob summary screenshot: drift_task01_environment_summary.png  
Next exact command/action: `.\.venv\Scripts\python.exe scripts/fetch_sources.py --device tmp117` then Task 02
