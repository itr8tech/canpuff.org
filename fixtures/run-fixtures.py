#!/usr/bin/env python3
"""Run the CanPUFF conformance fixtures against a validator.

Usage:  run-fixtures.py [--validator PATH] [--update] [fixture ...]

        fixture          names like valid/tombstones (default: all)
        --validator PATH a validate-vault.py-compatible tool
                         (default: ../tools/validate-vault.py, run with
                         this same Python interpreter)
        --update         rewrite each expected.json from the validator's
                         actual output — for maintainers after an
                         intentional validator change; review the diff

Each fixture directory holds:

    vault/           a plain vault (possibly deliberately broken)
    expected.json    { "verdict": "PASS" | "FAIL",
                       "errors":   [substring, ...],
                       "warnings": [substring, ...] }

A fixture agrees with the validator when the verdict (exit code) matches,
the error/warning counts match exactly, and every expected substring
matches a distinct reported message of its category. The last fixture is
also re-run zipped (.canpuff.zip) to prove archive input behaves
identically (Core §8).

Exit codes:  0 all fixtures agree · 1 any disagreement · 2 usage error
"""
import argparse
import json
import os
import re
import subprocess
import sys
import tempfile
import zipfile

HERE = os.path.dirname(os.path.abspath(__file__))
LINE = re.compile(r"^  (warn|ERROR) {1,2}(.*)$")


def run_validator(validator, target):
    proc = subprocess.run([sys.executable, validator, target],
                          capture_output=True, text=True)
    if proc.returncode not in (0, 1):
        print(proc.stderr or proc.stdout, file=sys.stderr)
        sys.exit(f"validator exited {proc.returncode} on {target} — not a verdict")
    errors, warnings = [], []
    for line in proc.stdout.splitlines():
        m = LINE.match(line)
        if m:
            (warnings if m.group(1) == "warn" else errors).append(m.group(2))
    return ("PASS" if proc.returncode == 0 else "FAIL"), errors, warnings


def match(expected, actual, problems, category):
    if len(expected) != len(actual):
        problems.append(f"{category}: expected {len(expected)}, validator reported {len(actual)}")
    unmatched = list(actual)
    for want in expected:
        hit = next((a for a in unmatched if want in a), None)
        if hit is None:
            problems.append(f"{category}: no reported message contains {want!r}")
        else:
            unmatched.remove(hit)
    for extra in unmatched[: max(0, len(actual) - len(expected)) or len(unmatched)]:
        if len(expected) != len(actual):
            problems.append(f"{category}: unexpected message {extra!r}")


def check(validator, fixture, update):
    vault = os.path.join(HERE, fixture, "vault")
    expected_path = os.path.join(HERE, fixture, "expected.json")
    verdict, errors, warnings = run_validator(validator, vault)

    if update:
        with open(expected_path, "w") as f:
            json.dump({"verdict": verdict, "errors": errors, "warnings": warnings},
                      f, indent=2, ensure_ascii=False)
            f.write("\n")
        print(f"  wrote  {fixture}/expected.json  ({verdict}, "
              f"{len(errors)} error(s), {len(warnings)} warning(s))")
        return True

    with open(expected_path) as f:
        expected = json.load(f)
    problems = []
    if expected["verdict"] != verdict:
        problems.append(f"verdict: expected {expected['verdict']}, got {verdict}")
    match(expected.get("errors", []), errors, problems, "errors")
    match(expected.get("warnings", []), warnings, problems, "warnings")

    status = "ok  " if not problems else "FAIL"
    print(f"  {status}  {fixture}  ({verdict}, {len(errors)} error(s), {len(warnings)} warning(s))")
    for p in problems:
        print(f"        {p}")
    return not problems


def check_zip_input(validator, fixture):
    """Zip a fixture vault and confirm the validator's verdict is unchanged (Core §8)."""
    vault = os.path.join(HERE, fixture, "vault")
    with open(os.path.join(HERE, fixture, "expected.json")) as f:
        expected = json.load(f)
    with tempfile.TemporaryDirectory(prefix="canpuff-fixtures-") as td:
        zpath = os.path.join(td, "fixture.canpuff.zip")
        with zipfile.ZipFile(zpath, "w", zipfile.ZIP_DEFLATED) as zf:
            for dirpath, _, files in os.walk(vault):
                for name in sorted(files):
                    full = os.path.join(dirpath, name)
                    zf.write(full, os.path.relpath(full, vault))
        verdict, errors, warnings = run_validator(validator, zpath)
    agrees = (verdict == expected["verdict"]
              and len(errors) == len(expected.get("errors", []))
              and len(warnings) == len(expected.get("warnings", [])))
    print(f"  {'ok  ' if agrees else 'FAIL'}  {fixture} as .canpuff.zip  "
          f"({verdict}, {len(errors)} error(s), {len(warnings)} warning(s))")
    return agrees


def main():
    ap = argparse.ArgumentParser(description="Run the CanPUFF conformance fixtures.")
    ap.add_argument("fixtures", nargs="*", help="e.g. valid/tombstones (default: all)")
    ap.add_argument("--validator",
                    default=os.path.join(HERE, "..", "tools", "validate-vault.py"))
    ap.add_argument("--update", action="store_true")
    args = ap.parse_args()

    if not os.path.isfile(args.validator):
        print(f"{args.validator}: validator not found", file=sys.stderr)
        return 2

    fixtures = args.fixtures or sorted(
        f"{kind}/{name}"
        for kind in ("valid", "invalid") if os.path.isdir(os.path.join(HERE, kind))
        for name in os.listdir(os.path.join(HERE, kind))
        if os.path.isdir(os.path.join(HERE, kind, name)))
    for fixture in fixtures:
        if not os.path.isdir(os.path.join(HERE, fixture, "vault")):
            print(f"{fixture}: no such fixture", file=sys.stderr)
            return 2

    print(f"Running {len(fixtures)} fixture(s) against {os.path.relpath(args.validator, HERE)}")
    ok = all([check(args.validator, f, args.update) for f in fixtures])
    if not args.update and fixtures:
        ok = check_zip_input(args.validator, fixtures[-1]) and ok
    print("ALL FIXTURES AGREE" if ok else "FIXTURE DISAGREEMENT — see above")
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
