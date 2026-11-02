# Portable residctl live comparison — Qwen2.5 3B

This handoff supplies `live_compare.py`, the original pager/reference source,
the complete pinned llama.cpp source with the existing mmap hook applied,
and compiled libraries plus pager objects. It also supplies a local rebuild
script and a hash-checked download script for the exact 3B model. The model
itself is not in the ZIP. The historical folder name `qwen05` is retained;
the default live comparison in this handoff uses **3B**, not 0.5B.

## Run under your existing project

Use the Ubuntu/WSL terminal. Copy `residctl_portable_live_handoff.zip` into
`~/projects/residctl` first. Extract into a fresh folder:

```bash
sudo apt update
sudo apt install -y build-essential cmake git curl patch python3 unzip binutils
mkdir -p "$HOME/projects/residctl/handoff-live"
cd "$HOME/projects/residctl/handoff-live"
unzip ../residctl_portable_live_handoff.zip
cd residctl-qwen05-isolated
```

Do not unzip over a previous run. This folder can live under
`~/projects/residctl`; all active scripts resolve their location at runtime.
They do not depend on `/root/residctl` or the existing `/tmp/wp2_gen` build.

Rebuild the supplied source on your own machine (recommended):

```bash
BUILD_JOBS=4 bash setup.sh
```

Setup builds only this kit's files. It does not fetch a different llama.cpp
revision, download a model, alter the paging algorithm, install libraries
globally, change sysctls, or replace the project's existing binaries.
Use `BUILD_JOBS=2` if compilation is memory constrained. The bundled source
is already patched; do not apply the hook again.

Download and verify the exact model:

```bash
bash download_model.sh
```

Run the short comparison:

```bash
bash run_live.sh \
  --tokens 16 --threads 8 --cap-mib 1800 --weight-ratio 0.75 \
  --prompt "Explain virtual memory in one short sentence."
```

The launcher resolves the kit path before sudo. Enter the Ubuntu password
if prompted. An existing root shell runs directly. Omit `--prompt` to enter
a question interactively. Use a real terminal for the updating display;
logs and result ZIPs are saved automatically.

If you already have the exact model somewhere else, validate and use that
file without moving it:

```bash
bash download_model.sh "$HOME/projects/residctl/models/model.gguf"
bash run_live.sh \
  --model "$HOME/projects/residctl/models/model.gguf" \
  --tokens 16 --cap-mib 1800 --weight-ratio 0.75 \
  --prompt "Explain virtual memory in one short sentence."
```

`download_model.sh PATH` verifies an existing file and stops if its size or
hash differs; it never overwrites that existing file. If PATH is absent it
downloads into PATH. The live script also rejects a wrong size/hash before
starting either inference arm. No Python packages, venv, CUDA, or PyTorch
are required.

## Exact model identity

| Field | Value |
|---|---|
| Publisher | `Qwen/Qwen2.5-3B-Instruct-GGUF` |
| File | `qwen2.5-3b-instruct-q4_k_m.gguf` |
| Pinned repository revision | `cc1e68eea5f05f88f41a6de1fc73110178f23715` |
| Size | `2104932768` bytes |
| SHA-256 | `626b4a6678b86442240e33df819e00132d3ba7dddfe1cdc4fbb18e0a9615c62d` |

Pinned download:
https://huggingface.co/Qwen/Qwen2.5-3B-Instruct-GGUF/resolve/cc1e68eea5f05f88f41a6de1fc73110178f23715/qwen2.5-3b-instruct-q4_k_m.gguf

Publisher's commit showing the exact LFS size/hash:
https://huggingface.co/Qwen/Qwen2.5-3B-Instruct-GGUF/commit/cc1e68eea5f05f88f41a6de1fc73110178f23715

The download script verifies both fields, so a different quantization or a
same-named conversion from another publisher cannot silently substitute.
If downloading manually in Windows, copy the downloaded GGUF into the
kit's `models` folder under the exact lowercase filename above, then run
`bash download_model.sh` to verify it.

Allow roughly 4.3 GB for the model plus the private demo copy, in addition
to source/build space. Keep approximately 6 GB free for setup and the first
run. The private copy is created once for per-file cache preparation.

## Included files and generated files

| Path | Purpose |
|---|---|
| `live_compare.py` | Actual runnable streaming comparison script |
| `reference-source/src/` | All 38 unchanged source/header/patch files from the original isolated kit |
| `SOURCE_MANIFEST.json` | Original pager snapshot hashes/provenance |
| `work/llama.cpp/` | Complete dependency source from commit `cae63579b67a2c51f160705956abbc8e8ebec458`, with only the existing mmap hook applied |
| `DEPENDENCY_MANIFEST.json` | Per-file hashes for that patched source tree and original upstream archive hash |
| `work/llama-build/bin/` | Built `libllama`, `libggml`, `libggml-base`, and `libggml-cpu` shared libraries |
| `work/pager-obj/` | The 13 pager/integration objects needed by `live_compare.py`, plus original runner object |
| `bin/residctl_llama` | Original measurement runner, linked to the included libraries |
| `build/` | Separate live runner, generated C++ and build record |
| `setup.sh` | Rebuild dependency, objects, and both runners in this folder |
| `download_model.sh` | Fetch/verify exact 3B GGUF |
| `run_live.sh` | Portable launcher for normal-user WSL or root |
| `verify_kit.py` | Check source identity; optionally check the initially bundled builds |
| `BUNDLED_BUILD_MANIFEST.json` | Hashes of packaged compiled files |
| `PREPARATION_VALIDATION.md` | What was actually checked, and execution limits |
| `provenance/` | Both original small handoff ZIPs for reference |

CMake caches/intermediate makefiles are deliberately excluded from the
release so absolute preparation paths do not break a fresh local rebuild.
The required compiled libraries/objects are included. Setup creates its own
CMake build metadata when run. Do not copy only the executable: it needs
the compatible libraries and objects/source expected by the live script.

## Dependencies and version information

Prepared on Linux x86_64, Ubuntu 24.04 toolchain: GCC/G++ **13.3.0**,
CMake **3.28.4**, Python **3.12.14**, glibc **2.39**. llama.cpp's source
declares CMake >=3.14. Use Python >=3.9 for the harness. The actual tested
versions above are the reproducibility baseline, not a promise that every
older toolchain is compatible. Your local versions are recorded in
`setup-logs/environment.txt` when you rebuild.

The packaged dependency build uses `GGML_NATIVE=OFF`, CUDA off, shared
libraries, Release mode. It is a fresh preparation build, not your previous
WSL executable. `setup.sh` defaults to `GGML_NATIVE=ON` to optimize locally;
set `GGML_NATIVE=OFF bash setup.sh` to reproduce the preparation choice.
Keep that choice recorded when comparing timings.

The prebuilt ELF files target x86_64 Linux and the preparation toolchain.
On older glibc/libstdc++ or a different architecture, rebuild before use.
Even on a compatible WSL environment, rebuilding is recommended for the
professor demo. The ZIP has no global installation or dependency on `/tmp`.

The pager requires Linux cgroup v2 with a writable memory-controller child
and a kernel/security configuration permitting userfaultfd with shmem
missing/minor faults. Root/sudo is needed for this runner. Root inside a
restricted container may still lack the required capabilities. Use your
previously working WSL environment. The driver requires 4096-byte pages.
Kernel permission failures are execution failures, not timing results.

## What the comparison does

Both arms use the same new executable, exact model, greedy decoding,
Qwen ChatML-wrapped question, output token allowance, CPU threads, and
total cgroup cap. Native runs first, residctl second, sequentially. Native
uses mmap with `RESIDCTL_CONFIG` unset. The pager uses declared order,
prefetch off, pinned retention, four fetch workers, protect_current off,
and the original pre-consumption notification mechanism.

Default settings: 16 output tokens, eight threads, 1800 MiB total cap for
each arm, and a pager weight budget of 75% of the aligned model size
(about 1506 MiB). This is a weight-residency budget, not the model's
parameter count or total process memory. Both total caps stay identical.

The live script creates a private model copy. Before each arm it requests
per-file cache discard and checks page residency using mincore. It stops
if that check fails. No system-wide page-cache drop is used. These checks
cover Linux guest file-cache residency; Windows/host caches remain
uncontrolled. The new cgroup is joined before exec. The live display shows
phase, elapsed time, real output tokens, and current/peak cgroup charge.

`generation s` includes prompt evaluation and streaming instrumentation;
it excludes model loading/context setup. `launch-to-exit s` includes the
runner's loading, context setup, generation, and shutdown, but excludes
Python-side build/copy/hash/cache preparation. The summary also records
launch-to-first-token. Cgroup peak and process RSS are different measures.

This is a live demonstration, not a statistical campaign. New builds,
prompts, hardware and host cache can change the outcome. A speedup is not
guaranteed. No earlier recorded timings are presented as new measurements.
Exact output-token parity must be true before interpreting performance.

## Output and troubleshooting

Completed pairs print a result directory and ZIP under `results/`.
Send the printed ZIP back. It contains raw logs, token IDs, output text,
commands, configs, timestamped events, memory samples and cgroup/cache
evidence; it excludes model weights. Errors retain a partial directory.
The default timeout is 180 seconds per arm; preparation is additional.

- `GLIBC_*` / `GLIBCXX_*` error: run `bash setup.sh` on this machine.
- Missing `.o` / `.so`: keep the complete folder and run setup; do not mix
  these objects with `/tmp/wp2_gen` or unrelated llama.cpp libraries.
- Wrong model size/hash: use the pinned download above; do not rename a
  different model and label it as the expected one.
- `userfaultfd` / cgroup permission error: retain the error and check WSL
  kernel/capabilities; this script does not change global sysctls.
- Timeout/OOM: retain partial evidence. Change settings only explicitly
  and keep the same total allowance for both arms.
- Moved a folder after running setup: the included ELF rpaths are relative,
  and the live runner relinks, but a configured CMake cache has absolute
  paths. Rename only this kit's `work/llama-build` before rebuilding if
  setup reports a relocated cache.

Source check (works without a model or root):

```bash
python3 verify_kit.py --sources-only
python3 live_compare.py --help
```

`python3 verify_kit.py` additionally checks the initially bundled binary
hashes. Those are expected to change after your local rebuild. Source
verification should still pass. Original ZIPs under `provenance` contain
historical instructions; use this README for the portable 3B workflow.
