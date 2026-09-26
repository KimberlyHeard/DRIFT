# DRIFT current status

Updated: September 26, 2026, after Task 05 virtual-device implementation and Kimberly's full-suite run.

## Locked scope

- Primary device: real TI TMP117, one-shot, no averaging, selected seven-bit I²C address `0x48`, with the fixture explicitly initialized in shutdown.
- Second device: real Bosch BME280 temperature-only forced profile, after the TMP117 end-to-end loop works.
- Bob IDE performs and documents central implementation and the recorded defect repair. Expected values remain independent of production code.

## Environment and budget

- Python 3.12.10; pytest 9.1.1; Pydantic 2.13.5.
- Git 2.46.0.windows.1; Node v24.19.0; npm 11.17.0.
- Virtual environment: `.venv\Scripts\python.exe`; editable package installed.
- Bob usage after Task 05: approximately 14.86 / 40 Bobcoins; approximately 25.14 remain. Task 05 cost 1.75. Recheck the account total in Bob IDE before relying on these figures.
- Current per-task Bob cost limit: 3 Bobcoins.

## Implemented

1. **Task 01 — interfaces.** `src/drift/interfaces.py` defines `RegisterBus` and `Clock` protocols, frozen result/trace dataclasses, typed errors, and seven-bit address validation. `tests/test_interfaces.py` contains 31 checks.

2. **Task 02 — source contract and approval gate.** `src/drift/contract.py` implements Pydantic candidate/approval models, canonical contract hashing, source-hash binding, citation/profile validation, and stale-approval rejection. `tests/test_contract.py` contains 18 checks. `docs/TMP117_SOURCE_REVIEW.md` links facts F01–F10 to printed pages of TI SNOSD82D Rev. D and separates vendor facts, derived values, and DRIFT policies. `scripts/approve_contract.py` requires source verification and Kimberly's explicit approval; its test file contains 12 checks. One Bob task in this phase was labeled Task 03 in the IDE, but it completed the ordered source-approval phase.

3. **Human source approval.** Kimberly approved `contracts/tmp117.approved.json` at `2026-09-26T17:52:57Z`. The candidate is marked `reviewed`. Source PDF SHA-256: `637a143dda6317d22222e265de47ceac72ba6aed4461ad460efbe84e16b936df`. Canonical approved contract SHA-256: `5f15b14e522a0ad886f07dda88a32ae3771951141bbeb4f139c6395e1cf0423f`. The PDF remains outside Git in `local_sources/`.

4. **Task 03 — decoder and isolated defects.** `src/drift/decoders/tmp117.py` decodes strict two-byte, signed, MSB-first temperatures and checks the device ID's lower 12 bits while accepting varying revision nibbles. `tests/test_decoder_tmp117.py` contains 29 checks using independent literal values, invalid lengths, identity cases, and byte-swap/unsigned defect examples. `0x8000` is arithmetic `-256 °C`, not a valid completed measurement.

5. **Task 04 — driver and scripted transactions.** `src/drift/drivers/tmp117.py` implements identity, selected-profile configuration, and bounded one-shot measurement through bus and clock interfaces. `src/drift/bus.py` includes an ordered scripted bus; `src/drift/clock.py` includes a deterministic step clock. `tests/test_driver_tmp117.py` contains 39 checks, including polling, timeout, short read, varying revision, and consecutive measurements.

6. **Task 05 — deterministic virtual device.** Bob added a TMP117 virtual model in `src/drift/devices/tmp117.py`, a virtual clock in `src/drift/clock.py`, and an addressed virtual-device bus in `src/drift/bus.py`. `tests/test_model_tmp117.py` adds 36 checks. The model was tested independently of the production driver. Kimberly reran the entire suite successfully. The actual example trace from Bob's task has not yet been independently inspected for the demo.

## Verification

| Check | Actual result |
| --- | --- |
| Task 01 targeted | 31 passed |
| Task 02 contract targeted | 18 passed |
| Task 03 decoder targeted | 29 passed |
| Task 04 driver targeted | 39 passed |
| Full suite after Task 04 | 129 passed |
| **Full suite after Task 05, run by Kimberly** | **165 passed in 0.42s; exit 0** |

An earlier Task 03 run had 89 passed and one stale test asserting that the subsequently approved candidate was still pending. Kimberly corrected that assertion and reran the suite: 90 passed. That issue is resolved.

For byte-swap demonstrations, swapped bytes `0C 80` become `0x800C`, or `-255.90625 °C`, not `-255.95 °C`.

## Not yet built or verified

- **Task 06:** integrate the driver and virtual device; run positive and negative baselines, four injected faults, and a seeded byte-swap defect; produce real trace-backed reports and a CLI.
- Deterministic generated driver/configuration artifacts from the approved profile.
- Public judge workbench, deployment, and signed-out usability check.
- Recorded Bob diagnosis and repair while independent expectations stay fixed.
- BME280 source review, bounded adapter, independent expected values, and integration.
- Presentation, real product demonstration video, and final submission.
- Public GitHub push has not been confirmed. Relevant Bob IDE task consumption-summary PNGs must be placed in `bob_sessions/` before submission.

## Next action

Commit Task 05's intended files and this status/work-log update. Begin Task 06 in a new Bob IDE task with the approved TMP117 profile. Verify a real driver-to-model baseline before expanding into fault reports.

## Handoff

- Latest verified Windows full suite: `.\.venv\Scripts\python.exe -m pytest -q` → 165 passed in 0.42s.
- Known current test failures: none in that run.
- Model and driver have each been tested independently; their combined run is not yet verified.
- Keep literal expected values independent of driver, model, and generator code.
- Stage only intended files. Check the untracked screenshot before assigning it to a Bob task or committing it.