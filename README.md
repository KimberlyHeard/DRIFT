# DRIFT

**Datasheet Review, Implementation, and Fault Testing** · A reproducible, software-level sensor-driver verification prototype created with IBM Bob.

> **Update note:** The overview sections at the top of this README (The problem through Roadmap) were added on October 2, 2026, after the hackathon submission deadline. Project is being re-deployed for LinkedIn. Changes are text only. No code, contracts, tests, reports, or demo content changed. Approval was requested through a support ticket and on LabLab Discord before this edit. Everything from "The workflow" onward is the README as submitted.

**Demo:** https://drift-verification-lab.vercel.app/

---

## The problem

AI can write code, but it cannot prompt a circuit board into existence.

Every chip ships with a datasheet that explains how to talk to it: register addresses, bit fields, byte order, conversion timing, and calibration. Firmware engineers translate that document into a driver, the code that lets a processor read the chip correctly. That driver is usually written before the physical board exists.

AI assistants can now produce that driver almost instantly. Checking that it actually matches the hardware is the hard part. A driver can compile, pass a code review, and still read two bytes in the wrong order or apply calibration incorrectly. Many of these mistakes return a plausible number, so they stay invisible until the code runs on a real device.

That moment can be weeks or months away while boards are designed, fabricated, assembled, and shipped. When the mistake finally appears during board bring-up, engineers have to work out whether the software or the hardware is at fault while the rest of integration waits. Caught late, it costs time and money in debugging, redesigns, and new board runs. Never caught, it can ship inside a product and become a recall or a safety failure in the field.

## Why now

- **Code generation got fast. Verification did not.** AI has shifted the slow part of firmware work from writing driver code to proving that code is correct.
- **Hardware is harder to get.** The global semiconductor market is projected to exceed $1.5 trillion in 2026, driven largely by AI infrastructure demand. Memory makers and fabs are prioritizing AI customers, and everyday devices compete for tighter supply. Longer waits for parts and boards mean longer stretches where firmware cannot be tested on real hardware.
- **Chips are in everything.** Phones, cars, medical monitors, industrial controllers, and grid equipment all depend on software reading sensors correctly. The verification gap is not specific to one industry.

## What DRIFT does

DRIFT gives a firmware team something real to test against before the board arrives, and keeps the AI that wrote the code out of the decision about whether that code is correct.

1. **Facts from the source.** IBM Bob reads the manufacturer's datasheet and drafts a contract of facts about the chip, each tied to the page and section it came from.
2. **Human approval, locked by hash.** An engineer reviews and approves those facts. The approval is bound to the exact datasheet revision with a SHA-256 hash, so the facts cannot silently change underneath the code.
3. **Driver and virtual twin.** From the approved contract, Bob builds the driver and a deterministic virtual version of the chip that models its registers and conversion timing on an integer microsecond clock.
4. **Independent verdict.** Plain Python runs the driver against the virtual chip, records every bus transaction, and compares results with literal expected answers prepared separately from the driver. Bob does not decide whether anything passed.
5. **Evidence, not confidence.** Every recorded bus step that depends on a datasheet fact links back to that fact and its page, so a failure points to its exact cause.

## Who it is for

- **Firmware engineers** bringing up a new sensor before boards arrive.
- **Hardware startups** without a dedicated validation team or a lab full of evaluation boards.
- **Teams adopting AI coding assistants** who need an audit trail showing why a generated driver can be trusted.
- **Reviewers and quality teams** in regulated or safety-sensitive products who must document how firmware was verified.
- **Chip vendors** who want developers to be productive with a new part on day one.

## How DRIFT differs from existing approaches

| Approach | What it gives you | What it misses |
|---|---|---|
| Testing on physical boards | Ground truth | Requires hardware that may not exist yet; failures are slow to reproduce and hard to attribute |
| Hand-written mocks and unit tests | Fast feedback | The mock usually encodes the same assumptions as the driver, so both can be wrong together |
| General-purpose emulators and simulators | Broad board and peripheral coverage | Peripheral models are typically hand-written and not tied, behavior by behavior, to a reviewed datasheet citation |
| Asking an AI whether its code is correct | Instant | The author grades its own work |
| **DRIFT** | A virtual chip built from human-approved, page-cited facts, with independent expected answers and a fact-linked bus trace | Currently covers two bounded sensor profiles and has not been compared against real hardware |

## What the prototype demonstrates

- **Two real sensors.** TI TMP117, a comparatively simple temperature sensor, showed the method works. Bosch BME280 extended it to a sensor whose readings depend on factory calibration data and multi-step integer compensation formulas.
- **Fault handling.** Injected faults cover a chip that does not acknowledge, a measurement that never completes, a different chip answering at the address, and short reads.
- **Checks that can fail.** A seeded byte-swap driver is kept in the suite as a negative control. It fails, as designed, and a separately repaired copy passes against the same fixed expectations.
- **A real catch.** During development, the independent checks caught an error in Bob's own virtual TMP117 model that had not been planted as a test. The fix went into the model, not the tests.

## Roadmap and possible business model

*Roadmap items are not built.*

- **Virtual bench in CI.** Replay every recorded scenario on every commit, so a driver regression is caught before review.
- **Hardware comparison.** When boards arrive, compare the virtual trace with a real bus capture to confirm or correct the model.
- **Shared contract library.** Reviewed, page-cited contracts for common parts that teams can reuse instead of re-reading the same datasheet.
- **Parts without drivers.** Apply the same contract-first method to new or obscure chips that lack vendor or community drivers.

The long-term vision is that every new chip ships with a verified virtual twin built from its datasheet, so firmware teams can build and test from the first day and the software is ready when the hardware arrives.

Possible ways to sustain this, not yet validated:

- **Team subscriptions** for CI integration and private contract libraries.
- **Per-part verified contracts and twins** licensed to firmware teams.
- **Chip vendor partnerships**, where vendors publish verified twins alongside their datasheets as part of the developer experience for a new part.

---

## The workflow

1. IBM Bob reads the vendor PDF and proposes page-linked facts. Kimberly reviews the exact downloaded revision and signs a contract with its source SHA-256, contract hash and profile. Bob cannot sign on the reviewer's behalf.
2. Bob implements reference drivers, virtual devices, targeted tests, fault scenarios and a separate seeded-defect repair candidate. DRIFT's generator consumes **approved contracts plus device-specific templates** to emit executable driver/model files and hash manifests.
3. Scripted bus tests exercise a driver independently of a virtual device. Direct model tests exercise the virtual device independently of the driver. Literal expected answers are prepared separately.
4. A runner records actual bus interactions, results, assertions, limitations and provenance. Two TMP117 byte-swap cases intentionally **fail**; the separate repaired candidate passes the same fixed expectations. An expected-fault report can pass when its driver correctly raises the expected error.

This prototype supports TI TMP117 (one-shot, address `0x48`) and Bosch BME280 (forced temperature only, address `0x76`). It has **not** been tested on physical hardware and does **not** accept arbitrary PDFs as trusted input.

## Reproduce on Python 3.11+

```powershell
py -m venv .venv
.\.venv\Scripts\python.exe -m pip install -e ".[dev]"
.\.venv\Scripts\python.exe -m pytest -q
.\.venv\Scripts\python.exe -m drift.cli verify --profile tmp117_one_shot_no_average --output artifacts\verification.json
.\.venv\Scripts\python.exe scripts\run_bme280_report.py
.\.venv\Scripts\python.exe -m drift.cli generate --contract contracts\tmp117.approved.json --output generated\
.\.venv\Scripts\python.exe -m drift.cli generate --contract contracts\bme280.approved.json --output generated\
```

Run commands from the repository root. Virtual time advances without real sleeps. The TMP117 verify command returns two intentional failing **verification cases** for the seeded byte-swap variant; that does not mean the Python test suite failed. The BME280 script reports two temperature baselines and a two-byte short-read fault.

## Inspect the evidence

- [TI TMP117 source review](docs/TMP117_SOURCE_REVIEW.md), [approved contract](contracts/tmp117.approved.json) and [independent raw vectors](tests/oracles/tmp117_vectors.json).
- [Bosch BME280 approved contract](contracts/bme280.approved.json): thirteen page-linked claims, including little-endian signed calibration and 20-bit temperature compensation.
- [TMP117 run reports](artifacts/verification.json) and [BME280 run reports](artifacts/bme280_verification.json). Reports are recorded Python runs, not live AI output in a browser.
- [Generated manifests and code](generated/), [Bob workflow tasks](prompts/BOB_TASKS.md), [provenance](PROVENANCE.md), and [limitations](AGENTS.md).

## Limitations

Vendor PDFs are intentionally excluded from Git; source URLs and hashes are in the approved contracts and source manifest. Reproducing contract approval from a new source revision requires a new human review. The simulator covers only the selected digital profiles; it does not model analog accuracy, electrical timing or real I²C waveforms.

## Sources

- Semiconductor market forecast: [SIA, WSTS Spring 2026 forecast](https://www.semiconductors.org/global-semiconductor-sales-increase-11-month-to-month-in-april/)
- AI-driven memory supply pressure: [Bloomberg](https://www.bloomberg.com/graphics/2026-ai-boom-memory-chip-shortage/), [CNBC](https://www.cnbc.com/2026/01/26/memory-chip-shortage-synopsys-lenovo-ai-data-centers.html)
