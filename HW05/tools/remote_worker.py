#!/usr/bin/env python3
"""Compute requested notebook parts on the server; export data and text logs only."""
import argparse
import json
import os
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "lib"))
os.environ["HW05_EXECUTION_MODE"] = "server"
from runtime import DEPENDENCIES, SIMULATION, load_meta, now, preflight
from execute_notebooks import execute_path


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--parts", default="bcdefg")
    args = parser.parse_args()
    if not args.parts or any(part not in DEPENDENCIES for part in args.parts):
        parser.error("Parts must be selected from bcdefg")
    overrides = json.loads(sys.stdin.read() or "{}")
    if not isinstance(overrides, dict) or not all(p in DEPENDENCIES and isinstance(v, dict) for p, v in overrides.items()):
        raise ValueError("Expected a JSON object mapping homework parts to parameter overrides")
    preflight()
    done = []
    audit = {"started_utc": now(), "requested_parts": args.parts, "parameters": overrides,
             "rendered_plots": False, "status": "running", "completed_parts": done}
    SIMULATION.mkdir(parents=True, exist_ok=True)
    audit_path = SIMULATION / "last_run.json"
    audit_path.write_text(json.dumps(audit, indent=2))

    def execute(part):
        if part in done:
            return
        for dependency in DEPENDENCIES[part]:
            if load_meta().get("parts", {}).get(dependency, {}).get("status") != "complete":
                execute(dependency)
        index = "bcdefg".index(part)+1
        path = ROOT / "notebooks" / f"{index:02d}_{part}.ipynb"
        execute_path(path, "server", overrides.get(part))
        done.append(part)
        audit_path.write_text(json.dumps(audit, indent=2))

    try:
        for part in "bcdefg":
            if part in args.parts:
                execute(part)
        if all(load_meta().get("parts", {}).get(p, {}).get("status") == "complete" for p in "bcdefg"):
            from validate_results import validate
            validate()
        audit["status"] = "complete"
    except BaseException:
        audit["status"] = "failed"
        raise
    finally:
        audit["finished_utc"] = now()
        audit_path.write_text(json.dumps(audit, indent=2)+"\n")
    print("Remote computation complete. Exporting numerical data; no plot generation.", flush=True)


if __name__ == "__main__":
    main()
