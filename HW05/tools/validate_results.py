#!/usr/bin/env python3
"""Check a completed server run and record comparison with the original submission."""
import json
import math
from pathlib import Path
import sys
import numpy as np

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "lib"))
from runtime import CURVES, REFERENCE, RESULT_DIR, load_meta, now, require_part, sha256


def validate():
    meta = load_meta()
    manifest = json.loads((RESULT_DIR / "migration_manifest.json").read_text())
    parts = {p: require_part(meta, p) for p in "bcdefg"}
    for name in ("input.scs", "ade_e.scs"):
        if sha256(REFERENCE / name) != manifest["original_sha256"][name]:
            raise RuntimeError(f"Reference changed: {name}")
    for p in "bce":
        if abs(parts[p]["outputs"]["fres_Hz"] - 5.8e9) > 2e6:
            raise RuntimeError(f"Part ({p}) misses the 2-MHz resonance tolerance")
    if abs(parts["c"]["outputs"]["Rin_ohm"] - 50) > .25:
        raise RuntimeError("Part (c) misses the 0.25-ohm input-matching tolerance")
    expected_curves = ["b_ac", "c_ac", "c_zin", "d_tran", "e_ac", "e_tran", "f_tran", "g_zin"]
    curves = {}
    for name in expected_curves:
        with np.load(CURVES / f"{name}.npz", allow_pickle=False) as trace:
            if str(trace["part_completed_utc"]) != parts[name[0]]["completed_utc"]:
                raise RuntimeError(f"Stale curve: {name}")
            axis = "time_s" if name.endswith("tran") else "frequency_Hz"
            if len(trace[axis]) < 2 or np.any(np.diff(trace[axis]) <= 0):
                raise RuntimeError(f"Invalid axis: {name}")
            for key in trace.files:
                if key != "part_completed_utc" and (len(trace[key]) != len(trace[axis]) or not np.all(np.isfinite(trace[key]))):
                    raise RuntimeError(f"Invalid trace: {name}/{key}")
            curves[name] = {"samples": len(trace[axis]), "part_completed_utc": str(trace["part_completed_utc"])}
    differences = {}
    for part, baseline in manifest["baseline_outputs"].items():
        current = parts[part]["outputs"]
        differences[part] = {
            key: {"original": old, "current": current.get(key),
                  "difference": current[key]-old,
                  "close_to_original": math.isclose(current[key], old, rel_tol=1e-5, abs_tol=1e-6)}
            for key, old in baseline.items()
            if isinstance(old, (int, float)) and isinstance(current.get(key), (int, float))
        }
    report = {"validated_utc": now(), "all_parts_complete": True, "reference_netlists_unchanged": True,
              "resonance_and_matching_targets_pass": True, "curves": curves,
              "baseline_comparison": differences,
              "note": "Baseline differences are reported, not fitted away. Solution-PDF numbers are comparison references with different initial W1 and mixed conventions."}
    report["validation_scope"] = "Workflow reproduction, resonance/matching targets and data consistency; this does not certify the legacy IIP3 method. See spectral_review.json."
    (RESULT_DIR / "validation.json").write_text(json.dumps(report, indent=2, sort_keys=True) + "\n")
    print("Validated all 6 parts, 2 unchanged reference files, and 8 actual curve datasets.")
    return report


if __name__ == "__main__":
    validate()
