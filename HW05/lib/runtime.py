"""Paths, metadata and Spectre execution shared by the HW05 notebooks (Python 3.9+)."""
import hashlib
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
from datetime import datetime, timezone

ROOT = Path(__file__).resolve().parents[1]
REFERENCE = ROOT / "netlists" / "reference"
GENERATED = ROOT / "netlists" / "generated"
SIMULATION = ROOT / "simulation"
RESULT_DIR = ROOT / "results"
CURVES = RESULT_DIR / "curves"
FIGURES = RESULT_DIR / "figures"
META = RESULT_DIR / "hw5_meta.json"
F0 = 5.8e9
Q = 8.0
MODEL = os.environ.get("HW05_MODEL", "/tools/designkits/NCSU/FreePDK4514/ncsu_basekit/models/hspice/tran_models/models_nom/NMOS_VTH.inc")
SPECTRE = os.environ.get("SPECTRE_BIN", "/tools/software/cadence/spectre/latest/tools.lnx86/bin/spectre")
# The login environment historically points to ece-linlic, which times out.
# Use the verified project license unless explicitly overridden for this project.
LICENSE = os.environ.get("HW05_LICENSE", "5280@ece-winlic.ece.gatech.edu:1055@ansyslic.ecs.gatech.edu")
DEPENDENCIES = {"b": [], "c": ["b"], "d": ["c"], "e": [], "f": ["c", "d", "e"], "g": ["c", "e", "f"]}


def now():
    return datetime.now(timezone.utc).isoformat()


def sha256(path):
    path = Path(path)
    return hashlib.sha256(path.read_bytes()).hexdigest() if path.exists() else None


def load_meta():
    if META.exists():
        return json.loads(META.read_text())
    return {"schema": "ECE6420_HW5_META_v1", "created_utc": now(), "parts": {}, "environment": {}}


def require_part(meta, part):
    entry = meta.get("parts", {}).get(part)
    if not entry or entry.get("status") != "complete":
        raise RuntimeError(f"Part ({part}) is missing or stale. Execute its notebook on the server first.")
    return entry


def save_meta(data):
    """Write atomically and mark downstream results stale after an upstream rerun."""
    old = load_meta().get("parts", {})
    parts = data.setdefault("parts", {})
    changed = {p for p, value in parts.items() if value != old.get(p)}
    stale = set()
    for part, deps in DEPENDENCIES.items():
        if part not in changed and any(dep in changed or dep in stale for dep in deps):
            stale.add(part)
    for part in stale:
        if part in parts:
            parts[part]["status"] = "stale"
            parts[part]["stale_reason"] = "An upstream notebook was rerun; execute this part again."
    data["updated_utc"] = now()
    data.setdefault("environment", {}).update({
        "f0_Hz": F0, "inductor_Q": Q, "model_file": MODEL,
        "spectre": SPECTRE, "license_server": LICENSE,
        "input_scs_sha256": sha256(REFERENCE / "input.scs"),
        "tune_c_py_sha256": sha256(ROOT / "lib" / "tune_c.py"),
    })
    RESULT_DIR.mkdir(parents=True, exist_ok=True)
    tmp = META.with_suffix(".json.tmp")
    tmp.write_text(json.dumps(data, indent=2, sort_keys=True) + "\n")
    tmp.replace(META)


def preflight():
    binary = shutil.which(SPECTRE) if "/" not in SPECTRE else SPECTRE
    if not binary or not Path(binary).is_file() or not os.access(binary, os.X_OK):
        raise RuntimeError("Spectre is unavailable. Run simulation notebooks on gt-ece; use review mode locally.")
    if not Path(MODEL).is_file():
        raise RuntimeError(f"PDK model not found: {MODEL}. Set HW05_MODEL if the server path changed.")
    return str(binary)


def write_netlist(path, text):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    # Relative include is portable when inspecting the generated deck.
    text = text.replace('include "ade_e.scs"', 'include "../reference/ade_e.scs"')
    path.write_text(text)


def run_spectre(work, raw, timeout=180, preset=None):
    """Keep simulator byproducts in simulation/ and surface the actual failure log."""
    binary = preflight()
    work, raw = Path(work).resolve(), Path(raw).resolve()
    if not raw.is_relative_to(SIMULATION.resolve()) or raw == SIMULATION.resolve():
        raise ValueError(f"Refusing to replace a directory outside simulation/: {raw}")
    if raw.exists():
        shutil.rmtree(raw)
    raw.mkdir(parents=True)
    text = work.read_text()
    for include in ('include "ade_e.scs"', 'include "../reference/ade_e.scs"'):
        text = text.replace(include, f'include "{REFERENCE / "ade_e.scs"}"')
    text = re.sub(r'include "[^"]*/NMOS_VTH.inc"', lambda _: f'include "{MODEL}"', text)
    text = text.replace('write="spectre.dc"', f'write="{raw / "spectre.dc"}"')
    text = re.sub(r'sensfile="[^"]*"', lambda _: f'sensfile="{raw / "sens.output"}"', text)
    work.write_text(text)
    log = raw / "spectre.out"
    stdout = raw / "stdout.log"
    env = os.environ.copy()
    env.update(CDS_LIC_FILE=LICENSE, LM_LICENSE_FILE=LICENSE)
    cmd = [binary, str(work), "+escchars", "+log", str(log), "-format", "psfascii", "-raw", str(raw), "+mt=1", "+lqtimeout", "60", "-maxw", "5", "-maxn", "5"]
    if preset:
        cmd.append(f"+preset={preset}")
    try:
        with stdout.open("w") as stream:
            proc = subprocess.run(cmd, cwd=raw, env=env, stdout=stream, stderr=subprocess.STDOUT, timeout=timeout)
    except subprocess.TimeoutExpired as exc:
        detail = log.read_text(errors="replace") if log.exists() else stdout.read_text(errors="replace")
        raise RuntimeError(f"Spectre exceeded {timeout}s. Log: {log}\n{detail[-6000:]}") from exc
    detail = log.read_text(errors="replace") if log.exists() else stdout.read_text(errors="replace")
    if proc.returncode or re.search(r"\bERROR\s*\(", detail, re.I):
        raise RuntimeError(f"Spectre failed (exit {proc.returncode}). Log: {log}\n{detail[-6000:]}")
    if not log.exists():
        raise RuntimeError(f"Spectre returned without its completion log: {log}\n{detail[-3000:]}")
    return log


def find_result(raw, analysis):
    files = sorted(Path(raw).glob(f"{analysis}*.{analysis}"))
    if not files:
        raise FileNotFoundError(f"No {analysis} result in {raw}; inspect spectre.out first.")
    return files[0]


def save_curve(name, **arrays):
    import numpy as np
    CURVES.mkdir(parents=True, exist_ok=True)
    completed = require_part(load_meta(), name[0])["completed_utc"]
    np.savez_compressed(CURVES / f"{name}.npz", part_completed_utc=completed, **arrays)


def execution_mode():
    """Local Run defaults to remote compute; the worker explicitly selects server mode."""
    mode = os.environ.get("HW05_EXECUTION_MODE", "remote")
    if mode not in {"remote", "review", "server"}:
        raise ValueError(f"Unknown HW05_EXECUTION_MODE: {mode}")
    return mode


def simulation_enabled():
    return execution_mode() == "server"
