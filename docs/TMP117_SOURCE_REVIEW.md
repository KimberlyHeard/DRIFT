# TMP117 Source Review — DRIFT Judge Reference

**Purpose:** This document provides judges and reviewers with the evidence chain
linking every contract fact (F01–F10) to its printed location in the official TI
datasheet. It distinguishes three categories of information:

| Label | Meaning |
|---|---|
| **TI fact** | A claim read directly from a printed page; page and section cited. |
| **Derived value** | Arithmetic derived from TI facts; flagged as unreviewed until human-approved. |
| **DRIFT policy** | A project-level decision (not from the datasheet); labeled separately per `AGENTS.md`. |

---

## 1. Vendor Source Document

| Field | Value |
|---|---|
| Document number | **SNOSD82D** |
| Revision | **D** |
| Official TI URL | <https://www.ti.com/lit/ds/symlink/tmp117.pdf> |
| Local copy | `local_sources/tmp117.pdf` |
| Provenance record | `local_sources/tmp117.provenance.json` |
| SHA-256 (recorded) | `637a143dda6317d22222e265de47ceac72ba6aed4461ad460efbe84e16b936df` |
| File size (bytes) | 1 718 311 |
| Acquisition | `vendor_download` via `scripts/fetch_sources.py` |
| Hash status | **PENDING human verification** — see §4 below |

> **Important:** The SHA-256 above was recorded by the automated download script.
> A human reviewer must open the physical PDF, confirm the revision letter and
> page numbers for F01–F10, and only then run `scripts/approve_contract.py`.
> The hash is **not** a substitute for reading the pages.

---

## 2. Candidate Contract Facts (F01–F10)

All ten facts below are **TI facts** — claims read from the printed datasheet.
Each entry lists the fact ID, the page(s) and section in the reviewed PDF, and
the verbatim claim from `contracts/tmp117.candidate.json`.

### F01 — I²C Address Selection  
**Page:** 21 &nbsp;|&nbsp; **Section:** Table 7-2  
**Claim:** ADD0 tied to ground selects seven-bit I2C address 0x48.

### F02 — Byte Order  
**Page:** 20 &nbsp;|&nbsp; **Section:** 7.5.3.1  
**Claim:** Register data is transferred most significant byte first.

### F03 — Register Map  
**Page:** 25 &nbsp;|&nbsp; *(section field absent in candidate — reviewer must confirm)*  
**Claim:** Temperature register 0x00, configuration 0x01, device ID 0x0F.

### F04 — Temperature Resolution and Reset Value  
**Page:** 26 &nbsp;|&nbsp; **Section:** 7.6.2  
**Claim:** Temperature is signed 16-bit two's-complement with 1/128 degree Celsius
per LSB; reset temperature word is 0x8000.

### F05 — Configuration Register Layout  
**Page:** 27 &nbsp;|&nbsp; *(section field absent in candidate — reviewer must confirm)*  
**Claim:** Configuration reset is 0x0220; Data_Ready bit 13, MOD bits 11:10,
AVG bits 6:5.

### F06 — MOD and AVG Bit Encodings  
**Page:** 27 &nbsp;|&nbsp; *(section field absent in candidate — reviewer must confirm)*  
**Claim:** MOD 01 selects shutdown, MOD 11 selects one-shot, AVG 00 disables
averaging.

### F07 — Data_Ready Behavior  
**Page:** 27 &nbsp;|&nbsp; *(section field absent in candidate — reviewer must confirm)*  
**Claim:** Conversion completion sets Data_Ready; reading configuration or
temperature clears it.

### F08 — One-Shot Conversion Behavior
**Direct source:** Page 15 &nbsp;|&nbsp; **Section:** 7.4.3
**Context:** Page 14 (shutdown mode description — background context only)
**Claim:** One-shot completes then returns to shutdown; CONV bits do not control
one-shot conversion time.

### F09 — Single Conversion Timing  
**Page:** 6 &nbsp;|&nbsp; *(section field absent in candidate — reviewer must confirm)*  
**Claim:** Single conversion timing is 13 ms minimum, 15.5 ms typical,
17.5 ms maximum.

### F10 — Device ID  
**Page:** 32 &nbsp;|&nbsp; *(section field absent in candidate — reviewer must confirm)*  
**Claim:** Device ID lower 12 bits are 0x117; upper 4 bits represent revision.

---

## 3. Derived Configuration Values (must be verified, not approved yet)

These values are **arithmetic derived from TI facts** — they are not vendor facts.
A reviewer must cross-check each derivation against the printed register map.

| Field | Hex | Derivation note |
|---|---|---|
| `shutdown_config_hex` | `0600` | From reset `0220`: clear MOD mask `0C00`, clear AVG mask `0060`, set MOD=01 (`0400`). |
| `start_config_hex` | `0E00` | From reset `0220`: clear MOD mask `0C00`, clear AVG mask `0060`, set MOD=11 (`0C00`). |
| `completed_config_snapshot_hex` | `2600` | One-shot complete state with Data_Ready (bit 13 = `2000`) set, MOD reverted to shutdown (`0400`), AVG=00. |
| `after_ready_consumed_hex` | `0600` | After reading temperature or config, Data_Ready clears, leaving shutdown config. |

> **Reviewer action:** Open SNOSD82D Rev. D, page 27 (configuration register table),
> and manually verify each hex value against the bit-field definitions before
> calling `scripts/approve_contract.py`.

---

## 4. DRIFT Policies (not vendor facts)

These values are **project decisions**, not claims from the datasheet.

| Policy | Value | Rationale |
|---|---|---|
| `timeout_us` | 100 000 µs | Conservative 100 ms wall-clock budget for a single conversion poll loop. |
| `poll_interval_us` | 1 000 µs | 1 ms poll tick — balances resolution against simulated test cost. |
| `virtual_conversion_us` | 15 500 µs | Matches typical conversion time from F09 (15.5 ms); deterministic for the virtual model. |
| `clock` | `deterministic_integer_microseconds` | Integer-only simulated clock; no floating-point drift in test assertions. |
| `physical_hardware_validated` | `false` | This contract applies to the virtual model only; no real hardware has been tested. |

---

## 5. Approval Prerequisites

Before running `scripts/approve_contract.py` the reviewer **must**:

1. Open `local_sources/tmp117.pdf` and verify the title page reads "SNOSD82D Rev. D".
2. Check each of F01–F10 against the cited page(s) in that exact file.
3. Manually cross-check the four derived hex values in §3 against page 27.
4. Compute or confirm the SHA-256 of `local_sources/tmp117.pdf`
   (`637a143dda6317d22222e265de47ceac72ba6aed4461ad460efbe84e16b936df`).
5. Update `contracts/tmp117.candidate.json` status from `"pending_human_review"`
   to `"reviewed"` only after all of the above are satisfied.
6. Run the CLI and enter name and explicit confirmation interactively.

The approval gate (`scripts/approve_contract.py`) will:
- Recompute the PDF hash from disk and refuse if it does not match.
- Refuse if any fact lacks a citation.
- Refuse if the contract status is still `"pending_*"`.
- Refuse if the profile is not in `SUPPORTED_PROFILES`.
- Bind source hash, canonical contract hash, reviewer identity, and UTC timestamp
  into `contracts/tmp117.approved.json`.

---

## 6. Citation Coverage Summary

| Fact | Page | Section cited | Status |
|---|---|---|---|
| F01 | 21 | ✓ Table 7-2 | Pending human verification |
| F02 | 20 | ✓ 7.5.3.1 | Pending human verification |
| F03 | 25 | ✗ absent | Pending human verification |
| F04 | 26 | ✓ 7.6.2 | Pending human verification |
| F05 | 27 | ✗ absent | Pending human verification |
| F06 | 27 | ✗ absent | Pending human verification |
| F07 | 27 | ✗ absent | Pending human verification |
| F08 | 15 (direct); 14 (context) | ✓ 7.4.3 | Pending human verification |
| F09 | 6 | ✗ absent | Pending human verification |
| F10 | 32 | ✗ absent | Pending human verification |

Facts without a section citation still satisfy the Pydantic gate (page alone is
sufficient), but the reviewer should note the gap and add sections if the printed
page confirms them.

---

*This document was prepared by Bob (IBM Bob, DRIFT task 03 source-review phase).*  
*Source provenance and fact claims are from the candidate contract. No facts have
been approved. The human reviewer's signature on the approved contract is the only
binding approval.*
