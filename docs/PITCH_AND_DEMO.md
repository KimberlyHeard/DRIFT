# DRIFT — explanations, pitch copy, and demonstration scripts

**Draft status:** These scripts describe the intended completed submission. Before recording or publishing, remove any capability you have not actually implemented and replace every bracketed placeholder with observed evidence. No result is claimed merely because it appears in this file.

## Name and positioning

Keep the team name **DRIFT**. Use the subtitle **Datasheet-to-Driver Virtual Verification Lab**. The subtitle explains the product without forcing an acronym.

Optional acronym expansions, if you want one later:

- **Datasheet Review, Implementation, and Fault Testing** — recommended; describes the workflow.
- **Device Requirements, Implementation, and Fault Testing** — emphasizes reviewed requirements.
- **Driver Reliability through Independent Fault Testing** — emphasizes verification, but leaves out source extraction.

Pick at most one. Changing the expansion should not change the scope or team name.

## 15-second explanation

“DRIFT helps embedded developers check sensor drivers before they have the hardware. IBM Bob helps turn a real datasheet into a reviewed specification, then we test the driver against a virtual device and fixed expectations, inject failures, and show Bob repairing a deliberate bug.”

## 60-second explanation

“A sensor datasheet explains what a device should do, but a developer still has to translate pages of registers, bit fields and timing rules into correct code. If the driver and its tests make the same mistake, a green test result can be misleading.

DRIFT connects the source evidence to an executable verification workflow. We start with a real TI TMP117 datasheet. Bob extracts candidate facts with page references; I review the selected profile. We implement the driver against a deterministic virtual I²C device and check it with independently prepared values and transaction sequences.

The workbench lets you run a normal measurement, inject four environmental faults, and inspect the exact bus trace. A separate deliberately broken driver produces the wrong temperature. In our recorded Bob task, we diagnose and repair that defect while keeping the expected answers fixed.

The reusable part is the review, generation, execution and evidence pipeline. [Only if completed: A real BME280 temperature profile demonstrates a second device using the same infrastructure.] This is software-level verification of declared profiles, with physical hardware validation still ahead.”

## Three levels of technical explanation

### Level 1 — No embedded background

“The datasheet is the device's instruction manual. The driver is the translator between your program and the sensor. Our virtual device follows a small, reviewed portion of that manual. We check the translator using answers that were prepared separately, and we keep a receipt for every message it sends.”

### Level 2 — Developer audience

“A human-reviewed contract specifies the supported registers, byte order, conversion behavior and timing policy. A Python driver only sees a bus and a clock. A deterministic simulator implements the selected behavior. Scripted-bus tests validate the driver's message sequence independently, and literal numerical fixtures validate decoding. The runner emits versioned reports and traces for the UI.”

### Level 3 — Reviewer asking about independence

“Driver/model agreement is insufficient. We separately test the model using literal register operations and the driver using scripted responses. Golden values are literal, human-reviewed arithmetic with source provenance; they are not generated from the driver's helper functions. A repair record binds the source, contract, oracle and code hashes. We verify that the oracle stays unchanged across the deliberate defect and Bob's repair. Shared schemas and bus interfaces are reusable; shared expected-answer computation would weaken the experiment.”

## One concrete walkthrough

1. Open TI page 26: the temperature word is signed, with one count equal to 1/128 °C. Show that the fact is approved for the exact source/contract version.
2. The selected fixture supplies raw bytes `0C 80`. Independently, `0x0C80 = 3200`, and `3200 / 128 = 25`.
3. The driver checks identity, starts one conversion, polls readiness and reads those bytes. The trace shows these real software bus operations.
4. Select the deliberate byte-swap variant. It interprets `0C 80` as `0x800C`, so its result is −255.90625 °C. The expected value stays 25 °C and the check fails.
5. Open the recorded Bob diagnosis and actual patch. Show the same expected-answer file/hash and the rerun passing after the repair.

The numbers above are arithmetically verified examples. The transaction trace, generated artifact, repair and UI must be produced by the actual application before recording this flow.

## Three-minute demo storyboard

| Time | On screen | Narration/action |
|---|---|---|
| 0:00–0:20 | Title and problem | “Embedded developers must translate datasheet rules into code before reliable hardware access. DRIFT makes those assumptions reviewable and testable.” |
| 0:20–0:45 | Evidence panel and TI page 26 | Show one source-linked fact, approved profile and source identity. Explain human review. |
| 0:45–1:10 | Run baseline, expected/actual, trace | Run TMP117. Explain `0C 80` → 25 °C and expand one transaction. |
| 1:10–1:35 | Four fault outcomes | Run/show NACK, never-ready, wrong ID and short read. Expected error handling counts as a successful scenario check. |
| 1:35–2:20 | Seeded defect + recorded Bob repair | Show numerical failure, source reasoning, actual diff and unchanged expectations, then passing rerun. |
| 2:20–2:45 | Generated artifact and reuse | Download actual generated source. If BME280 works, run it and identify reused components. Otherwise explain extension points without implying support. |
| 2:45–3:00 | Results and limits | Give actual test/defect counts, public links and the selected-profile/no-physical-validation boundary. |

## Full demo script: target 4:20, hard limit 5:00

Do a timed rehearsal. These windows leave room for transitions; trim rather than speaking too quickly.

### 0:00–0:25 — Introduction

“I'm Kimberly, building DRIFT for embedded developers who need to integrate a documented sensor before they can depend on physical hardware. The difficult part is turning register tables and timing rules into behavior you can trust. A plausible driver can still return the wrong number or mishandle a device that never becomes ready.”

### 0:25–0:55 — Source and scope

“Our first supported profile uses the real TI TMP117 datasheet: one requested measurement at a time, with averaging disabled, at the selected I²C address 0x48. Here is a page-linked fact Bob helped extract. I review the contract before generation. This hash binds the approved content; changing it invalidates approval.”

Show one actual pending/draft block and one approved profile. Do not spend the segment reading every register.

### 0:55–1:35 — Working path and generated output

“This produces an actual driver artifact for our supported profile. Now I run it against the virtual device. These bytes, `0C 80`, should produce 25 degrees. The expected answer was prepared independently. The trace shows identity, configuration, polling and the final read, with deterministic virtual time.”

Show Generate/Download only if it works. Open one source file/manifest briefly. Run the baseline, then expand a useful trace row. Do not describe virtual microseconds as real wall-clock speed.

### 1:35–2:05 — Four fault cases

“Now the device fails in controlled ways: no acknowledgment, never ready, wrong identity, and a short read. The driver must report the right error within a bound. A timeout here is the simulated device outcome; the green verification means the driver handled that expected failure correctly.”

Show real results, preferably one click for the verification suite and one expanded fault.

### 2:05–3:10 — Deliberate defect and Bob repair

“This is a deliberately seeded driver bug, separate from the environmental faults. The bus still returns `0C 80`, but the broken code swaps the byte order. Its result is −255.90625 instead of 25, so the fixed check fails.

Here is the recorded Bob task. Bob uses the trace and the reviewed datasheet fact to diagnose the problem and propose this patch. I review it, and we rerun the same checks. These hashes show that the expected-answer files stayed unchanged. The repair changes the driver and restores the correct result.”

Use a short labeled recording of the real session, not a recreated conversation. Include enough of the patch and test output to make the claim checkable. Preserve any failed attempt honestly in the underlying evidence.

### 3:10–3:40 — Reusability

If BME280 works:

“Our second device is the real Bosch BME280, scoped to forced temperature measurements. Its calibration and compensation differ from TMP117. We reuse the approval format, bus and clock interfaces, runner, report and workbench; the device-specific driver, model and independent values are new. Here is its actual compensated result.”

If it is unfinished:

“The reusable infrastructure is the approval process, bus and clock boundary, fault runner, report and workbench. A second device needs its own reviewed behavior and independent values. BME280 is the planned extension; this submission currently supports the displayed TMP117 profile.”

### 3:40–4:20 — Evidence, impact, limits

“Bob contributed to [actual tasks]. The repository includes the required task-summary screenshots, reproducible commands, reviewed source facts and repair evidence. We executed [actual checks], handled [actual fault count] selected faults, and caught [named seeded defects]. We haven't measured a manual-work baseline, so we aren't claiming a percentage productivity gain.

DRIFT demonstrates a repeatable path from a real datasheet to a checked driver and an auditable repair. These are software models of selected profiles; physical hardware validation remains future work. You can try the workbench and inspect the evidence at these links.”

## Submission copy

### Title

DRIFT — Datasheet-to-Driver Virtual Verification Lab

### Short description (under 255 characters)

DRIFT uses IBM Bob to turn real sensor datasheets into reviewed driver contracts, test Python drivers against deterministic virtual devices, inject faults, and document repairs against independent expectations.

### Long description (draft; keep only completed capabilities)

DRIFT addresses a recurring embedded-development task: translating a sensor datasheet into driver behavior that can be checked before dependable hardware access is available. Our initial profile uses the real Texas Instruments TMP117 in one-shot mode with averaging disabled and the selected I²C address 0x48.

IBM Bob helps extract source-linked facts, implement the driver and virtual device, develop verification code, and diagnose a deliberately seeded driver defect. A human reviews the contract before approved generation. Independent numerical values and scripted bus tests provide checks beyond agreement between the driver and simulator.

The online workbench exposes approved evidence, generated artifacts, deterministic transaction traces, normal measurements, and four controlled environmental faults. A separate repair demonstration preserves the failing result and shows Bob's patch against unchanged expectations. The repository records source provenance, limitations, reproducible commands and Bob task summaries.

The intended users are firmware developers, students and teams integrating documented devices while hardware access is constrained. The prototype verifies selected software-visible behavior; it does not claim electrical simulation, complete device coverage or physical validation. The shared approval, execution and reporting infrastructure provides a foundation for additional reviewed device profiles.

Optional sentence only if complete: “A Bosch BME280 forced temperature profile demonstrates reuse with device-specific calibration and compensation.”

## Six-slide outline for presentation help

1. **Problem and user:** translating datasheets while hardware access is limited. One concrete wrong-temperature example.
2. **Workflow:** source → human review → generated driver → independent verification → Bob repair. Distinguish authoring from execution.
3. **Architecture:** driver/bus/model, independent oracle and report. Use the playbook diagram.
4. **Proof:** real baseline, four fault outcomes, seeded defect, unchanged expectations and repair. Fill only with actual screenshots/counts.
5. **Reuse and boundaries:** shared components; BME280 only if complete; supported profiles and physical-validation limits.
6. **Bob contribution and access:** actual task roles, `bob_sessions/`, repository, interactive URL, next work.

Check event eligibility for any collaborator authoring submission assets. Presentation rehearsal and feedback can start immediately. Export final slides to PDF and verify they match the video.

## Recording checklist

- Use the final public app and a known reset state. Close unrelated/private windows.
- Show text large enough to read at normal video size; confirm microphone input and sound.
- Label prerecorded Bob footage and seeded defects. Do not simulate live inference activity.
- Keep a local unedited recording and final export. Verify the actual MP4 is at most five minutes.
- Keep a backup baseline/fault report for explaining an outage, but do not present a static backup as a live run.
- Run the walkthrough once without narration. A stranger should know which button to press and what the outcome means.
- Upload early enough to preview the processed video, slides and links before submission.
