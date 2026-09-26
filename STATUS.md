# DRIFT current status

Updated: September 26, 2026, after Task 03 decoder work and local test correction.

## Locked scope

- Primary device: real TI TMP117, one-shot, no averaging, selected seven-bit I²C address `0x48`, fixture initialized explicitly in shutdown.
- Second device: real Bosch BME280 temperature-only forced profile, after the TMP117 end-to-end loop works.
- Bob IDE performs and documents the central implementation and the recorded defect repair. Expectations remain independent of production code.

## Environment

- Python 3.12.10; pytest 9.1.1; Pydantic 2.13.5.
- Git 2.46.0.windows.1; Node v24.19.0; npm 11.17.0.
- Virtual environment: `.venv\Scripts\python.exe`; editable package installed.
- Last reported Bob usage: 11.18 / 40 Bobcoins; next task cost cap: 3 Bobcoins. Recheck current usage in Bob IDE before starting.

## Implemented

1. **Task 01 — interfaces.** `src/drift/interfaces.py` defines `RegisterBus` and `Clock` protocols, frozen result/trace dataclasses, typed errors, and seven-bit address validation. Bus, clock, driver, virtual device, scenario, runner, and reporting module stubs exist. `tests/test_interfaces.py` contains 31 checks.
2. **Task 02 — source contract and gate.** `src/drift/contract.py` implements Pydantic candidate/approval models, canonical contract hashing, source-hash binding, profile/citation validation, and stale-approval rejection. `tests/test_contract.py` has 18 checks. `docs/TMP117_SOURCE_REVIEW.md` links F01–F10 to printed pages in TI SNOSD82D Rev. D and distinguishes source facts from derived values and DRIFT policies. `scripts/approve_contract.py` checks the PDF and requires Kimberly's name and explicit `YES`; `tests/test_approve_contract_script.py` has 12 checks, including default output naming. The Bob session that added the review page was called Task 03, but this work completes the source-approval phase of the ordered task cards.
3. **Human source approval.** `contracts/tmp117.candidate.json` is marked `reviewed`; `contracts/tmp117.approved.json` was approved by Kimberly Heard at `2026-09-26T17:52:57Z`. Source PDF SHA-256: `637a143dda6317d22222e265de47ceac72ba6aed4461ad460efbe84e16b936df`. Canonical approved contract SHA-256: `5f15b14e522a0ad886f07dda88a32ae3771951141bbeb4f139c6395e1cf0423f`. The vendor PDF stays in `local_sources/` outside Git.
4. **Task 03 — decoder and isolated mutants.** `src/drift/decoders/tmp117.py` implements strict two-byte, signed, MSB-first `decode_temperature()` and revision-tolerant `decode_device_id()` checking part ID `0x117`. `tests/test_decoder_tmp117.py` has 29 checks using literal oracle values, length/identity cases, and detectable byte-swap and unsigned defects. `0x8000` is tested as arithmetic (`-256 °C`), not claimed to be a valid completed reading.

## Verified tests

| Run | Result |
| --- | --- |
| Task 01 interfaces | 31 passed in 0.11s |
| Task 02 contract gate | 18 passed in 0.76s |
| Task 02 approval CLI before final naming test | 11 passed in 0.37s; a twelfth CLI check was subsequently added and is included in the full suite |
| Task 03 decoder targeted | 29 passed in 0.08s |
| **Latest full suite: `.\.venv\Scripts\python.exe -m pytest -q`** | **90 passed in 0.39s**, exit 0, on Kimberly's Windows workspace |

The first Task 03 full run had 89 passed / 1 failed because `tests/test_contract.py::test_T01_load_candidate_real_file_no_hash` still expected `pending_human_review` after the human-approved candidate had become `reviewed`. Kimberly updated that stale test assertion and reran the full suite: **90 passed**. This earlier failure is resolved; preserve both actual run results in the work log rather than presenting the first run as a pass.

Byte-swap arithmetic for `0C 80` must be reported accurately: swapped `0x800C` equals `-255.90625 °C`, not `-255.95 °C`. Literal temperature expectations must not be computed with production decoder helpers.

## Not yet built or verified

- TMP117 driver and independent scripted bus; virtual device/clock/trace; baseline and four injected faults; runner/CLI and real reports.
- Generated source/configuration artifacts; recorded Bob diagnosis and repair; public workbench and signed-out check; final presentation, demo, and submission.
- BME280 reviewed contract, adapter, compensation/model/oracle, and independent integration checks.
- Public GitHub push is not yet confirmed: HTTPS remote exists, but authentication previously failed. Save all relevant genuine Bob IDE task consumption-summary PNGs in `bob_sessions/` before submission.

## Next action — ordered Task 04

Commit Task 03 decoder/tests and the corrected T01 assertion if they are uncommitted. In a **new Bob IDE task**, implement only the TMP117 driver using `RegisterBus` and `Clock`, with an independent scripted bus and focused tests. The driver must preserve the Data_Ready bit observed on a configuration read, then read temperature without an extra status read. No simulator or runner in Task 04. Run targeted tests and one quiet full-suite check; record actual results and any outstanding failure. Do not reopen the vendor PDF.

## Handoff

- Current baseline: approved real TMP117 contract; latest Windows full-suite result 90 passed in 0.39s.
- Known current test failures: none in the latest full-suite run.
- Next task: Task 04 driver + scripted bus, three-Bobcoin cap as currently configured.
- Manual checks: inspect `git status --short`, stage only intended files, save Bob session summaries, resolve GitHub push authentication before final submission.
