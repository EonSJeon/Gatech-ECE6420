#!/usr/bin/env bash
set -euo pipefail
HW05_ROOT="$(cd "$(dirname "$0")/.." && pwd)"
exec "${HW05_LOCAL_PYTHON:-python3}" "$HW05_ROOT/tools/manage_remote.py" "$@"
