#!/usr/bin/env python3
"""Verify the original pager snapshot and the exact bundled patched dependency."""
import argparse
import hashlib
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parent

def sha256(p):
    h = hashlib.sha256()
    with p.open('rb') as f:
        for b in iter(lambda: f.read(8*1048576), b''): h.update(b)
    return h.hexdigest()

def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument('--sources-only', action='store_true')
    args = ap.parse_args()
    pager = json.loads((ROOT/'SOURCE_MANIFEST.json').read_text())['files']
    upstream = json.loads((ROOT/'DEPENDENCY_MANIFEST.json').read_text())
    for prefix, files in [('reference-source', pager), ('work/llama.cpp', upstream['files'])]:
        for name, want in files.items():
            p = ROOT/prefix/name
            if not p.is_file() or sha256(p) != want:
                raise SystemExit(f'Source verification failed: {p}')
        print(f'Verified {len(files)} files: {prefix}')
    if not args.sources_only:
        manifest = json.loads((ROOT/'BUNDLED_BUILD_MANIFEST.json').read_text())
        for name, want in manifest['files'].items():
            if sha256(ROOT/name) != want:
                raise SystemExit(f'Bundled build differs: {name}. Expected after a local rebuild; inspect setup-logs.')
        print(f'Verified {len(manifest["files"])} bundled build files.')

if __name__ == '__main__':
    main()
