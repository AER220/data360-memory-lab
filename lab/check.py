"""Friendly checkpoint runner for the Data360-Memory lab.

    python lab/check.py                 # check lab/starter/memory_lab.py (your work)
    python lab/check.py ex4             # only exercise 4
    python lab/check.py --solutions     # check the reference solutions
"""
# Here I run the lab checkpoints and present them as a friendly PASS / TODO / FAIL table for
# students.
from __future__ import annotations

import os
import subprocess
import sys
import tempfile
import xml.etree.ElementTree as ET
from pathlib import Path

# Paths are worked out from this file, so the runner works from any folder.
LAB = Path(__file__).resolve().parent
ROOT = LAB.parent
# Friendly names for each exercise, matched against the test name prefixes (test_ex1_...,
# test_stretch_a_...).
EXERCISES = {
    "ex1": "Exercise 1: write filter", "ex2": "Exercise 2: write + correction", "ex3": "Exercise 3: point in time",
    "ex4": "Exercise 4: retrieve (filter first)", "ex5": "Exercise 5: prompt", "ex6": "Exercise 6: delete",
    "stretch_a": "Stretch A: decay and forgetting", "stretch_b": "Stretch B: consolidation",
}


# Runs the lab's pytest checks in a separate process and turns the JUnit XML report into simple rows.
# The Lab page uses this too.
def run_checks(target: str = "starter", only: str | None = None) -> list[dict]:
    with tempfile.TemporaryDirectory() as d:
        xml = Path(d) / "r.xml"
        cmd = [sys.executable, "-m", "pytest", str(LAB / "checks"), "-q", "-p", "no:cacheprovider", f"--junitxml={xml}"]
        if only:
            cmd += ["-k", only]
        # LAB_TARGET tells lab/checks/conftest.py whether to import the starter or the solutions file.
        env = dict(os.environ, LAB_TARGET=target)
        subprocess.run(cmd, cwd=ROOT, env=env, capture_output=True, text=True, timeout=600)
        rows = []
        if not xml.exists():
            return rows
        for tc in ET.parse(xml).getroot().iter("testcase"):
            name = tc.get("name")
            ex = next((k for k in EXERCISES if name.startswith(f"test_{k}_")), "other")
            fail = tc.find("failure")
            if fail is None:
                fail = tc.find("error")
            if fail is None:
                status, msg = "PASS", ""
            else:
                text = (fail.get("message") or "") + (fail.text or "")
                # An untouched starter function raises NotImplementedError; I show that as TODO
                # instead of a scary FAIL.
                status = "TODO" if "NotImplementedError" in text else "FAIL"
                msg = (fail.get("message") or "").splitlines()[0][:160] if status == "FAIL" else "not implemented yet"
            rows.append({"exercise": EXERCISES.get(ex, ex), "check": name, "status": status, "message": msg})
        return rows


# Command-line version: prints a table and exits with 0 only when every check passes.
def main() -> int:
    args = [a for a in sys.argv[1:] if not a.startswith("--")]
    target = "solutions" if "--solutions" in sys.argv else "starter"
    rows = run_checks(target, args[0] if args else None)
    if not rows:
        print("No results. Is pytest installed in this environment?")
        return 2
    width = max(len(r["check"]) for r in rows)
    for r in rows:
        print(f"{r['status']:<5} {r['check']:<{width}}  {r['message']}")
    n = sum(r["status"] == "PASS" for r in rows)
    print(f"\n{n}/{len(rows)} checks pass for lab/{target}/memory_lab.py")
    return 0 if n == len(rows) else 1


if __name__ == "__main__":
    raise SystemExit(main())
