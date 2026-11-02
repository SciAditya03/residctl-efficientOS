#!/usr/bin/env bash
set -euo pipefail
ROOT=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd -P)
DEST=${1:-"$ROOT/models/qwen2.5-3b-instruct-q4_k_m.gguf"}
MODEL_URL=https://huggingface.co/Qwen/Qwen2.5-3B-Instruct-GGUF/resolve/cc1e68eea5f05f88f41a6de1fc73110178f23715/qwen2.5-3b-instruct-q4_k_m.gguf
verify() {
    python3 - "$1" <<'PY'
import hashlib, pathlib, sys
p = pathlib.Path(sys.argv[1])
if p.stat().st_size != 2104932768:
    raise SystemExit(f'Wrong model size: {p.stat().st_size}; expected 2104932768 bytes. File left unchanged: {p}')
h = hashlib.sha256()
with p.open('rb') as f:
    for block in iter(lambda: f.read(8*1048576), b''): h.update(block)
if h.hexdigest() != '626b4a6678b86442240e33df819e00132d3ba7dddfe1cdc4fbb18e0a9615c62d':
    raise SystemExit(f'Wrong model SHA256. File left unchanged: {p}')
print(f'Exact Qwen 3B model verified: {p}')
PY
}
mkdir -p -- "$(dirname -- "$DEST")"
if [[ -f "$DEST" ]]; then
    verify "$DEST"
    exit 0
fi
PART="$DEST.part"
if [[ -e "$PART" ]]; then
    echo "Partial file already exists: $PART. Rename it before retrying (no file overwritten)." >&2
    exit 2
fi
curl --fail --location --retry 3 --connect-timeout 30 "$MODEL_URL" -o "$PART"
verify "$PART"
mv -- "$PART" "$DEST"
echo "Model ready: $DEST"
