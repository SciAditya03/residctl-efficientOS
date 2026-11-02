#!/usr/bin/env bash
set -euo pipefail
ROOT=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd -P)
# Resolve HOME and all paths before sudo; sudo may set HOME=/root.
PYTHON=$(command -v python3)
if [[ $EUID -eq 0 ]]; then
    exec "$PYTHON" "$ROOT/live_compare.py" --kit "$ROOT" "$@"
else
    exec sudo "$PYTHON" "$ROOT/live_compare.py" --kit "$ROOT" "$@"
fi
