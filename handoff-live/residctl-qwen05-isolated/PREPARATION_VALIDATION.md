# Preparation checks — 30 October 2026 (India)

This is a newly packaged portable source/build handoff. It is not a new
inference measurement or a copy of the friend's original WSL binary.

Completed in this preparation environment:

- CRC checks passed for both original handoff archives.
- All 38 pager/reference-source files match the original SOURCE_MANIFEST.
- Downloaded the complete upstream source archive for llama.cpp revision
  `cae63579b67a2c51f160705956abbc8e8ebec458`.
- Applied the original mmap hook without rejected hunks. The complete
  patched dependency is covered by 3492 per-file hashes.
- Built the dependency's shared libraries, all 13 required pager/integration
  objects, the original measurement runner and the separate live runner.
- Verified exported `residctl_llama_mmap` and resolved shared-library linkage.
- Bash syntax, Python compilation and CLI help checks passed.
- Copied required source headers, objects and libraries into a different
  directory whose name contains spaces. Relinked the live runner there.
  Both executables loaded and produced their expected no-model usage exit
  (status 2), with LD_LIBRARY_PATH unset and all libraries resolved from
  the relocated kit. No preparation-directory dependency remained in the
  selected-library RUNPATHs or ldd resolution.
- An existing wrong-size model was rejected without overwriting it.
- The model-copy path rejected an incorrect SHA-256 before inference.
- On a real 1 MiB temporary file, cache preparation observed 256 resident
  pages before the per-file discard and zero afterward.
- Official Qwen repository commit metadata matches the requested 3B model
  hash and exact 2104932768-byte size. Model weights were not downloaded
  in this preparation environment.

Not performed here:

- End-to-end 3B inference, token-parity verification or cgroup/UFFD runs.
  This environment has no effective Linux capabilities and is restricted
  by seccomp. The actual WSL rehearsal remains necessary.
- No new throughput or memory-saving result is claimed.
- Binary compatibility on every WSL distro/CPU is not established. The
  portable rebuild script is the recommended path.

Preparation toolchain: GCC/G++ 13.3.0, CMake 3.28.4, Python 3.12.14,
glibc 2.39, Linux x86_64. Packaged dependency compilation uses
GGML_NATIVE=OFF and CUDA off. Local setup defaults GGML_NATIVE=ON and
records its environment. Libraries and executables use relative $ORIGIN
runtime paths. CMake cache/intermediate files are omitted from the ZIP.

Changes relative to the original live handoff:

- Default kit path is this script's folder; default model is the exact 3B
  filename under that kit. Explicit --kit and --model remain supported.
- Exact model size and hash are enforced; 4096-byte pages are checked.
- The live executable uses a relative library runtime path.
- Added location-independent setup/download/launch/verification helpers.
- The pager policy/algorithm and all reference-source C/C++ files are
  unchanged. Live timing still includes the original streaming overhead.

Model identity source:
https://huggingface.co/Qwen/Qwen2.5-3B-Instruct-GGUF/commit/cc1e68eea5f05f88f41a6de1fc73110178f23715

Upstream archive source:
https://codeload.github.com/ggml-org/llama.cpp/tar.gz/cae63579b67a2c51f160705956abbc8e8ebec458
