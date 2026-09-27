"""Generate BME280 verification report to artifacts/bme280_verification.json."""
import json
import pathlib
import sys

ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from drift.runner_bme280 import execute_bme280_verify
from drift.reporting_bme280 import build_bme280_verification_summary

results = execute_bme280_verify()
summary = build_bme280_verification_summary(results)

out = ROOT / "artifacts" / "bme280_verification.json"
out.parent.mkdir(parents=True, exist_ok=True)
out.write_text(json.dumps(summary, indent=2, default=str), encoding="utf-8")

print("Report:", out)
print()
s = summary["summary"]
print(f"Summary: total={s['total']} passed={s['passed']} failed={s['failed']}")
print()
for run in summary["runs"]:
    status = "PASS" if run["verification_status"] == "pass" else "FAIL"
    print(f"  [{status}] {run['scenario_id']}  outcome={run['device_outcome']}")
    for a in run["assertions"]:
        mark = "ok  " if a["passed"] else "FAIL"
        print(f"         {mark}  {a['assertion_id']}: expected={a['expected']}  actual={a['actual']}")
