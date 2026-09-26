# DRIFT repository instructions

Project: DRIFT — Datasheet-to-Driver Virtual Verification Lab. The current execution plan is DRIFT_PLAYBOOK.md; task cards are prompts/BOB_TASKS.md. Read STATUS.md at task start and update it at task end.

## Locked scope

- Real TI TMP117: one-shot, averaging disabled, selected seven-bit address 0x48; initialized shutdown fixture.
- BME280 temperature-only forced profile is the second real device after the full TMP117 loop works.
- Python core, independent verification, deterministic trace/report, actual generated artifacts, Bob repair evidence, online workbench.
- Preserve the name and source provenance. Fictional-device examples from older unrelated files are not this project.

## Correctness boundaries

- Vendor facts carry document/revision/page references. Policies and derived arithmetic are labeled separately.
- Only the human reviewer approves the source contract. Approval binds a canonical hash and source hash.
- Driver uses bus/clock interfaces and cannot inspect simulator internals or expected answers.
- Independent expected values stay literal and reviewed. They cannot be calculated from production or generated decoding helpers.
- Virtual model tests run independently of the production driver; scripted bus tests check the driver independently of the model.
- Fault injection changes the environment; a seeded defect changes code. Label each accurately.
- Trace/report inspection cannot read device registers or mutate device state.
- State and time reset per scenario. All loops have appropriate bounds; deliberate infinite-loop mutants require isolation.
- UI metrics and outcomes come from real reports. A recorded run or repair is labeled recorded.
- Generated source is actually tested; unsupported profiles fail explicitly.
- Public execution accepts only reviewed named variants/fixtures; arbitrary uploaded code is outside scope.

## Working method

Implement one bounded task, run relevant checks, report exact results, and preserve a recoverable baseline. Use honest task/commit provenance. Keep Bob screenshots genuine; never synthesize them. Keep vendor PDFs and secrets out of Git. A screenshot/report is not approval or proof of correctness by itself.

The educational decoder and environment utilities shipped in this kit were prepared by ChatGPT during the event. The main application still needs Bob implementation. Disclose external contributions in PROVENANCE.md. Old planning was prepared September 20, 2026.
