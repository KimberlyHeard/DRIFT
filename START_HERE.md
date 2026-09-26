# Start DRIFT here

**Current state:** Bob IDE/Shell installed. Team DRIFT exists. Core app not implemented. This folder is a repository-ready planning/scaffold kit, not a submitted application.

1. Extract the ZIP and open this folder in Bob IDE.
2. Confirm your hackathon account and actual coin balance in Settings.
3. Open a terminal and run `py scripts/doctor.py`.
4. Run `git init -b main`, then `py -m venv .venv`.
5. Run `.\.venv\Scripts\python.exe -m pip install -e ".[dev]"`.
6. Run `.\.venv\Scripts\python.exe examples/decode_walkthrough.py` to see what the basic decoding example means.
7. Run `.\.venv\Scripts\python.exe scripts/fetch_sources.py --device tmp117`. Open the real PDF in `local_sources/`.
8. In Bob, read AGENTS.md and paste **Task 01** from `prompts/BOB_TASKS.md`. Keep the task bounded.
9. Execute Task 02 and review the actual source facts yourself before approval.
10. After each relevant Bob task: **Tasks → task → task header → screenshot consumption summary → save PNG in bob_sessions/**.

Read `DRIFT_PLAYBOOK.md` for architecture, all sources, workflow, example run, reliability rules, deployment and final submission. `docs/PITCH_AND_DEMO.md` gives explanations and presentation scripts. `STATUS.md` is the handoff between tasks.

Create a public GitHub repository named `drift-datasheet-verification` and follow the playbook's push steps. The ZIP contains no remote connection or Git author identity. This kit should be committed with its actual provenance.

**First project milestone:** a reviewed TMP117 contract plus an independently tested decoder and scripted-bus driver. Then the model, full run, faults, generator, workbench and recorded repair. BME280 extends the proven loop.
