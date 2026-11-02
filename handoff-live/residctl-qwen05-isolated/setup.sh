#!/usr/bin/env bash
set -euo pipefail
ROOT=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd -P)
cd "$ROOT"
for tool in cmake gcc g++ make python3 patch sha256sum ldd nm; do
    command -v "$tool" >/dev/null || { echo "Missing dependency: $tool. See README.md." >&2; exit 2; }
done
case "$ROOT" in /mnt/*) echo 'Use the WSL Linux filesystem, e.g. ~/projects/residctl.' >&2; exit 2;; esac
python3 verify_kit.py --sources-only
mkdir -p bin setup-logs work/pager-obj
{
    uname -a
    gcc --version | head -1
    g++ --version | head -1
    cmake --version | head -1
    python3 --version
    ldd --version | head -1
    printf 'GGML_NATIVE=%s\nBUILD_JOBS=%s\n' "${GGML_NATIVE:-ON}" "${BUILD_JOBS:-4}"
} > setup-logs/environment.txt
LC="$ROOT/work/llama.cpp"
BUILD="$ROOT/work/llama-build"
# The archive deliberately excludes CMake caches and intermediate makefiles.
# If YOU moved a previously configured tree, use a fresh build directory.
if [[ -f "$BUILD/CMakeCache.txt" ]]; then
    CACHE_SOURCE=$(sed -n 's/^CMAKE_HOME_DIRECTORY:INTERNAL=//p' "$BUILD/CMakeCache.txt")
    if [[ "$CACHE_SOURCE" != "$LC" ]]; then
        echo 'A relocated CMake cache was found. Rename work/llama-build, then rerun setup.sh.' >&2
        exit 2
    fi
fi
cmake -S "$LC" -B "$BUILD" -DBUILD_SHARED_LIBS=ON \
    -DCMAKE_BUILD_RPATH_USE_ORIGIN=ON \
    -DGGML_CUDA=OFF -DGGML_NATIVE="${GGML_NATIVE:-ON}" -DLLAMA_CURL=OFF \
    -DCMAKE_BUILD_TYPE=Release -DLLAMA_BUILD_TESTS=OFF \
    2>&1 | tee setup-logs/cmake.log
cmake --build "$BUILD" --parallel "${BUILD_JOBS:-4}" --target llama \
    2>&1 | tee setup-logs/llama-build.log
SRC="$ROOT/reference-source/src"
OBJ="$ROOT/work/pager-obj"
PAGER_C=(core/region.c core/pager.c core/fetch.c core/budget.c
    observability/trace.c observability/metrics.c observability/cgroup_stat.c
    policy/policy.c prefetch/prefetch.c prefetch/prefetch_pool.c
    observability/fetch_trace.c observability/policy_trace.c)
INCLUDES=(-I"$SRC/core" -I"$SRC/observability" -I"$SRC/policy" -I"$SRC/prefetch" -I"$SRC"
    -I"$LC/include" -I"$LC/ggml/include")
OBJECTS=()
for f in "${PAGER_C[@]}" integrations/llama/residctl_llama.c; do
    obj="$OBJ/$(basename "$f" .c).o"
    gcc -O2 -g -pthread -Wall -Wextra "${INCLUDES[@]}" -c "$SRC/$f" -o "$obj"
    OBJECTS+=("$obj")
done
g++ -O2 -g -std=c++17 -pthread "${INCLUDES[@]}" \
    -c "$SRC/integrations/llama/llama_runner.cpp" -o "$OBJ/llama_runner.o"
g++ -O2 -g -pthread -o "$ROOT/bin/residctl_llama" "$OBJ/llama_runner.o" "${OBJECTS[@]}" \
    -Wl,--export-dynamic -L"$BUILD/bin" '-Wl,-rpath,$ORIGIN/../work/llama-build/bin' \
    -lllama -lggml -lggml-base -lggml-cpu -ldl -lpthread -lm
ldd "$ROOT/bin/residctl_llama" | tee setup-logs/linkage.txt
nm -D "$ROOT/bin/residctl_llama" | grep ' T residctl_llama_mmap$'
sha256sum "$ROOT/bin/residctl_llama" > setup-logs/runner-sha256.txt
# Build the live wrapper now, as the invoking user, before requesting root.
python3 - "$ROOT" <<'PY'
import pathlib, sys
import live_compare
r = pathlib.Path(sys.argv[1])
live_compare.build_runner(r, r/'build')
PY
echo 'Setup complete. Next: bash download_model.sh, then bash run_live.sh'
