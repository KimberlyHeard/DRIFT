# DRIFT

**Datasheet-to-Driver Virtual Verification Lab** · A reproducible, software-level sensor-driver verification prototype created with IBM Bob.

A sensor datasheet spans register addresses, bit fields, byte order, timing and calibration. DRIFT takes a deliberately bounded, human-reviewed device profile and turns it into executable artifacts. It runs the driver against a deterministic virtual device, checks literal independent answers, injects bus faults, and keeps an ordered trace linked to approved source facts. This prototype supports TI TMP117 (one-shot, address `0x48`) and Bosch BME280 (forced temperature only, address `0x76`). It has **not** been tested on physical hardware and does **not** accept arbitrary PDFs as trusted input.

## The workflow

1. IBM Bob reads the vendor PDF and proposes page-linked facts. Kimberly reviews the exact downloaded revision and signs a contract with its source SHA-256, contract hash and profile. Bob cannot sign on the reviewer's behalf.
2. Bob implements reference drivers, virtual devices, targeted tests, fault scenarios and a separate seeded-defect repair candidate. DRIFT's generator consumes **approved contracts plus device-specific templates** to emit executable driver/model files and hash manifests.
3. Scripted bus tests exercise a driver independently of a virtual device. Direct model tests exercise the virtual device independently of the driver. Literal expected answers are prepared separately.
4. A runner records actual bus interactions, results, assertions, limitations and provenance. Two TMP117 byte-swap cases intentionally **fail**; the separate repaired candidate passes the same fixed expectations. An expected-fault report can pass when its driver correctly raises the expected error.

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

Vendor PDFs are intentionally excluded from Git; source URLs and hashes are in the approved contracts and source manifest. Reproducing contract approval from a new source revision requires a new human review. The simulator covers only the selected digital profiles; it does not model analog accuracy, electrical timing or real I²C waveforms.
