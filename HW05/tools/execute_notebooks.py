#!/usr/bin/env python3
"""Execute local notebooks or headless server analysis with the same source files."""
import argparse
import copy
import json
import os
from pathlib import Path
import re
import sys
import nbformat
from nbclient import NotebookClient

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "lib"))
from runtime import preflight


def execute_path(path, mode="review", parameters=None, output_dir=None, in_place=False):
    os.environ["HW05_EXECUTION_MODE"] = mode
    os.environ.setdefault("MPLCONFIGDIR", str(ROOT / "simulation" / "matplotlib"))
    os.environ.setdefault("IPYTHONDIR", str(ROOT / "simulation" / "ipython"))
    original = nbformat.read(path, as_version=4)
    notebook = copy.deepcopy(original)
    for cell in notebook.cells:
        if cell.cell_type != "code":
            continue
        cell.outputs, cell.execution_count = [], None
        cell.source = re.sub(r"(?m)^EXECUTION_MODE = .*", "EXECUTION_MODE = execution_mode()", cell.source)
        if mode == "server" and set(cell.metadata.get("tags", [])) & {"local-only", "remote-bridge"}:
            cell.metadata.setdefault("tags", []).append("skip-execution")
    if parameters:
        allowed = set(original.metadata.get("hw05", {}).get("parameters", []))
        if not set(parameters) <= allowed:
            raise ValueError(f"Unknown parameter override: {set(parameters)-allowed}")
        index = next(i for i, cell in enumerate(notebook.cells) if "parameters" in cell.metadata.get("tags", []))
        source = "import json\nglobals().update(json.loads(" + repr(json.dumps(parameters)) + "))\n"
        source += 'if "F1" in globals() and "F2" in globals():\n    IM31, IM32 = 2*F1-F2, 2*F2-F1\n'
        notebook.cells.insert(index+1, nbformat.v4.new_code_cell(source))
    print(f"Executing {path.name} ({mode}{', no plots' if mode == 'server' else ''})", flush=True)
    kernel = "python3" if mode == "server" else original.metadata.get("kernelspec", {}).get("name", "python3")
    client = NotebookClient(notebook, timeout=3600, kernel_name=kernel, resources={"metadata": {"path": str(ROOT)}})
    manager = client.create_kernel_manager()
    manager.kernel_spec.argv = [sys.executable, "-m", "ipykernel_launcher", "-f", "{connection_file}"]
    try:
        client.execute()
    finally:
        if mode == "server":
            logs = ROOT / "simulation" / "logs"
            logs.mkdir(parents=True, exist_ok=True)
            text = []
            for cell in notebook.cells:
                for output in cell.get("outputs", []):
                    if output.output_type == "stream":
                        text.append(output.text)
                    elif output.output_type == "error":
                        text.append("\n".join(output.traceback))
                    elif any(key.startswith("image/") for key in output.get("data", {})):
                        raise RuntimeError("Server analysis attempted to produce a plot")
            (logs / f"{path.stem}.log").write_text("\n".join(text))
        else:
            if "language_info" in notebook.metadata:
                original.metadata["language_info"] = notebook.metadata["language_info"]
            results = {cell.id: cell for cell in notebook.cells if cell.cell_type == "code"}
            for cell in original.cells:
                if cell.cell_type == "code" and cell.id in results:
                    cell.outputs = results[cell.id].outputs
                    cell.execution_count = results[cell.id].execution_count
            destination = path if in_place else (output_dir or ROOT / "simulation" / "local-executed") / path.name
            destination.parent.mkdir(parents=True, exist_ok=True)
            nbformat.write(original, destination)
    return notebook


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--mode", choices=["review", "remote", "server"], default="review")
    parser.add_argument("--simulate", action="store_true", help="Compatibility alias for --mode server (no plots)")
    parser.add_argument("--part", choices=list("bcdefg"))
    parser.add_argument("--overview", action="store_true")
    parser.add_argument("--output-dir", type=Path)
    parser.add_argument("--in-place", action="store_true", help="Save locally generated output in the source notebook")
    args = parser.parse_args()
    mode = "server" if args.simulate else args.mode
    if mode == "server":
        preflight()
    paths = sorted((ROOT / "notebooks").glob("[0-9][0-9]_*.ipynb"))
    if args.part:
        paths = [p for p in paths if p.stem.endswith("_"+args.part)]
    elif args.overview or mode == "remote":
        paths = [ROOT / "notebooks" / "00_overview.ipynb"]
    elif mode == "server":
        paths = [p for p in paths if "overview" not in p.stem]
    else:
        paths = [p for p in paths if "overview" not in p.stem] + [ROOT / "notebooks" / "00_overview.ipynb"]
    for path in paths:
        execute_path(path, mode, output_dir=args.output_dir, in_place=args.in_place)
    if mode == "server" and not args.part:
        from validate_results import validate
        validate()
    print("Completed. Plots are produced by local notebooks only.", flush=True)


if __name__ == "__main__":
    main()
