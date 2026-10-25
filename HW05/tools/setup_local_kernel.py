#!/usr/bin/env python3
"""Register the Python environment used for local notebook execution and plotting."""
import importlib.util
import subprocess
import sys


def main():
    required = ["numpy", "matplotlib", "nbformat", "nbclient", "ipykernel"]
    missing = [name for name in required if importlib.util.find_spec(name) is None]
    if missing:
        raise SystemExit("Missing packages: " + ", ".join(missing) + ". Install HW05/requirements.txt with this Python first.")
    subprocess.run([sys.executable, "-m", "ipykernel", "install", "--user", "--name", "ece6420-local",
                    "--display-name", "ECE6420 (Local)"], check=True)
    print("Select kernel: ECE6420 (Local)")
    print("Local interpreter:", sys.executable)
    print("Spectre runs through SSH on gt-ece; plots run in this local Python kernel.")


if __name__ == "__main__":
    main()
