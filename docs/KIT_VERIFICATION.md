# Starter verification — September 26, 2026

These checks were performed on the launch kit in the preparation environment. They are not Bob sessions, application test results, or human approval of the device contract.

| Check | Observed result |
|---|---|
| `python3 scripts/doctor.py` | Completed; Python 3.12.14, Git 2.51.1, Node 24.19.0 and npm 11.9.0 detected in the preparation environment. Your machine may differ. |
| `python3 examples/decode_walkthrough.py` | All eight literal arithmetic expectations matched. |
| Deliberate byte-swap arithmetic | −255.90625 °C differed from expected 25 °C; detected. |
| Deliberate unsigned arithmetic | 511 °C differed from expected −1 °C; detected. |
| Python compilation | Scripts, example and package scaffold compiled successfully. |
| JSON parse | Candidate contract, source manifest and independent-value file parsed successfully. |
| Source download utility | Successfully downloaded both official PDFs and recorded their actual hashes; no approval performed. |
| TMP117 PDF check | Cover SNOSD82D, September 2022; 50 pages. Candidate referenced pages inspected. |
| Short/long copy | 210-character short description; 185-word long description before the optional BME280 sentence. |
| Local Git | Empty local repository initialized for preparation. No GitHub remote created; ZIP omits Git internals. |

The downloaded TMP117 hash differs from the historical September 20 record even though the cover revision is unchanged. Do not reuse a historical hash as approval of a new PDF. The actual preparation-time hashes are in `sources/manifest.json`; your own download still needs its own review.

Not yet verified: installation on your computer, Windows execution, full application tests, hardware behavior, hosting, Bob repair, generated driver artifacts, or final submission. Those are explicit tasks in the prompt pack.
