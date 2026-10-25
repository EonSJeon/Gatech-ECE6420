#!/usr/bin/env python3
"""Manage the one-to-one HW05 source workspace and numerical-data transfer."""
import argparse
from pathlib import Path
import sys
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "lib"))
from remote_bridge import RemoteConfig, push_sources, pull_data, run_remote_parts, run_command


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("operation", choices=["status", "push", "pull", "run"], nargs="?", default="status")
    parser.add_argument("--parts", default="bcdefg")
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()
    config = RemoteConfig.load()
    if args.operation == "push":
        push_sources(config, args.dry_run)
    elif args.operation == "pull":
        pull_data(config, args.dry_run)
    elif args.operation == "run":
        if args.dry_run:
            parser.error("Use push --dry-run or pull --dry-run to preview transfers")
        run_remote_parts(args.parts)
    else:
        import shlex
        run_command(config.command(f"hostname && ls -ld {shlex.quote(config.directory)}"))


if __name__ == "__main__":
    main()
