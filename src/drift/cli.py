"""
DRIFT command-line interface.

Usage
-----
  python -m drift.cli run --profile tmp117_one_shot_no_average \\
         --scenario baseline_25c --driver baseline \\
         --output artifacts/baseline.json

  python -m drift.cli run --profile tmp117_one_shot_no_average \\
         --scenario baseline_25c --driver byte_swap \\
         --output artifacts/byte_swap.json

  python -m drift.cli verify --profile tmp117_one_shot_no_average \\
         --output artifacts/verification.json

Both subcommands:
  - Reject unknown profiles, scenarios, and driver variants before execution.
  - Create the output directory if it does not exist.
  - Print a short summary to stdout on completion.
  - Exit 0 on success (even if verification_status is "fail", which is an
    expected failing report, not a CLI error).
  - Exit 1 on argument errors (unknown profile / scenario / driver).
  - Exit 2 on unexpected infrastructure errors.

Public execution accepts only reviewed named profiles, scenarios, and driver
variants (AGENTS.md boundary).
"""

from __future__ import annotations

import argparse
import json
import sys

from drift.reporting import (
    build_report,
    build_verification_summary,
    report_to_dict,
    save_report,
)
from drift.runner import execute_scenario, execute_verify
from drift.scenarios import (
    CLI_PROFILE_ID,
    SCENARIO_REGISTRY,
    SUPPORTED_DRIVER_VARIANTS,
)


# ---------------------------------------------------------------------------
# Subcommand: run
# ---------------------------------------------------------------------------

def cmd_run(args: argparse.Namespace) -> int:
    """
    Execute one named scenario and write the JSON report to --output.

    Returns an exit code: 0 = ok, 1 = argument error, 2 = infrastructure error.
    """
    try:
        result = execute_scenario(
            scenario_id=args.scenario,
            driver_variant=args.driver,
            profile_id=args.profile,
        )
    except ValueError as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1
    except Exception as exc:
        print(f"INFRASTRUCTURE ERROR: {exc}", file=sys.stderr)
        return 2

    report = build_report(result)
    report_dict = report_to_dict(report, result)
    save_report(report_dict, args.output)

    # Short summary to stdout.
    vs = report_dict["verification_status"]
    outcome = report_dict["device_outcome"]
    n_asserts = len(report_dict["assertions"])
    n_passed = sum(1 for a in report_dict["assertions"] if a["passed"])
    print(
        f"[{vs.upper()}]  scenario={args.scenario}  driver={args.driver}  "
        f"outcome={outcome}  assertions={n_passed}/{n_asserts}  "
        f"report={args.output}"
    )
    return 0


# ---------------------------------------------------------------------------
# Subcommand: verify
# ---------------------------------------------------------------------------

def cmd_verify(args: argparse.Namespace) -> int:
    """
    Execute all scenarios for the profile and write the summary to --output.

    Returns an exit code: 0 = ok, 1 = argument error, 2 = infrastructure error.
    """
    try:
        results = execute_verify(profile_id=args.profile)
    except ValueError as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1
    except Exception as exc:
        print(f"INFRASTRUCTURE ERROR: {exc}", file=sys.stderr)
        return 2

    summary = build_verification_summary(results)
    save_report(summary, args.output)

    # Short summary to stdout.
    s = summary["summary"]
    print(
        f"[VERIFY]  profile={args.profile}  "
        f"total={s['total']}  passed={s['passed']}  failed={s['failed']}  "
        f"report={args.output}"
    )
    for run in summary["runs"]:
        vs = run["verification_status"]
        marker = "✓" if vs == "pass" else "✗"
        print(
            f"  {marker} {run['scenario_id']:25s}  driver={run['driver_variant']:10s}  "
            f"outcome={run['device_outcome']}"
        )
    return 0


# ---------------------------------------------------------------------------
# Argument parser
# ---------------------------------------------------------------------------

def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="python -m drift.cli",
        description="DRIFT TMP117 verification runner",
    )
    sub = parser.add_subparsers(dest="command", required=True)

    # --- run ---
    run_p = sub.add_parser("run", help="Run one scenario and write a JSON report.")
    run_p.add_argument(
        "--profile",
        required=True,
        help=f"Profile ID.  Supported: {CLI_PROFILE_ID!r}",
    )
    run_p.add_argument(
        "--scenario",
        required=True,
        help=f"Scenario ID.  Supported: {sorted(SCENARIO_REGISTRY)}",
    )
    run_p.add_argument(
        "--driver",
        required=True,
        help=f"Driver variant.  Supported: {sorted(SUPPORTED_DRIVER_VARIANTS)}",
    )
    run_p.add_argument(
        "--output",
        required=True,
        help="Output JSON report path (directory created if needed).",
    )

    # --- verify ---
    verify_p = sub.add_parser(
        "verify", help="Run all scenarios and write a verification summary."
    )
    verify_p.add_argument(
        "--profile",
        required=True,
        help=f"Profile ID.  Supported: {CLI_PROFILE_ID!r}",
    )
    verify_p.add_argument(
        "--output",
        required=True,
        help="Output JSON summary path (directory created if needed).",
    )

    return parser


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

def main(argv: list[str] | None = None) -> int:
    parser = _build_parser()
    args = parser.parse_args(argv)

    if args.command == "run":
        return cmd_run(args)
    if args.command == "verify":
        return cmd_verify(args)

    parser.print_help()
    return 1


if __name__ == "__main__":
    sys.exit(main())
