# DRIFT current status

Updated: September 26, 2026, after Task 07 deterministic generation and Kimberly's full-suite run.

## Locked scope

- Primary device: real TI TMP117, one-shot conversion, no averaging, selected seven-bit I²C address `0x48`, with the fixture explicitly initialized in shutdown.
- Second device: real Bosch BME280 temperature-only forced profile, after the TMP117 end-to-end loop.
- Bob IDE performs and documents the central engineering work and the recorded defect repair. Expected values remain independent of production code.
- The generator currently supports one reviewed TMP117 profile. It does not claim to convert arbitrary datasheets automatically.

## Environment and budget

- Python 3.12.10; pytest 9.1.1; Pydantic 2.13.5.
- Git 2.46.0.windows.1; Node v24.19.0; npm 11.17.0.
- Virtual environment: `.venv\Scripts\python.exe`; editable package installed.
- Latest account usage reported by Kimberly: **24.21 / 40 Bobcoins**; **15.79 remain**. Preserve approximately 5 Bobcoins for unexpected fixes. The account balance is authoritative.
- Current per-task Bob cost limit: 3 Bobcoins.

## Implemented

1. **Task 01 — interfaces.** `src/drift/interfaces.py` defines `RegisterBus` and `Clock` protocols, frozen result and trace dataclasses, typed errors, and seven-bit address validation. `tests/test_interfaces.py` contains 31 checks.

2. **Task 02 — source contract and approval gate.** `src/drift/contract.py` implements Pydantic candidate and approval models, canonical contract hashing, source-hash binding, citation and profile validation, and stale-approval rejection. `tests/test_contract.py` contains 18 checks. `docs/TMP117_SOURCE_REVIEW.md` links F01–F10 to printed pages in TI SNOSD82D Rev. D and separates vendor facts, derived values, and DRIFT policies. `scripts/approve_contract.py` requires source verification and Kimberly's explicit approval; its test file contains 12 checks. One Bob session in this phase was labeled Task 03 in the IDE, but it completed the ordered source-approval phase.

3. **Human source approval.** Kimberly approved `contracts/tmp117.approved.json` at `2026-09-26T17:52:57Z`. The candidate is marked `reviewed`. Source PDF SHA-256: `637a143dda6317d22222e265de47ceac72ba6aed4461ad460efbe84e16b936df`. Canonical approved contract SHA-256: `5f15b14e522a0ad886f07dda88a32ae3771951141bbeb4f139c6395e1cf0423f`. The PDF remains outside Git in `local_sources/`.

4. **Task 03 — decoder and isolated defects.** `src/drift/decoders/tmp117.py` decodes strict two-byte, signed, MSB-first temperatures and checks the device ID's lower 12 bits while accepting varying revision nibbles. `tests/test_decoder_tmp117.py` contains 29 checks using independent literal values, invalid lengths, identity cases, and detectable byte-swap and unsigned defects. `0x8000` is tested as arithmetic `-256 °C`, not as a valid completed measurement.

5. **Task 04 — driver and scripted transactions.** `src/drift/drivers/tmp117.py` implements identity, selected-profile configuration, and bounded one-shot measurement through bus and clock interfaces. `src/drift/bus.py` includes an ordered scripted bus; `src/drift/clock.py` includes a deterministic step clock. `tests/test_driver_tmp117.py` contains 39 checks, including polling, timeout, short read, varying revision, and consecutive measurements.

6. **Task 05 — deterministic virtual device.** `src/drift/devices/tmp117.py` implements the selected-profile virtual model. `src/drift/clock.py` provides a virtual clock, and `src/drift/bus.py` provides an addressed virtual-device bus. `tests/test_model_tmp117.py` contains 36 model checks. Trace events are frozen records exposed through tuple snapshots.

7. **Task 06 — integration, faults, runner, and reports.** Bob first reproduced a driver-to-model integration failure: a configuration poll returned ready word `2600`, but the next temperature read incorrectly returned reset word `8000`. Bob corrected the virtual model to retain the last completed conversion independently of `Data_Ready`. Integration checks confirm `0C80` produces `25.0 °C` and `FF80` produces `-1.0 °C`; the corrected positive trace reads `2600` and then `0C80` at 16,000 virtual µs. The approved contract and independent expectations did not change.

   The runner now executes fresh baseline and fault scenarios, records ordered transactions and delivered bytes or errors, separates execution outcome from assertion results, and emits JSON reports. Four injected faults cover identity-read NACK, conversion never ready, wrong device-ID bits, and a one-byte temperature response. A separately labeled byte-swap driver produces an intentionally failing temperature assertion against the fixed 25 °C expectation. The CLI exposes bounded `run` and `verify` commands.

   The approval/policy correction makes the runner load and integrity-check the approved contract before scenario execution. Reports derive source and contract hashes, reviewer, approval time, and the **100,000 µs** timeout policy from that contract. The never-ready scenario no longer silently substitutes a 20,000 µs timeout. The seven-case verification reports **six expected passes and one intentional byte-swap failure**. That failure is evidence that the independent expectation detects the seeded defect; it is not a passing verification case.

8. **Task 07 — deterministic generator.** `src/drift/generator.py` generates three artifacts under `generated/<contract-hash>/` from the validated approved contract and the device-specific template `src/drift/templates/tmp117_device.json`. It emits an executable `driver.py`, `device_model.py`, and `manifest.json` with provenance and output hashes. It rejects missing approval, stale contract content, and unsupported profiles before writing. Repeated generation of the same inputs produces byte-identical driver and model files. `src/drift/cli.py` exposes `python -m drift.cli generate --contract ... --output ...`. `tests/test_generator_tmp117.py` contains 24 checks, including approval rejection, determinism, importability, scripted transactions, and generated driver-to-model measurements against literal 25 °C and −1 °C expectations.

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
| Full suite after Task 06 approval/policy correction | 199 passed in 0.42s; exit 0 |
| Task 07 generator targeted, reported by Bob | 24 passed in 0.50s; exit 0 |
| **Latest full suite, run by Kimberly after Task 07** | **223 passed in 0.74s; exit 0** |

An earlier Task 03 run had 89 passes and one stale test that expected the subsequently approved candidate to remain pending. Kimberly corrected that assertion and reran the suite: 90 passed. The issue is resolved.

For the byte-swap demonstration, reversing `0C 80` produces `0x800C`, or `-255.90625 °C`, instead of the independent expectation of `25.0 °C`.

## Generated artifacts

- Directory: `generated/5f15b14e522a0ad886f07dda88a32ae3771951141bbeb4f139c6395e1cf0423f/`
- `driver.py` SHA-256 reported by Bob: `02eca1cbdd96dd1d2b1cd1ed472c0ae15b035d5857c0debee1ac78bc79dc47b8`
- `device_model.py` SHA-256 reported by Bob: `6069f87e6f34688fa36226e650e9da9755c06570b424cbf0d44d10af5d5bd762`
- Template: `src/drift/templates/tmp117_device.json`
- Reproduction command: `.\.venv\Scripts\python.exe -m drift.cli generate --contract contracts/tmp117.approved.json --output generated/`

## Not yet built or verified

- Recorded Bob diagnosis and repair of a separate seeded defect, with unchanged independent expectations and before/after evidence.
- BME280 source review, human approval, bounded driver, independent expected values, virtual model, and integration.
- Public judge workbench, deployment, and signed-out usability check.
- Presentation, product demonstration video, and final submission.
- Public GitHub push is not yet confirmed. Relevant genuine Bob IDE consumption-summary screenshots still need to be placed in `bob_sessions/`.

## Next action

Commit the Task 07 generator and its generated artifacts. Then record the existing byte-swap failure and give Bob a bounded task to diagnose and repair a **separate candidate**, preserving the original failing example and literal expectations. Develop the judge workbench alongside the remaining Bob engineering tasks. Pursue BME280 after the repair evidence is secured and its real source facts can be reviewed.

## Handoff

- Latest verified Windows full suite: `.\.venv\Scripts\python.exe -m pytest -q` → **223 passed in 0.74s**.
- Known current test failures: none in the full suite. The byte-swap scenario is an intentional **report-level failure**.
- Seven-case CLI verification: six expected passes, one intentionally failing seeded driver.
- Keep expected temperatures independent of the driver, virtual model, and generator.
- Stage only intended files; identify and move the root-level screenshot into `bob_sessions/`. Keep useful JSON reports in `artifacts/` available for the judge workbench.