#!/usr/bin/env bash
set -euo pipefail
HW05_ROOT="$(cd "$(dirname "$0")" && pwd)"
HW05_PYTHON="${HW05_PYTHON:-python3}"
if [[ -x "$HW05_ROOT/.venv/bin/python" && "$HW05_PYTHON" == python3 ]]; then
    HW05_PYTHON="$HW05_ROOT/.venv/bin/python"
fi
exec "$HW05_PYTHON" "$HW05_ROOT/tools/execute_notebooks.py" --mode remote --in-place "$@"
