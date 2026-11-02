#!/usr/bin/env python3
from http.server import ThreadingHTTPServer, BaseHTTPRequestHandler
from pathlib import Path
from urllib.parse import urlparse, unquote
import json, os, re, subprocess, threading, time, uuid

ROOT = Path(__file__).resolve().parent
RESULTS = ROOT / "results"
MODEL = ROOT / "models" / "qwen2.5-3b-instruct-q4_k_m.gguf"
HOST, PORT = "127.0.0.1", 8000
RUNS = {}
LOCK = threading.Lock()
MAX_LOG = 20000

PAGE = r'''<!doctype html>
<html><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>residctl | Local Benchmark</title><style>
:root{color-scheme:dark;--bg:#0a1020;--panel:#121d31;--line:#293954;--muted:#91a2bd;--text:#edf3ff;--green:#65e2a3;--blue:#85bcff;--amber:#ffd078}
*{box-sizing:border-box}body{margin:0;background:radial-gradient(ellipse at 5% 0%,#1a3154 0,transparent 42%),var(--bg);color:var(--text);font:14px/1.5 system-ui,Segoe UI,sans-serif}main{max-width:1400px;margin:auto;padding:26px 22px 44px}.top{display:flex;justify-content:space-between;align-items:center;gap:16px;margin-bottom:22px}.brand{display:flex;gap:12px;align-items:center}.mark{display:grid;place-items:center;width:43px;height:43px;border-radius:14px;background:linear-gradient(135deg,var(--green),var(--blue));color:#071322;font-size:22px;font-weight:900}.eyebrow{font-size:10px;letter-spacing:.16em;text-transform:uppercase;color:var(--green);font-weight:800}.title{font-size:26px;font-weight:850;letter-spacing:-.04em}.muted{color:var(--muted);font-size:12px}.pill{border:1px solid #2d765b;border-radius:99px;background:#102a27;color:var(--green);padding:7px 11px;font-size:11px;font-weight:800}
.layout{display:grid;grid-template-columns:340px minmax(0,1fr);gap:17px;align-items:start}.stack{display:grid;gap:17px}.panel{background:linear-gradient(180deg,#15223a,#111a2b);border:1px solid var(--line);border-radius:17px;padding:19px;box-shadow:0 12px 32px #0002}.panel h2{font-size:15px;margin:0 0 3px}.desc{color:var(--muted);font-size:12px;margin:0 0 16px}label{display:block;font-size:12px;color:#bfcee2;font-weight:700;margin:12px 0 6px}textarea,input{width:100%;background:#0a1425;border:1px solid #344866;color:var(--text);border-radius:10px;padding:10px 11px;font:inherit}textarea{min-height:82px;resize:vertical}.fields{display:grid;grid-template-columns:1fr 1fr;gap:9px}.btn{cursor:pointer;border:0;border-radius:10px;padding:12px 14px;font-weight:850;font:inherit}.primary{width:100%;margin-top:17px;background:linear-gradient(100deg,var(--green),var(--blue));color:#071322;font-weight:900}.secondary{background:#22334f;color:var(--text);border:1px solid #344866;padding:6px 10px;font-size:11px}.btn:disabled{opacity:.5;cursor:not-allowed}.status{display:flex;align-items:center;gap:8px;margin-top:13px;color:var(--muted);font-size:12px}.dot{width:8px;height:8px;border-radius:50%;background:#7586a0}.dot.running{background:var(--amber)}.dot.ok{background:var(--green)}.dot.bad{background:#ff8585}.hint{font-size:11px;color:var(--muted);margin-top:10px}
.metrics{display:grid;grid-template-columns:repeat(4,minmax(0,1fr));gap:10px}.metric{background:#0c1729;border:1px solid var(--line);border-radius:13px;padding:14px;min-width:0}.k{color:var(--muted);font-size:10px;text-transform:uppercase;letter-spacing:.09em;font-weight:800}.v{font-size:24px;font-weight:850;letter-spacing:-.04em;margin-top:7px;overflow-wrap:anywhere}.unit{color:var(--muted);font-size:10px}.good{color:var(--green)}.warn{color:var(--amber)}.head{display:flex;align-items:center;justify-content:space-between;gap:10px;margin-bottom:13px}.head h2{margin:0}.small{font-size:10px;color:var(--muted)}
.compare{display:grid;grid-template-columns:1fr 1fr;gap:11px}.arm{border:1px solid var(--line);border-radius:13px;overflow:hidden;background:#0c1729}.armhead{background:#182740;padding:11px 13px;font-weight:850;display:flex;justify-content:space-between}.armhead span{font-size:10px;color:var(--muted)}.armbody{padding:13px}.stats{display:flex;gap:16px;flex-wrap:wrap;margin-bottom:12px}.stats strong{display:block;font-size:17px}.stats span{display:block;color:var(--muted);font-size:10px}.response{white-space:pre-wrap;overflow-wrap:anywhere;min-height:45px;border-top:1px solid #253550;padding-top:11px;font-size:12px;color:#d5e2f6}
.progressbox{background:#0b1425;border:1px solid var(--line);padding:13px;border-radius:12px;margin-top:14px}.progressmeta{display:flex;justify-content:space-between;color:var(--muted);font-size:11px;margin-bottom:8px}.track{height:8px;background:#273650;border-radius:99px;overflow:hidden}.fill{height:100%;width:0;background:linear-gradient(90deg,var(--green),var(--blue));transition:width .25s}.bars{display:grid;gap:13px}.barrow{display:grid;grid-template-columns:105px minmax(0,1fr) 62px;gap:10px;align-items:center;font-size:11px}.bartrack{height:8px;background:#26344c;border-radius:99px;overflow:hidden}.barfill{height:100%;background:linear-gradient(90deg,var(--blue),var(--green));width:0}.barfill.alt{background:#7186a8}.log{background:#080e19;border:1px solid #26344c;border-radius:11px;padding:12px;max-height:230px;overflow:auto;white-space:pre-wrap;overflow-wrap:anywhere;font:11px/1.5 ui-monospace,Consolas,monospace;color:#b9c8dc}
table{border-collapse:collapse;width:100%;font-size:11px}th{text-align:left;color:var(--muted);font-size:9px;text-transform:uppercase;letter-spacing:.08em}td,th{padding:10px 8px;border-bottom:1px solid #26344c;vertical-align:top}tr:last-child td{border-bottom:0}.empty{text-align:center;color:var(--muted);padding:22px}.footer{color:#71829d;font-size:10px;margin-top:18px;display:flex;justify-content:space-between;gap:10px;flex-wrap:wrap}
@media(max-width:950px){.layout{grid-template-columns:1fr}.metrics{grid-template-columns:repeat(2,minmax(0,1fr))}}@media(max-width:600px){main{padding:15px 11px}.title{font-size:22px}.top{align-items:flex-start}.pill{font-size:9px}.compare{grid-template-columns:1fr}.panel{padding:14px}.metric{padding:11px}.v{font-size:21px}}
</style></head><body><main>
<header class="top"><div class="brand"><div class="mark">r</div><div><div class="eyebrow">Local inference lab</div><div class="title">residctl <span style="color:#91a2bd;font-weight:500">/ benchmark</span></div><div class="muted">Native inference vs. memory-managed inference</div></div></div><div class="pill">● LOCAL ONLY · 127.0.0.1</div></header>
<div class="layout"><aside class="stack">
<section class="panel"><h2>Configure a run</h2><p class="desc">Runs the actual pinned-model comparison, not a simulation.</p><label for="prompt">Prompt</label><textarea id="prompt">Explain virtual memory in one short sentence.</textarea>
<div class="fields"><div><label>Output tokens</label><input id="tokens" type="number" min="1" max="256" value="16"></div><div><label>CPU threads</label><input id="threads" type="number" min="1" max="128" value="8"></div><div><label>Memory cap (MiB)</label><input id="cap" type="number" min="512" max="65536" value="1800"></div><div><label>Pager weight ratio</label><input id="ratio" type="number" min=".1" max=".95" step=".05" value=".75"></div></div>
<button class="btn primary" id="runBtn" onclick="startRun()">▶ &nbsp; Run native vs. residctl</button><div class="status"><span id="dot" class="dot"></span><span id="status">Ready when you are</span></div><p class="hint">Keep this terminal/server open. A benchmark runs one arm after the other. Do not start another run until it finishes.</p></section>
<section class="panel"><div class="head"><h2>Live progress</h2><span class="small" id="arm">IDLE</span></div><div class="progressbox"><div class="progressmeta"><span id="progressLabel">Waiting for a run</span><b id="progressPct">0%</b></div><div class="track"><div class="fill" id="progressFill"></div></div></div><div class="fields" style="margin-top:10px"><div class="metric"><div class="k">Tokens seen</div><div class="v" id="tokensNow">—</div></div><div class="metric"><div class="k">Current charge</div><div class="v" id="chargeNow">—</div><div class="unit">MiB</div></div></div></section>
</aside><div class="stack">
<section class="metrics"><div class="metric"><div class="k">Throughput change</div><div class="v" id="speedChange">—</div><div class="unit">residctl vs native</div></div><div class="metric"><div class="k">Elapsed-time change</div><div class="v" id="timeChange">—</div><div class="unit">lower is better</div></div><div class="metric"><div class="k">Peak-memory change</div><div class="v" id="memChange">—</div><div class="unit">lower is better</div></div><div class="metric"><div class="k">Token parity</div><div class="v" id="parity">—</div><div class="unit">exact token IDs</div></div></section>
<section class="panel"><div class="head"><h2>Run comparison</h2><span id="stamp" class="small">No run selected</span></div><div class="compare">
<div class="arm"><div class="armhead">Native <span>BASELINE</span></div><div class="armbody"><div class="stats"><div><strong id="ntps">—</strong><span>tokens/sec</span></div><div><strong id="ntime">—</strong><span>launch → exit (s)</span></div><div><strong id="nmem">—</strong><span>peak MiB</span></div></div><div class="response" id="nout">Native response appears here.</div></div></div>
<div class="arm"><div class="armhead">residctl <span>PAGER ENABLED</span></div><div class="armbody"><div class="stats"><div><strong id="rtps">—</strong><span>tokens/sec</span></div><div><strong id="rtime">—</strong><span>launch → exit (s)</span></div><div><strong id="rmem">—</strong><span>peak MiB</span></div></div><div class="response" id="rout">residctl response appears here.</div></div></div></div></section>
<section class="panel"><div class="head"><h2>Relative performance</h2><span class="small">Native = 100%</span></div><div class="bars"><div class="barrow"><span>Throughput</span><div class="bartrack"><div class="barfill" id="sb"></div></div><b id="sr">—</b></div><div class="barrow"><span>Elapsed time</span><div class="bartrack"><div class="barfill alt" id="tb"></div></div><b id="tr">—</b></div><div class="barrow"><span>Peak memory</span><div class="bartrack"><div class="barfill alt" id="mb"></div></div><b id="mr">—</b></div></div><p class="hint">Positive throughput change means faster generation. Lower elapsed time and memory are improvements. One run is not a statistical conclusion.</p></section>
<section class="panel"><div class="head"><h2>Runner output</h2><button class="btn secondary" onclick="copyLog()">Copy log</button></div><div class="log" id="log">Runner output will stream here.</div></section>
<section class="panel"><div class="head"><h2>Run history</h2><button class="btn secondary" onclick="loadHistory()">Refresh</button></div><div style="overflow-x:auto"><table><thead><tr><th>Run</th><th>Native tok/s</th><th>residctl tok/s</th><th>Change</th><th>Parity</th><th>Evidence</th></tr></thead><tbody id="history"><tr><td colspan="6" class="empty">Loading saved runs…</td></tr></tbody></table></div></section>
</div></div><div class="footer"><span>residctl local benchmark dashboard · standard library only</span><span>Metrics are populated from actual runner output.</span></div></main>
<script>
let active=null,timer=null,lastLog='';const $=x=>document.getElementById(x);
function f(n,d=2){return Number.isFinite(Number(n))?Number(n).toFixed(d):'—'}function pc(n){return Number.isFinite(Number(n))?`${n>=0?'+':''}${n.toFixed(1)}%`:'—'}
function esc(s){return String(s??'').replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]))}
async function api(u,o={}){let r=await fetch(u,{headers:{'Content-Type':'application/json'},...o}),x=await r.json();if(!r.ok)throw Error(x.error||'Request failed');return x}
function status(s,k=''){$('status').textContent=s;$('dot').className='dot '+k}
async function startRun(){if($('runBtn').disabled)return;let a={prompt:$('prompt').value,tokens:+$('tokens').value,threads:+$('threads').value,cap_mib:+$('cap').value,weight_ratio:+$('ratio').value};$('runBtn').disabled=true;status('Starting benchmark…','running');$('log').textContent='Starting…';try{let x=await api('/api/run',{method:'POST',body:JSON.stringify(a)});active=x.id;timer=setInterval(poll,650);poll()}catch(e){status(e.message,'bad');$('runBtn').disabled=false}}
async function poll(){if(!active)return;try{let x=await api('/api/run/'+active);lastLog=x.log||'';$('log').textContent=lastLog;$('log').scrollTop=$('log').scrollHeight;$('arm').textContent=(x.arm||x.state).toUpperCase();$('tokensNow').textContent=x.tokens_seen??'—';$('chargeNow').textContent=x.current_mib==null?'—':f(x.current_mib,1);$('progressLabel').textContent=x.message||x.state;$('progressPct').textContent=(x.progress||0)+'%';$('progressFill').style.width=(x.progress||0)+'%';if(x.state==='running')status(x.message||'Benchmark running','running');if(x.result){show(x.result);loadHistory()}if(x.state==='completed'){clearInterval(timer);timer=null;active=null;$('runBtn').disabled=false;status('Benchmark completed','ok');$('progressFill').style.width='100%';$('progressPct').textContent='100%'}if(x.state==='failed'){clearInterval(timer);timer=null;active=null;$('runBtn').disabled=false;status(x.error||'Benchmark failed','bad')}}catch(e){status(e.message,'bad')}}
function show(r){let n=r.native||{},p=r.residctl||{};$('stamp').textContent=r.id||'Completed';$('ntps').textContent=f(n.tok_s,3);$('rtps').textContent=f(p.tok_s,3);$('ntime').textContent=f(n.elapsed_s,3);$('rtime').textContent=f(p.elapsed_s,3);$('nmem').textContent=f(n.peak_mib,1);$('rmem').textContent=f(p.peak_mib,1);$('nout').textContent=n.output||'See runner log / result ZIP';$('rout').textContent=p.output||'See runner log / result ZIP';
let s=n.tok_s>0&&p.tok_s>0?(p.tok_s/n.tok_s-1)*100:null,t=n.elapsed_s>0&&p.elapsed_s>0?(1-p.elapsed_s/n.elapsed_s)*100:null,m=n.peak_mib>0&&p.peak_mib>0?(1-p.peak_mib/n.peak_mib)*100:null;
[['speedChange',s],['timeChange',t],['memChange',m]].forEach(([id,v])=>{$(id).textContent=pc(v);$(id).className='v '+(v>0?'good':v<0?'warn':'')});$('parity').textContent=r.token_parity===true?'PASS':r.token_parity===false?'FAIL':'—';$('parity').className='v '+(r.token_parity===true?'good':'warn');
let sr=n.tok_s>0&&p.tok_s>0?p.tok_s/n.tok_s*100:0,tr=n.elapsed_s>0&&p.elapsed_s>0?p.elapsed_s/n.elapsed_s*100:0,mr=n.peak_mib>0&&p.peak_mib>0?p.peak_mib/n.peak_mib*100:0;
$('sb').style.width=Math.min(100,sr/2)+'%';$('tb').style.width=Math.min(100,tr)+'%';$('mb').style.width=Math.min(100,mr)+'%';$('sr').textContent=sr?f(sr,1)+'%':'—';$('tr').textContent=tr?f(tr,1)+'%':'—';$('mr').textContent=mr?f(mr,1)+'%':'—'}
async function loadHistory(){try{let x=await api('/api/runs'),b=$('history');b.innerHTML='';if(!x.runs.length){b.innerHTML='<tr><td colspan="6" class="empty">No saved run summaries yet.</td></tr>';return}x.runs.forEach(r=>{let s=r.native_tps>0&&r.residctl_tps>0?(r.residctl_tps/r.native_tps-1)*100:null,tr=document.createElement('tr');tr.innerHTML=`<td><b>${esc(r.id)}</b><br><span class="small">${esc(r.when||'')}</span></td><td>${f(r.native_tps,3)}</td><td>${f(r.residctl_tps,3)}</td><td class="${s>0?'good':s<0?'warn':''}">${pc(s)}</td><td>${r.parity===true?'PASS':r.parity===false?'FAIL':'—'}</td><td>${r.zip?`<a style="color:#85bcff" href="/api/zip/${encodeURIComponent(r.id)}">Download ZIP</a>`:'—'}</td>`;b.appendChild(tr)})}catch(e){$('history').innerHTML=`<tr><td colspan="6" class="empty">${esc(e.message)}</td></tr>`}}
async function copyLog(){try{await navigator.clipboard.writeText(lastLog||$('log').textContent);status('Runner log copied','ok')}catch(e){status('Select the log and copy manually','bad')}}
loadHistory();setInterval(loadHistory,10000);
</script></body></html>'''

def nested_dicts(x):
    if isinstance(x, dict):
        yield x
        for v in x.values(): yield from nested_dicts(v)
    elif isinstance(x, list):
        for v in x: yield from nested_dicts(v)

def first(d, keys):
    for k in keys:
        if isinstance(d, dict) and d.get(k) is not None: return d[k]
    return None

def read_run(run_id, log=""):
    match = re.search(r"Results:\s*(.+)", log)
    p = Path(match.group(1).strip()) if match else RESULTS / run_id
    if not p.is_absolute(): p = ROOT / p
    data={}
    try: data=json.loads((p/"summary.json").read_text(errors="replace"))
    except Exception: pass
    objs=list(nested_dicts(data))
    result={"id":run_id,"native":{},"residctl":{},"token_parity":None}
    for arm in ("native","residctl"):
        obj=next((o for o in objs if str(o.get("arm","")).lower()==arm),None)
        if obj is None: obj=next((o for o in objs if arm in str(o.get("name","")).lower()),{})
        result[arm]={"tok_s":first(obj,["tok_s","tokens_per_second","tps"]),
                     "elapsed_s":first(obj,["elapsed_s","launch_to_exit_s","elapsed_seconds"]),
                     "peak_mib":first(obj,["peak_mib","peak_memory_mib","cgroup_peak_mib"]),
                     "output":first(obj,["output","text","response"])}
    result["token_parity"]=next((o[k] for o in objs for k in ("token_parity","exact_output_token_parity","exact_token_parity") if isinstance(o.get(k),bool)),None)
    for arm in ("native","residctl"):
        if not result[arm]["tok_s"]:
            m=re.search(rf"(?im)^\s*{arm}\s+\d+\s+([\d.]+)\s+([\d.]+)\s+([\d.]+)\s+([\d.]+)\s*$",log)
            if m: result[arm].update(elapsed_s=float(m.group(2)),tok_s=float(m.group(3)),peak_mib=float(m.group(4)))
    if result["token_parity"] is None:
        m=re.search(r"Exact output token parity:\s*(True|False)",log,re.I)
        if m: result["token_parity"]=m.group(1).lower()=="true"
    return result

def scan_runs():
    out=[]
    if not RESULTS.exists(): return out
    for p in sorted((x for x in RESULTS.iterdir() if x.is_dir()),key=lambda x:x.name,reverse=True):
        log=""
        try: log=(p/"runner.log").read_text(errors="replace")
        except Exception: pass
        r=read_run(p.name,log)
        zipf=RESULTS/(p.name+".zip")
        out.append({"id":p.name,"when":time.strftime("%Y-%m-%d %H:%M",time.localtime(p.stat().st_mtime)),
                    "native_tps":r["native"]["tok_s"],"residctl_tps":r["residctl"]["tok_s"],
                    "parity":r["token_parity"],"zip":zipf.exists()})
    return out

def worker(rid, args):
    state=RUNS[rid]
    cmd=["sudo","-n","python3",str(ROOT/"live_compare.py"),"--kit",str(ROOT),
         "--tokens",str(args["tokens"]),"--threads",str(args["threads"]),
         "--cap-mib",str(args["cap_mib"]),"--weight-ratio",str(args["weight_ratio"]),
         "--prompt",args["prompt"]]
    try:
        proc=subprocess.Popen(cmd,cwd=ROOT,stdout=subprocess.PIPE,stderr=subprocess.STDOUT,text=True,bufsize=1,
                              env={**os.environ,"PYTHONUNBUFFERED":"1"})
        lines=[]
        state.update(state="running",message="Native arm starting",arm="native",progress=2)
        for line in iter(proc.stdout.readline,""):
            lines.append(line); state["log"]="".join(lines)[-MAX_LOG:]
            m=re.search(r"(NATIVE|RESIDCTL):\s*(\w+).*?tokens?\s+(\d+)/(\d+).*?([\d.]+)\s+MiB",line,re.I)
            if m:
                arm=m.group(1).lower(); seen=int(m.group(3)); total=max(1,int(m.group(4)))
                progress=(4+44*seen/total) if arm=="native" else (52+44*seen/total)
                state.update(arm=arm,tokens_seen=seen,current_mib=float(m.group(5)),
                             message=f"{arm} generating · {seen}/{total} tokens",progress=min(96,int(progress)))
            if "NATIVE:" in line and "completed" in line.lower():
                state.update(arm="residctl",message="Native completed · residctl starting",progress=50)
        code=proc.wait(); log="".join(lines); state["log"]=log[-MAX_LOG:]
        if code: state.update(state="failed",error=f"Runner exited with status {code}; inspect runner output.",message="Benchmark failed")
        else: state.update(state="completed",result=read_run(rid,log),progress=100,message="Benchmark completed",arm="completed")
    except Exception as e: state.update(state="failed",error=str(e),message="Could not launch runner")

class Handler(BaseHTTPRequestHandler):
    def log_message(self,*args): pass
    def sendj(self,obj,status=200):
        b=json.dumps(obj,default=str).encode();self.send_response(status);self.send_header("Content-Type","application/json");self.send_header("Content-Length",str(len(b)));self.send_header("Cache-Control","no-store");self.end_headers();self.wfile.write(b)
    def do_GET(self):
        path=urlparse(self.path).path
        if path=="/":
            b=PAGE.encode();self.send_response(200);self.send_header("Content-Type","text/html; charset=utf-8");self.send_header("Content-Length",str(len(b)));self.end_headers();self.wfile.write(b);return
        if path=="/api/runs": self.sendj({"runs":scan_runs()});return
        if path.startswith("/api/run/"):
            rid=unquote(path.rsplit("/",1)[-1]);s=RUNS.get(rid)
            if not s:self.sendj({"error":"Unknown run id"},404);return
            self.sendj({k:v for k,v in s.items() if k!="process"});return
        if path.startswith("/api/zip/"):
            rid=unquote(path.rsplit("/",1)[-1]);p=RESULTS/(rid+".zip")
            if not p.exists() or p.resolve().parent!=RESULTS.resolve():self.sendj({"error":"ZIP not found"},404);return
            b=p.read_bytes();self.send_response(200);self.send_header("Content-Type","application/zip");self.send_header("Content-Disposition",f'attachment; filename="{p.name}"');self.send_header("Content-Length",str(len(b)));self.end_headers();self.wfile.write(b);return
        self.sendj({"error":"Not found"},404)
    def do_POST(self):
        if urlparse(self.path).path!="/api/run":self.sendj({"error":"Not found"},404);return
        try:
            n=int(self.headers.get("Content-Length","0"))
            if n>20000:raise ValueError("Request too large")
            a=json.loads(self.rfile.read(n));prompt=str(a.get("prompt","")).strip()
            tokens=int(a.get("tokens",16));threads=int(a.get("threads",8));cap=int(a.get("cap_mib",1800));ratio=float(a.get("weight_ratio",.75))
            if not prompt or len(prompt)>4000:raise ValueError("Prompt must be 1–4000 characters.")
            if not 1<=tokens<=256:raise ValueError("Tokens must be 1–256.")
            if not 1<=threads<=128:raise ValueError("Threads must be 1–128.")
            if not 512<=cap<=65536:raise ValueError("Memory cap must be 512–65536 MiB.")
            if not .1<=ratio<=.95:raise ValueError("Pager ratio must be 0.1–0.95.")
            if not MODEL.exists():raise ValueError("Pinned model is missing; run download_model.sh first.")
            with LOCK:
                if any(s.get("state") in ("starting","running") for s in RUNS.values()):self.sendj({"error":"A benchmark is already running."},409);return
                rid=time.strftime("%Y%m%d-%H%M%S")+"-"+uuid.uuid4().hex[:6]
                RUNS[rid]={"id":rid,"state":"starting","message":"Starting runner","arm":"starting","progress":0,"tokens_seen":0,"current_mib":None,"log":""}
                threading.Thread(target=worker,args=(rid,{"prompt":prompt,"tokens":tokens,"threads":threads,"cap_mib":cap,"weight_ratio":ratio}),daemon=True).start()
            self.sendj({"id":rid},202)
        except Exception as e:self.sendj({"error":str(e)},400)

if __name__=="__main__":
    if not (ROOT/"live_compare.py").exists():raise SystemExit("Place dashboard.py inside residctl-qwen05-isolated, beside live_compare.py.")
    print(f"residctl dashboard: http://{HOST}:{PORT}")
    print("Web server runs as your normal user. Run `sudo -v` first so benchmark runs can use sudo -n.")
    ThreadingHTTPServer((HOST,PORT),Handler).serve_forever()
