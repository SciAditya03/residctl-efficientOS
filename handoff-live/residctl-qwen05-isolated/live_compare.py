#!/usr/bin/env python3
"""Portable native/pager live comparison for the hash-pinned Qwen 3B model."""
import argparse
import codecs
import ctypes
import hashlib
import json
import os
import pathlib
import re
import selectors
import shutil
import signal
import subprocess
import sys
import time
import zipfile

ROOT = pathlib.Path(__file__).resolve().parent
MIB = 1048576
EXPECTED_MODEL_BYTES = 2104932768
EXPECTED_MODEL_SHA256 = '626b4a6678b86442240e33df819e00132d3ba7dddfe1cdc4fbb18e0a9615c62d'
CGROUP_ROOT = pathlib.Path('/sys/fs/cgroup')

LIVE_CPP = r'''
#include <unistd.h>
static long long live_now_us() {
    struct timespec ts; clock_gettime(CLOCK_MONOTONIC, &ts);
    return (long long)ts.tv_sec * 1000000LL + ts.tv_nsec / 1000;
}
static void live_phase(const char *name) {
    fprintf(stderr, "LIVE_PHASE,%s,%lld\n", name, live_now_us()); fflush(stderr);
}
static void live_token(const llama_vocab *v, llama_token id) {
    long long stamp = live_now_us();
    std::vector<char> buf(256);
    int32_t n = llama_token_to_piece(v, id, buf.data(), (int32_t)buf.size(), 0, false);
    if (n < 0) { buf.resize((size_t)-n); n = llama_token_to_piece(v, id, buf.data(), (int32_t)buf.size(), 0, false); }
    fprintf(stderr, "LIVE_TOKEN,%d,%lld,", (int)id, stamp);
    for (int32_t i = 0; i < n; ++i) fprintf(stderr, "%02x", (unsigned char)buf[i]);
    fputc('\n', stderr); fflush(stderr);
}
'''


def replace_once(text, old, new):
    if text.count(old) != 1:
        raise RuntimeError('Unexpected runner source; no changes made to the original. Missing/ambiguous anchor: ' + old[:90])
    return text.replace(old, new, 1)


def build_runner(kit, out):
    source = kit / 'reference-source/src/integrations/llama/llama_runner.cpp'
    lc = kit / 'work/llama.cpp'
    lib = kit / 'work/llama-build/bin'
    objdir = kit / 'work/pager-obj'
    names = ['region', 'pager', 'fetch', 'budget', 'trace', 'metrics', 'cgroup_stat',
             'policy', 'prefetch', 'prefetch_pool', 'fetch_trace', 'policy_trace', 'residctl_llama']
    objects = [objdir / (n + '.o') for n in names]
    for p in [source, lc / 'include/llama.h', *objects]:
        if not p.is_file():
            raise RuntimeError(f'Missing existing setup output: {p}. Complete the isolated kit setup first.')
    text = source.read_text()
    text = replace_once(text, 'int main(int argc, char ** argv) {', LIVE_CPP + '\nint main(int argc, char ** argv) {\n    fprintf(stderr, "LIVE_PID,%ld\\n", (long)getpid()); fflush(stderr);\n    live_phase("runner_start");')
    text = replace_once(text, '    llama_model * model = llama_model_load_from_file(model_path.c_str(), mp);',
                        '    live_phase("loading_model");\n    llama_model * model = llama_model_load_from_file(model_path.c_str(), mp);\n    live_phase("model_loaded");')
    text = replace_once(text, '    llama_context * ctx = llama_init_from_model(model, cp);',
                        '    live_phase("creating_context");\n    llama_context * ctx = llama_init_from_model(model, cp);\n    live_phase("context_ready");')
    text = replace_once(text, '    uint64_t io0 = proc_io_read_bytes();',
                        '    live_phase("generating");\n    uint64_t io0 = proc_io_read_bytes();')
    text = replace_once(text, '        n_decoded++;', '        n_decoded++;\n        live_token(vocab, id);')
    text = replace_once(text, '    int64_t t1 = ggml_time_us();', '    int64_t t1 = ggml_time_us();\n    live_phase("generation_finished");')
    text = replace_once(text, '    residctl_llama_teardown();  // no-op if the pager was never started',
                        '    live_phase("shutting_down");\n    residctl_llama_teardown();  // no-op if the pager was never started\n    live_phase("finished");')
    out.mkdir(parents=True, exist_ok=True)
    cpp = out / 'llama_runner_live.cpp'
    cpp.write_text(text)
    exe = out / 'residctl_llama_live'
    cmd = ['g++', '-O2', '-g', '-std=c++17', '-pthread', '-I' + str(source.parent),
           '-I' + str(lc / 'include'), '-I' + str(lc / 'ggml/include'), str(cpp),
           *map(str, objects), '-o', str(exe), '-Wl,--export-dynamic', '-L' + str(lib),
           '-Wl,-rpath,$ORIGIN/../work/llama-build/bin', '-lllama', '-lggml', '-lggml-base', '-lggml-cpu', '-ldl', '-lpthread', '-lm']
    print('Building a separate streaming executable; the existing runner and pager objects are unchanged.', flush=True)
    p = subprocess.run(cmd, text=True, stdout=subprocess.PIPE, stderr=subprocess.STDOUT)
    (out / 'build.log').write_text(p.stdout)
    if p.returncode:
        raise RuntimeError('Streaming runner build failed:\n' + p.stdout[-6000:])
    (out / 'build-command.json').write_text(json.dumps(cmd, indent=2) + '\n')
    return exe


def hash_file(path):
    h = hashlib.sha256()
    with path.open('rb') as f:
        for b in iter(lambda: f.read(8 * MIB), b''):
            h.update(b)
    return h.hexdigest()


def model_copy(source):
    st = source.stat()
    key = hashlib.sha256(f'{source}:{st.st_size}:{st.st_mtime_ns}'.encode()).hexdigest()[:16]
    dest = ROOT / 'models' / key / 'model.gguf'
    dest.parent.mkdir(parents=True, exist_ok=True)
    if not dest.exists():
        if shutil.disk_usage(dest.parent).free < st.st_size + 128 * MIB:
            raise RuntimeError('Not enough free disk space for an independent model copy.')
        print(f'Copying {st.st_size / MIB:.1f} MiB into the demo folder once. Original model is unchanged.', flush=True)
        part = dest.with_suffix('.part')
        shutil.copyfile(source, part)
        now = source.stat()
        if (now.st_size, now.st_mtime_ns) != (st.st_size, st.st_mtime_ns):
            raise RuntimeError('Original model changed during copying; stop and inspect.')
        part.replace(dest)
    if dest.stat().st_size != st.st_size:
        raise RuntimeError('Demo model copy has an unexpected size.')
    print('Recording the model hash before per-run cache preparation ...', flush=True)
    digest = hash_file(dest)
    if digest != EXPECTED_MODEL_SHA256:
        raise RuntimeError(f'Wrong model SHA256: {digest}; expected {EXPECTED_MODEL_SHA256}. No comparison run.')
    return dest, {'source_path': str(source), 'source_size': st.st_size,
                  'source_mtime_ns': st.st_mtime_ns, 'demo_copy': str(dest), 'sha256': digest}


def residency(fd, length):
    libc = ctypes.CDLL(None, use_errno=True)
    libc.mmap.argtypes = [ctypes.c_void_p, ctypes.c_size_t, ctypes.c_int, ctypes.c_int, ctypes.c_int, ctypes.c_longlong]
    libc.mmap.restype = ctypes.c_void_p
    libc.mincore.argtypes = [ctypes.c_void_p, ctypes.c_size_t, ctypes.POINTER(ctypes.c_ubyte)]
    libc.mincore.restype = ctypes.c_int
    libc.munmap.argtypes = [ctypes.c_void_p, ctypes.c_size_t]
    libc.munmap.restype = ctypes.c_int
    ptr = libc.mmap(None, length, 1, 1, fd, 0)  # PROT_READ, MAP_SHARED; no memory dereference
    if ptr == ctypes.c_void_p(-1).value:
        raise OSError(ctypes.get_errno(), 'mmap residency observer failed')
    try:
        n = (length + os.sysconf('SC_PAGE_SIZE') - 1) // os.sysconf('SC_PAGE_SIZE')
        vec = (ctypes.c_ubyte * n)()
        if libc.mincore(ptr, length, vec):
            raise OSError(ctypes.get_errno(), 'mincore failed')
        return {'resident_pages': sum(bool(x & 1) for x in vec), 'pages': n}
    finally:
        libc.munmap(ptr, length)


def prepare_cache(model):
    fd = os.open(model, os.O_RDWR)
    try:
        os.fsync(fd)
        before = residency(fd, model.stat().st_size)
        os.posix_fadvise(fd, 0, 0, os.POSIX_FADV_DONTNEED)
        after = residency(fd, model.stat().st_size)
        if after['resident_pages'] > 16:
            raise RuntimeError(f'Per-file cache discard was not established: {after}. Stop rather than treating this as a prepared run.')
        return {'method': 'fsync + per-file DONTNEED, checked with mincore without reading model bytes',
                'before': before, 'after': after, 'scope': 'Linux guest cache only; host cache not controlled'}
    finally:
        os.close(fd)


def read_text(path):
    try:
        return path.read_text()
    except OSError:
        return None


def number(path):
    s = read_text(path)
    return int(s.strip()) if s and s.strip().isdigit() else None


def snapshot(cg):
    fields = ['memory.max', 'memory.high', 'memory.swap.max', 'memory.current', 'memory.peak',
              'memory.events', 'memory.stat', 'io.stat', 'cpu.stat', 'cpu.max', 'cpuset.cpus.effective']
    return {str(group): {name: read_text(group / name) for name in fields}
            for group in [CGROUP_ROOT, cg]}


def metrics_from_log(log, prefix):
    lines = [x for x in log.splitlines() if x.startswith(prefix + ',')]
    return dict(x.split('=', 1) for x in lines[-1].split(',')[1:] if '=' in x) if lines else None


def safe_text(s):
    return ''.join(c if c in '\n\t' or ord(c) >= 32 and ord(c) != 127 else '?' for c in s)


def render(states, settings, force=False):
    if not sys.stdout.isatty():
        return
    lines = ['RESIDCTL — REAL LIVE COMPARISON',
             f"Same model / question | {settings['tokens']} requested tokens | CPU threads {settings['threads']}",
             f"Total cap BOTH: {settings['cap_mib']} MiB | Pager weight budget: {settings['weight_bytes'] / MIB:.1f} MiB",
             'Linux guest file-cache preparation verified separately before each arm.',
             'Question: ' + safe_text(settings['question']), '']
    for state in states:
        elapsed = state.get('elapsed', 0)
        completed = state.get('phase') == 'completed'
        mem = state.get('memory_peak') if completed else state.get('memory_current')
        label = 'peak charged' if completed else 'currently charged'
        memtext = f'{mem / MIB:.1f} MiB {label}' if mem is not None else 'memory unavailable'
        lines += [f"{state['arm'].upper()}: {state.get('phase', 'waiting')} | elapsed {elapsed:.1f}s | "
                  f"tokens {len(state.get('token_ids', []))}/{settings['tokens']} | {memtext}",
                  safe_text(state.get('text', '')) or '(No output token yet.)', '']
    sys.stdout.write('\033[H\033[2J' + '\n'.join(lines) + '\n')
    sys.stdout.flush()


def run_arm(arm, args, model, exe, folder, states, settings):
    folder.mkdir()
    print(f'Preparing {arm}: discarding only the demo copy from the Linux file cache ...', flush=True)
    prep = prepare_cache(model)
    (folder / 'cache-preparation.json').write_text(json.dumps(prep, indent=2) + '\n')
    cg = CGROUP_ROOT / f'residctl_live_{os.getpid()}_{time.time_ns()}_{arm}'
    cg.mkdir()
    p = None
    state = {'arm': arm, 'phase': 'starting', 'token_ids': [], 'text': '', 'elapsed': 0}
    states.append(state)
    try:
        for f, v in [('memory.max', args.cap_mib * MIB), ('memory.high', 'max'), ('memory.swap.max', 0)]:
            (cg / f).write_text(str(v) + '\n')
        (folder / 'cgroup-before.json').write_text(json.dumps(snapshot(cg), indent=2) + '\n')
        env = os.environ.copy()
        env.pop('RESIDCTL_CONFIG', None)
        env['LD_LIBRARY_PATH'] = str(args.kit / 'work/llama-build/bin')
        if arm == 'residctl':
            cfg = folder / 'pager.conf'
            cfg.write_text(f'model={model}\ncgroup={cg}\nbudget_bytes={settings["weight_bytes"]}\n'
                           'policy=layer_order_declared\nprefetch=off\nretention=pinned\n'
                           'fetch_workers=4\nprotect_current=off\neager_reconcile=0\n')
            env['RESIDCTL_CONFIG'] = str(cfg)
        query = args.prompt
        if not args.raw_prompt:
            query = '<|im_start|>system\nYou are a helpful assistant.<|im_end|>\n<|im_start|>user\n' + query + '<|im_end|>\n<|im_start|>assistant\n'
        cmd = [str(exe), '-m', str(model), '-n', str(args.tokens), '-t', str(args.threads),
               '-p', query, '--dump-tokens', str(folder / 'tokens.txt')]
        if arm == 'residctl':
            cmd += ['--inventory', str(folder / 'inventory.txt')]
        launch = ['timeout', '--foreground', '--signal=TERM', '--kill-after=10s', str(args.timeout) + 's',
                  'bash', '-c', 'set -e; printf "%s\\n" "$$" > "$1/cgroup.procs"; shift; exec "$@"', '_', str(cg), *cmd]
        (folder / 'command.json').write_text(json.dumps({'command': launch, 'prompt': query,
                    'RESIDCTL_CONFIG': env.get('RESIDCTL_CONFIG'), 'LD_LIBRARY_PATH': env['LD_LIBRARY_PATH']}, indent=2) + '\n')
        started = time.monotonic()
        p = subprocess.Popen(launch, env=env, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, start_new_session=True)
        sel = selectors.DefaultSelector()
        sel.register(p.stdout, selectors.EVENT_READ)
        pending = b''
        pieces = bytearray()
        plain_decoder = codecs.getincrementaldecoder('utf-8')('replace')
        last_plain = 0
        log_lines = []
        events = []
        def consume(line):
            nonlocal pieces
            s = line.decode(errors='replace').rstrip('\r\n')
            log_lines.append(s)
            if s.startswith('LIVE_PHASE,'):
                _, phase, stamp = s.split(',')
                state['phase'] = phase
                events.append({'type': 'phase', 'phase': phase, 'monotonic_us': int(stamp)})
            elif s.startswith('LIVE_TOKEN,'):
                _, idx, stamp, hx = s.split(',', 3)
                b = bytes.fromhex(hx)
                pieces.extend(b)
                state['text'] = pieces.decode('utf-8', errors='replace')
                state['token_ids'].append(int(idx))
                events.append({'type': 'token', 'id': int(idx), 'monotonic_us': int(stamp), 'piece_hex': hx})
                if not sys.stdout.isatty():
                    print(f'[{arm} {time.monotonic() - started:.2f}s token {len(state["token_ids"])}] {plain_decoder.decode(b)!r}', flush=True)
            elif s.startswith('LIVE_PID,'):
                state['pid'] = int(s.split(',')[1])
        with (folder / 'runner.log').open('wb') as raw, (folder / 'samples.jsonl').open('w') as samples:
            while sel.get_map():
                for key, _ in sel.select(timeout=0.25):
                    b = os.read(key.fd, 65536)
                    if not b:
                        sel.unregister(key.fileobj)
                        continue
                    raw.write(b)
                    raw.flush()
                    pending += b
                    while b'\n' in pending:
                        line, pending = pending.split(b'\n', 1)
                        consume(line)
                state['elapsed'] = time.monotonic() - started
                state['memory_current'] = number(cg / 'memory.current')
                state['memory_peak'] = number(cg / 'memory.peak')
                sample = {'elapsed_s': state['elapsed'], 'phase': state['phase'],
                          'tokens': len(state['token_ids']), 'memory_current': state['memory_current'],
                          'memory_peak': state['memory_peak']}
                if state.get('pid'):
                    status = read_text(pathlib.Path('/proc') / str(state['pid']) / 'status')
                    m = re.search(r'^VmRSS:\s*(\d+) kB', status or '', re.M)
                    sample['process_rss_bytes'] = int(m[1]) * 1024 if m else None
                samples.write(json.dumps(sample) + '\n')
                render(states, settings)
                if not sys.stdout.isatty() and state['elapsed'] - last_plain >= 2:
                    print(f'[{arm}] {state["phase"]}; elapsed {state["elapsed"]:.1f}s; tokens {len(state["token_ids"])}', flush=True)
                    last_plain = state['elapsed']
            if pending:
                consume(pending)
        rc = p.wait()
        state['elapsed'] = time.monotonic() - started
        after = snapshot(cg)
        (folder / 'cgroup-after.json').write_text(json.dumps(after, indent=2) + '\n')
        (folder / 'events.json').write_text(json.dumps(events, indent=2) + '\n')
        (folder / 'output.txt').write_text(state['text'])
        (folder / 'exit-code.txt').write_text(str(rc) + '\n')
        log = '\n'.join(log_lines)
        rec = metrics_from_log(log, 'WP2_CSV')
        stats = metrics_from_log(log, 'RESIDCTL_STATS')
        expected_mode = 'mmap' if arm == 'native' else 'residctl'
        if rc or not rec or rec.get('arm_mode') != expected_mode:
            raise RuntimeError(f'{arm} failed or has no valid summary (exit {rc}). Inspect {folder}/runner.log')
        if arm == 'residctl' and (not stats or 'residctl_llama: region up.' not in log or 'using plain mmap' in log):
            raise RuntimeError('Pager activation not confirmed; do not interpret as a pager run.')
        saved = [int(x) for x in (folder / 'tokens.txt').read_text().split()]
        if saved != state['token_ids'] or len(saved) != int(rec['n_decoded']) or not saved:
            raise RuntimeError('Live token events do not match the saved nonempty output sequence.')
        state['phase'] = 'completed'
        state['memory_peak'] = number(cg / 'memory.peak')
        render(states, settings)
        token_events = [e for e in events if e['type'] == 'token']
        launch_to_first = token_events[0]['monotonic_us'] / 1000000 - started
        span = (token_events[-1]['monotonic_us'] - token_events[0]['monotonic_us']) / 1000000
        decode_rate = (len(saved) - 1) / span if len(saved) >= 2 and span > 0 else None
        return {'runner_metrics': rec, 'pager_metrics': stats, 'launch_to_exit_s': state['elapsed'],
                'launch_to_first_token_s': launch_to_first, 'first_to_last_token_throughput': decode_rate,
                'peak_cgroup_bytes': number(cg / 'memory.peak'), 'token_ids': saved,
                'output_text': state['text'], 'cache_preparation': prep}
    finally:
        if p is not None and p.poll() is None:
            os.killpg(p.pid, signal.SIGTERM)
            try:
                p.wait(timeout=5)
            except subprocess.TimeoutExpired:
                os.killpg(p.pid, signal.SIGKILL)
                p.wait()
        try:
            cg.rmdir()
        except OSError:
            print(f'New demo cgroup retained for inspection: {cg}', file=sys.stderr)


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument('--kit', type=pathlib.Path, default=ROOT, help='Built kit folder; defaults to this script directory')
    ap.add_argument('--model', type=pathlib.Path, help='Exact 3B GGUF; defaults to KIT/models/qwen2.5-3b-instruct-q4_k_m.gguf')
    ap.add_argument('--prompt', help='Your question. If omitted, ask interactively.')
    ap.add_argument('--tokens', type=int, default=16)
    ap.add_argument('--threads', type=int, default=8)
    ap.add_argument('--cap-mib', type=int, default=1800, help='Identical total cgroup allowance for both arms')
    ap.add_argument('--weight-ratio', type=float, default=0.75, help='Pager residency budget / aligned model file size')
    ap.add_argument('--timeout', type=int, default=180, help='Per-arm timeout in seconds')
    ap.add_argument('--raw-prompt', action='store_true', help='Pass prompt verbatim; otherwise use Qwen ChatML wrapper for these Qwen models')
    args = ap.parse_args()
    if os.geteuid() != 0:
        raise SystemExit('This CLI needs root for new cgroups and userfaultfd. Use sudo python3 live_compare.py with the same arguments. It is not a web server.')
    if not 1 <= args.tokens <= 256 or args.threads < 1 or args.cap_mib < 1 or args.timeout < 1 or not 0 < args.weight_ratio <= 1:
        ap.error('Use 1..256 output tokens, positive threads/cap/timeout, and weight ratio in (0,1].')
    args.kit = args.kit.expanduser().resolve()
    args.model = pathlib.Path(args.model).expanduser().resolve(strict=True) if args.model else (args.kit / 'models/qwen2.5-3b-instruct-q4_k_m.gguf').resolve(strict=True)
    if args.model.stat().st_size != EXPECTED_MODEL_BYTES:
        ap.error(f'Wrong model size: {args.model.stat().st_size}; expected {EXPECTED_MODEL_BYTES} bytes. Obtain the exact model with download_model.sh.')
    if os.sysconf('SC_PAGE_SIZE') != 4096:
        ap.error('This handoff requires a 4096-byte Linux page size.')
    if args.model.suffix.lower() != '.gguf':
        ap.error('Select a GGUF file.')
    if args.prompt is None:
        args.prompt = input('Enter your question: ').strip()
    if not args.prompt:
        ap.error('Question must not be empty.')
    region = (args.model.stat().st_size + 4095) // 4096 * 4096
    weight = int(region * args.weight_ratio)
    if weight >= args.cap_mib * MIB:
        ap.error('Weight budget must leave headroom below the total cap for runtime memory.')
    settings = {'expected_model_sha256': EXPECTED_MODEL_SHA256, 'model_size': args.model.stat().st_size, 'tokens': args.tokens, 'threads': args.threads,
                'cap_mib': args.cap_mib, 'weight_bytes': weight, 'raw_prompt': args.raw_prompt, 'question': args.prompt,
                'note': 'Real-time display/instrumented run, guest file-cache prepared; host cache not controlled; not a statistical benchmark.'}
    print(f'Model: {args.model} ({region / MIB:.1f} MiB aligned). Both total caps: {args.cap_mib} MiB; pager weights: {weight / MIB:.1f} MiB.')
    exe = build_runner(args.kit, ROOT / 'build')
    model, identity = model_copy(args.model)
    run = ROOT / 'results' / (time.strftime('%Y%m%d-%H%M%S') + '-' + str(os.getpid()))
    run.mkdir(parents=True)
    (run / 'settings.json').write_text(json.dumps({**settings, 'question': args.prompt, 'kit': str(args.kit)}, indent=2) + '\n')
    (run / 'model-identity.json').write_text(json.dumps(identity, indent=2) + '\n')
    (run / 'uname.txt').write_text(subprocess.check_output(['uname', '-a'], text=True))
    states = []
    records = {}
    try:
        for arm in ['native', 'residctl']:
            records[arm] = run_arm(arm, args, model, exe, run / arm, states, settings)
        parity = records['native']['token_ids'] == records['residctl']['token_ids']
        (run / 'summary.json').write_text(json.dumps({'settings': settings, 'arms': records, 'exact_token_parity': parity}, indent=2) + '\n')
        print('\nACTUAL COMPLETED RUNS (generation timing includes live-output instrumentation)')
        print('Arm          output N   generation s   launch-to-exit s   tok/s   cgroup peak MiB')
        for arm, rec in records.items():
            m = rec['runner_metrics']; peak = rec['peak_cgroup_bytes']
            print(f"{arm:12} {m['n_decoded']:>8} {m['wall_s']:>14} {rec['launch_to_exit_s']:>18.3f} {m['tokens_s']:>8} {peak / MIB if peak is not None else float('nan'):>17.2f}")
        print('Exact output token parity:', parity)
        print('Results:', run)
        archive = run.parent / (run.name + '.zip')
        with zipfile.ZipFile(archive, 'x', zipfile.ZIP_DEFLATED) as z:
            for p in sorted(run.rglob('*')):
                if p.is_file():
                    z.write(p, p.relative_to(run.parent))
            for p in [pathlib.Path(__file__), ROOT / 'build/llama_runner_live.cpp', ROOT / 'build/build.log', ROOT / 'build/build-command.json']:
                z.write(p, 'demo-code/' + p.name)
        print('Send this result ZIP:', archive)
        if not parity:
            raise RuntimeError('Output mismatch: stop performance interpretation.')
    except BaseException:
        print('\nPartial evidence preserved:', run, file=sys.stderr)
        raise


if __name__ == '__main__':
    try:
        main()
    except KeyboardInterrupt:
        print('\nStopped by user; only this demo process group was stopped.', file=sys.stderr)
        sys.exit(130)
    except (RuntimeError, OSError) as exc:
        print('\nSTOP:', exc, file=sys.stderr)
        sys.exit(1)
