# DRIFT current status

Snapshot reviewed September 27, 2026. Final Windows test count must be rerun after the last patch.

## Demonstrated scope

- TI TMP117 one-shot, no averaging, I²C 0x48: human-approved ten-fact contract, signed MSB-first decoder, reference driver, deterministic virtual model, generated driver/model, four injected environmental faults, two deliberately failing byte-swap cases, and a separate repaired candidate that passes unchanged expectations.
- Bosch BME280 forced temperature-only, I²C 0x76: human-approved thirteen-fact contract, signed little-endian calibration, 20-bit compensation, reference driver, virtual model, three recorded scenarios (25.08 °C, −7.86 °C and short read), generated driver/model and hash manifest.
- Python test suite reported by Kimberly on Windows: **307 passed in 0.86 s** before the final five generator/fault-trace checks. The five new checks passed under Python's unittest in the extracted review snapshot; rerun the full suite on Windows before updating this count.
- Bob's BME280 generator produced executable files. Independent review executed its generated driver against two literal scripted bus fixtures and its generated virtual model; 25.08 °C and −7.86 °C both passed at 4,000 virtual µs. Repeated driver/model file bytes matched, output hashes matched manifest, stale edited approval was rejected. Save the focused test result in the public repository.
- Independent review of this uploaded snapshot checked all 65,536 possible TMP117 16-bit raw encodings with zero arithmetic mismatches; 100 deterministic replays of the current ten TMP117 plus three BME280 scenarios (1,300 software executions) differed in zero normalized report groups. Recheck after final changes; these are software results, not sensor hardware measurements or independent physical environments.

## Verified source identities

- TMP117 source SHA-256 `637a143dda6317d22222e265de47ceac72ba6aed4461ad460efbe84e16b936df`; approved content `5f15b14e522a0ad886f07dda88a32ae3771951141bbeb4f139c6395e1cf0423f`.
- BME280 source SHA-256 `a2ccdb449fec94380742fe8eec851a11d9bd4142252d332b34682b4deecd7d89`; approved content `5b1ef2802b99e0e708dafae30de96f0bdacc5a349c0e9e6504d65a5f7f3bfa13`.
- Reviewer Kimberly Heard; exact timestamps in approved contracts. Vendor PDF bytes stay in `local_sources/`, outside Git.

## Immediate release checklist

1. Apply/review short-read trace and generated BME tests; regenerate both verification JSON files; run the Windows full suite.
2. Commit code, generated manifests, selected real reports and Bob screenshots. Ensure the README and provenance describe the actual work.
3. Push to a public repository and verify a signed-out clone/use. Publish a workbench showing actual report traces, source facts, expected vs observed, and before/after repair; label recorded output.
4. Record a video under three minutes with Kimberly's narration, capture live site and genuine Bob session evidence, complete the hackathon submission and verify confirmation well before 11 AM EDT.

## Limits

Selected profiles only. Templates hold device-specific register information; source review and approval require a human. No live AI execution in the workbench or physical/electrical validation is asserted.
