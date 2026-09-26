# DRIFT current status

Updated: September 26, 2026, after the Task 06 approval/policy boundary.

## Locked scope

- Primary device: real TI TMP117, one-shot, no averaging, selected seven-bit I²C address `0x48`, with the fixture explicitly initialized in shutdown.
- Second device: real Bosch BME280 temperature-only forced profile, after the TMP117 end-to-end loop works.
- Bob IDE performs and documents central implementation and the recorded defect repair. Expected values remain independent of production code.

## Environment and budget

- Python 3.12.10; pytest 9.1.1; Pydantic 2.13.5.
- Git 2.46.0.windows.1; Node v24.19.0; npm 11.17.0.
- Virtual environment: `.venv\Scripts\python.exe`; editable package installed.
- Latest account usage reported by Kimberly: 16.54 / 40 Bobcoins; 23.46 remain. Use the account balance as authoritative because displayed task costs are rounded.
- Current per-task Bob cost limit: 3 Bobcoins.

## Implemented

1. **Task 01 — interfaces.** `src/drift/interfaces.py` defines `RegisterBus` and `Clock` protocols, frozen result/trace dataclasses, typed errors, and seven-bit address validation. `tests/test_interfaces.py` contains 31 checks.

2. **Task 02 — source contract and approval gate.** `src/drift/contract.py` implements Pydantic candidate/approval models, canonical contract hashing, source-hash binding, citation/profile validation, and stale-approval rejection. `tests/test_contract.py` contains 18 checks. `docs/TMP117_SOURCE_REVIEW.md` links F01–F10 to printed pages in TI SNOSD82D Rev. D and separates vendor facts, derived values, and DRIFT policies. `scripts/approve_contract.py` requires source verification and Kimberly's explicit approval; its test file contains 12 checks. One Bob session in this phase was labeled Task 03 in the IDE, but it completed the ordered source-approval phase.

3. **Human source approval.** Kimberly approved `contracts/tmp117.approved.json` at `2026-09-26T17:52:57Z`. The candidate is marked `reviewed`. Source PDF SHA-256: `637a143dda6317d22222e265de47ceac72ba6aed4461ad460efbe84e16b936df`. Canonical approved contract SHA-256: `5f15b14e522a0ad886f07dda88a32ae3771951141bbeb4f139c6395e1cf0423f`. The PDF remains outside Git in `local_sources/`.

4. **Task 03 — decoder and isolated defects.** `src/drift/decoders/tmp117.py` decodes strict two-byte, signed, MSB-first temperatures and checks the device ID's lower 12 bits while accepting varying revision nibbles. `tests/test_decoder_tmp117.py` contains 29 checks using independent literal values, invalid lengths, identity cases, and byte-swap/unsigned defect examples. `0x8000` is arithmetic `-256 °C`, not a valid completed measurement.

5. **Task 04 — driver and scripted transactions.** `src/drift/drivers/tmp117.py` implements identity, selected-profile configuration, and bounded one-shot measurement through bus and clock interfaces. `src/drift/bus.py` includes an ordered scripted bus; `src/drift/clock.py` includes a deterministic step clock. `tests/test_driver_tmp117.py` contains 39 checks, including polling, timeout, short read, varying revision, and consecutive measurements.

6. **Task 05 — deterministic virtual device.** `src/drift/devices/tmp117.py` implements the selected-profile virtual model. `src/drift/clock.py` provides a virtual clock, and `src/drift/bus.py` provides an addressed virtual-device bus. `tests/test_model_tmp117.py` contains 36 model checks. Trace events are frozen records exposed through tuple snapshots.

7. **Task 06 integration checkpoint — real driver against virtual device.** Bob first reproduced a genuine integration failure: a configuration poll returned ready word `2600`, but the subsequent temperature read incorrectly returned reset word `8000`. Bob corrected the model so its temperature register stores the last completed conversion independently of the `Data_Ready` flag. Model tests T15, T18, T19, and T36 were corrected. `tests/test_integration_tmp117.py` adds two independent driver-to-model checks: `0C80` produces `25.0 °C`, and `FF80` produces `-1.0 °C`. In the corrected positive trace, the ready poll at 16,000 virtual µs returns `2600` and the temperature read returns `0C80`. The approved source contract and independent temperature expectations did not change.

## Verification

| Check | Actual result |
| --- | --- |
| Task 01 interfaces targeted | 31 passed |
| Task 02 contract targeted | 18 passed |
| Task 03 decoder targeted | 29 passed |
| Task 04 driver targeted | 39 passed |
| Full suite after Task 04 | 129 passed |
| Full suite after Task 05 | 165 passed |
| Task 06 fault scenarios targeted | 32 passed |
| **Latest full suite after Task 06 approval/policy boundary** | **199 passed in 0.43s; exit 0** |

Bob also recorded the integration failure before its fix: the ready poll returned `2600`, followed by incorrect temperature bytes `8000`. The corrected trace returns `0C80` for the 25 °C fixture. This is an integration correction, separate from the planned seeded byte-swap demonstration and recorded Bob repair.

Task 06 approval/policy boundary: `src/drift/runner.py` now loads and integrity-verifies `contracts/tmp117.approved.json` once at import time via `ApprovedContract.from_file()`; a missing or stale approval is a hard error before any bus operations. Runtime policy (`timeout_us = 100 000 µs`) and provenance (contract hash, source hash, reviewer, approval UTC) are derived from the validated contract rather than duplicated as module constants. The `fault_never_ready` scenario-specific 20 000 µs timeout override is removed; it uses the approved 100 000 µs policy. `reporting.py` derives the provenance block and source document string from the same loaded contract; reports now carry `policy_timeout_us`. Four new tests (FA01–FA04) verify missing approval, stale approval, applied timeout, and provenance in reports.

An earlier Task 03 run had 89 passed and one stale test asserting that the subsequently approved candidate was still pending. Kimberly corrected that assertion and reran the suite: 90 passed. That issue is resolved.

For byte-swap demonstrations, swapped bytes `0C 80` become `0x800C`, or `-255.90625 °C`, not `-255.95 °C`.

## Not yet built or verified

- Remaining Task 06: bounded runner/CLI, provenance-bearing JSON reports to disk, and repeatability checks; the baseline and four fault scenarios with the byte-swap failing report are implemented and verified.
- Deterministic generated driver/configuration artifacts from the approved profile.
- Public judge workbench, deployment, and signed-out usability check.
- Recorded Bob diagnosis and repair of the seeded defect while independent expectations stay fixed.
- BME280 source review, bounded adapter, independent expected values, and integration.
- Presentation, real product demonstration video, and final submission.
- Public GitHub push has not been confirmed. Relevant genuine Bob IDE task consumption-summary PNGs must be placed in `bob_sessions/` before submission.

## Next action

Commit the Task 06 integration correction. In a new Bob IDE task, implement the remaining fault runner, reports, and CLI using the verified driver-to-model baseline. Inject short reads explicitly at a bus wrapper and trace the bytes actually delivered; the normal virtual device still returns two-byte registers.

## Handoff

- Latest verified Windows full suite: `.\.venv\Scripts\python.exe -m pytest -q` → 199 passed in 0.43s.
- Known current test failures: none in that run.
- Actual baseline integration works for positive and negative literal fixtures.
- Four fault scenarios, report pipeline, and seeded failing report are not yet implemented.
- Keep literal expected values independent of driver, model, and generator code.
- Stage only intended files; the root-level screenshot remains untracked until identified and moved into `bob_sessions/`.