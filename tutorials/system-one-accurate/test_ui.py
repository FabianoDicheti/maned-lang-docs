#!/usr/bin/env python3
"""A tiny local web UI to test System One in the browser.

    cd mnd_scripts/tutorials/system_one   # the tutorial project folder
    . ~/.config/maned/xlm.env         # worker host + login
    python3 test_ui.py                # -> http://127.0.0.1:8808

Two tabs:
  Decide  drives the SAME decide() the tutorial uses (consumers/python/decide.py):
          the fast lane runs in-process through manedpy, the XLM slow lane and
          the record are maned-run processes on the worker.
  API     documents the endpoints for testing - this UI's own test API and the
          XLM worker's HTTP API (port 4780) - with copy-paste curl, and a live
          worker health check.

Zero third-party deps.
"""
import json
import os
import sys
import threading
import urllib.request
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, "consumers", "python"))

# Importing decide chdirs to the project and loads 01_lookup.mnd once.
import decide as engine  # noqa: E402

engine.load_env()  # ~/.config/maned/xlm.env -> XLM_USER / XLM_PASS / S1_WORKER_HOST

# ensure a memory exists (no worker needed for this)
if not os.path.exists("work/memory.dqt"):
    os.makedirs("work/q/out", exist_ok=True)
    os.makedirs("work/ranges", exist_ok=True)
    engine.run_mnd("00_init_memory.mnd")

LOCK = threading.Lock()  # decide() shares work/q files + reloads the lookup; serialize

PORT = int(os.environ.get("S1_UI_PORT", "8808"))
WORKER_PORT = 4780  # the XLM worker's HTTP API


def worker_host():
    return os.environ.get("S1_WORKER_HOST", "")


def effective_learn():
    return int(os.environ.get("S1_LEARN", engine.DEFAULT_LEARN))


def worker_status():
    """GET the worker's /api/status (no auth). Returns parsed JSON or {error}."""
    host = worker_host()
    if not host:
        return {"error": "S1_WORKER_HOST is not set (source ~/.config/maned/xlm.env)"}
    url = "http://%s:%d/api/status" % (host, WORKER_PORT)
    try:
        with urllib.request.urlopen(url, timeout=5) as r:
            return json.loads(r.read().decode())
    except Exception as e:
        return {"error": "%s: %s" % (type(e).__name__, e), "url": url}


PAGE = r"""<!doctype html>
<html lang="en"><head>
<meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1">
<title>System One</title>
<style>
  :root{
    --bg:#f6f7f9; --card:#fff; --ink:#1a1c20; --muted:#6b7280; --line:#e4e7ec;
    --accent:#2563eb; --auto:#15803d; --verify:#b45309; --review:#b91c1c;
    --bar:#dbe3f0; --barfill:#2563eb; --code:#f0f2f6; --codeink:#1a1c20;
    --ok:#15803d; --tag:#eef2ff; --tagink:#3730a3;
  }
  @media (prefers-color-scheme:dark){:root:not([data-theme=light]){
    --bg:#0f1115; --card:#181b20; --ink:#e7e9ee; --muted:#9aa2af; --line:#2a2f37;
    --accent:#60a5fa; --auto:#4ade80; --verify:#fbbf24; --review:#f87171;
    --bar:#242a33; --barfill:#60a5fa; --code:#11141a; --codeink:#cfd6e0;
    --ok:#4ade80; --tag:#1e2436; --tagink:#a5b4fc;
  }}
  *{box-sizing:border-box}
  body{margin:0;background:var(--bg);color:var(--ink);
    font:15px/1.5 -apple-system,BlinkMacSystemFont,"Segoe UI",Roboto,sans-serif}
  .wrap{max-width:760px;margin:0 auto;padding:24px 16px 64px}
  h1{font-size:20px;margin:0 0 2px}
  h2{font-size:16px;margin:26px 0 10px}
  .sub{color:var(--muted);font-size:13px;margin-bottom:18px}
  .sub b{color:var(--ink);font-weight:600}
  .tabs{display:inline-flex;border:1px solid var(--line);border-radius:10px;overflow:hidden;margin-bottom:18px}
  .tabs button{border:0;background:transparent;color:var(--ink);padding:9px 20px;font:inherit;font-weight:600;cursor:pointer}
  .tabs button[aria-selected=true]{background:var(--accent);color:#fff}
  .panel[hidden]{display:none}
  .card{background:var(--card);border:1px solid var(--line);border-radius:12px;padding:16px;margin-bottom:16px}
  label{display:block;font-size:12px;font-weight:600;color:var(--muted);text-transform:uppercase;letter-spacing:.04em;margin:0 0 6px}
  textarea,input[type=text]{width:100%;padding:10px;border:1px solid var(--line);border-radius:8px;
    background:transparent;color:var(--ink);font:inherit}
  textarea{resize:vertical;min-height:70px}
  .row{display:flex;gap:10px;flex-wrap:wrap;align-items:center}
  .row>div{flex:1;min-width:120px}
  .seg{display:inline-flex;border:1px solid var(--line);border-radius:8px;overflow:hidden}
  .seg button{border:0;background:transparent;color:var(--ink);padding:8px 12px;font:inherit;cursor:pointer}
  .seg button[aria-pressed=true]{background:var(--accent);color:#fff}
  .labels .lrow{display:flex;gap:8px;margin-bottom:8px}
  .labels .lrow input.name{flex:0 0 120px}
  .labels .lrow input.desc{flex:1}
  .labels .lrow button{flex:0 0 auto;border:1px solid var(--line);background:transparent;color:var(--muted);border-radius:8px;cursor:pointer;padding:0 12px}
  .addbtn{border:1px dashed var(--line);background:transparent;color:var(--accent);border-radius:8px;padding:8px 12px;cursor:pointer;font:inherit}
  .go{background:var(--accent);color:#fff;border:0;border-radius:8px;padding:12px 20px;font:inherit;font-weight:600;cursor:pointer}
  .go:disabled{opacity:.5;cursor:progress}
  .ghost{background:transparent;border:1px solid var(--line);color:var(--ink);border-radius:8px;padding:9px 16px;font:inherit;font-weight:600;cursor:pointer}
  .chk{display:flex;align-items:center;gap:8px;font-size:13px;color:var(--muted)}
  .chk input{width:auto}
  .answer{font-size:28px;font-weight:700;margin:2px 0 4px}
  .badge{display:inline-block;font-size:12px;font-weight:700;padding:3px 10px;border-radius:999px;color:#fff;text-transform:uppercase;letter-spacing:.04em}
  .b-auto{background:var(--auto)} .b-verify{background:var(--verify)} .b-review{background:var(--review)}
  .meta{color:var(--muted);font-size:13px;margin-top:8px}
  .meta b{color:var(--ink)}
  .lanes{margin-top:14px;border:1px solid var(--line);border-radius:8px;overflow:hidden}
  .lane{display:flex;align-items:center;gap:10px;padding:8px 12px;font-size:13px}
  .lane+.lane{border-top:1px solid var(--line)}
  .lane .who{flex:0 0 76px;font-weight:600;color:var(--muted);text-transform:uppercase;letter-spacing:.03em;font-size:11px}
  .lane .what{flex:1}
  .lane .ms{flex:0 0 auto;color:var(--muted);font-variant-numeric:tabular-nums}
  .bars{margin-top:14px}
  .bar{display:flex;align-items:center;gap:10px;margin:6px 0}
  .bar .bn{flex:0 0 90px;font-size:13px;overflow:hidden;text-overflow:ellipsis;white-space:nowrap}
  .bar .bt{flex:1;height:18px;background:var(--bar);border-radius:6px;overflow:hidden}
  .bar .bf{height:100%;background:var(--barfill);border-radius:6px}
  .bar .bv{flex:0 0 52px;text-align:right;font-variant-numeric:tabular-nums;font-size:13px}
  .note{margin-top:12px;padding:10px;border-radius:8px;font-size:13px;font-weight:600}
  .note-review{background:color-mix(in srgb,var(--review) 15%,transparent);color:var(--review)}
  .note-hold{background:color-mix(in srgb,var(--verify) 16%,transparent);color:var(--verify)}
  .note-ok{background:color-mix(in srgb,var(--ok) 15%,transparent);color:var(--ok)}
  .err{color:var(--review);font-weight:600;white-space:pre-wrap}
  details{margin-top:12px}summary{cursor:pointer;color:var(--muted);font-size:13px}
  pre{overflow:auto;background:var(--code);color:var(--codeink);border:1px solid var(--line);border-radius:8px;padding:12px;font-size:12.5px;line-height:1.45;margin:8px 0}
  code{background:var(--code);border-radius:4px;padding:1px 5px;font-size:13px}
  .hint{color:var(--muted);font-size:12px;margin-top:4px}
  .ep{border:1px solid var(--line);border-radius:10px;padding:14px 16px;margin-bottom:12px;background:var(--card)}
  .ep .sig{font-family:ui-monospace,SFMono-Regular,Menlo,monospace;font-size:14px;font-weight:600}
  .ep .m{display:inline-block;font-size:11px;font-weight:700;padding:2px 7px;border-radius:5px;background:var(--tag);color:var(--tagink);margin-right:8px;letter-spacing:.03em}
  .ep p{color:var(--muted);font-size:13px;margin:8px 0 4px}
  table.fields{width:100%;border-collapse:collapse;margin:6px 0 2px;font-size:13px}
  table.fields td{padding:3px 8px 3px 0;vertical-align:top}
  table.fields td.k{font-family:ui-monospace,Menlo,monospace;color:var(--accent);white-space:nowrap}
</style></head>
<body><div class="wrap">
  <h1>System One</h1>
  <div class="sub">memory answers first · the XLM worker teaches it · worker <b id="host">…</b> · learning gate S1_LEARN=<b id="learn">…</b>‰</div>

  <div class="tabs" role="tablist">
    <button role="tab" data-tab="decide" aria-selected="true">Decide</button>
    <button role="tab" data-tab="api" aria-selected="false">API</button>
  </div>

  <!-- ===================== DECIDE TAB ===================== -->
  <div class="panel" id="panel-decide" role="tabpanel">
  <div class="card">
    <label>Mode</label>
    <div class="seg" id="mode">
      <button data-m="choice" aria-pressed="true">Choice</button>
      <button data-m="yesno" aria-pressed="false">Yes / No</button>
      <button data-m="score" aria-pressed="false">Score</button>
    </div>

    <div style="margin-top:14px">
      <label>Text</label>
      <textarea id="text">Our servers crashed again, customers cannot log in, fix it within the hour.</textarea>
    </div>

    <div style="margin-top:14px" id="labelsBox">
      <label id="labelsLabel">Labels &amp; descriptions</label>
      <div class="labels" id="labels"></div>
      <button class="addbtn" id="addLabel" type="button">+ add label</button>
    </div>

    <div class="row" style="margin-top:16px">
      <div>
        <label>Risk</label>
        <div class="seg" id="risk">
          <button data-r="low" aria-pressed="false">Low</button>
          <button data-r="medium" aria-pressed="true">Medium</button>
          <button data-r="high" aria-pressed="false">High</button>
        </div>
      </div>
      <div style="flex:0 0 auto">
        <label>&nbsp;</label>
        <label class="chk"><input type="checkbox" id="train"> training mode (XLM always runs &amp; teaches)</label>
      </div>
    </div>

    <div style="margin-top:16px">
      <button class="go" id="go">Decide</button>
    </div>
  </div>
  <div id="out"></div>
  </div>

  <!-- ===================== API TAB ===================== -->
  <div class="panel" id="panel-api" role="tabpanel" hidden>
    <p class="sub">Everything the UI does is reachable over HTTP, so you can script the same
      tests from a shell. Examples use <code>http://127.0.0.1:<span class="uiport">PORT</span></code>
      for this UI and <code>$S1_WORKER_HOST:4780</code> for the worker.</p>

    <h2>This UI's test API</h2>

    <div class="ep">
      <div><span class="m">GET</span><span class="sig">/api/host</span></div>
      <p>The configured worker host, this UI's port, and the effective learning gate.</p>
      <pre>curl -s http://127.0.0.1:<span class="uiport">PORT</span>/api/host
# {"host":"&lt;worker&gt;","port":<span class="uiport">PORT</span>,"learn":70}</pre>
    </div>

    <div class="ep">
      <div><span class="m">POST</span><span class="sig">/api/decide</span></div>
      <p>Run one decision through the tutorial's <code>decide()</code>. Body:</p>
      <table class="fields">
        <tr><td class="k">mode</td><td>"choice" | "yesno" | "score"</td></tr>
        <tr><td class="k">text</td><td>the message to classify</td></tr>
        <tr><td class="k">risk</td><td>"low" | "medium" | "high" (policy row)</td></tr>
        <tr><td class="k">train</td><td>true = XLM always runs and teaches the memory</td></tr>
        <tr><td class="k">labels</td><td>[{"name","desc"}, …] — for score, name is the rank "1".."n"</td></tr>
      </table>
      <pre>curl -s http://127.0.0.1:<span class="uiport">PORT</span>/api/decide \
  -H 'Content-Type: application/json' \
  -d '{"mode":"choice","risk":"medium","train":false,
       "text":"the house is on fire",
       "labels":[{"name":"urgent","desc":"act now: an outage, an emergency"},
                 {"name":"later","desc":"can wait: a newsletter, an update"},
                 {"name":"careful","desc":"read closely: a contract, legal terms"}]}'</pre>
      <p>Response (the <code>decide()</code> dict):</p>
      <table class="fields">
        <tr><td class="k">answer</td><td>the chosen label</td></tr>
        <tr><td class="k">via</td><td>memory:known | memory:auto | memory:verified | xlm</td></tr>
        <tr><td class="k">tier</td><td>auto | verify | review</td></tr>
        <tr><td class="k">p</td><td>{label: permille} the judge's distribution</td></tr>
        <tr><td class="k">best, p_best</td><td>the memory's own pick and its confidence (permille)</td></tr>
        <tr><td class="k">coverage</td><td>[features covered, total] when known</td></tr>
        <tr><td class="k">xlm</td><td>the worker's label, when the slow lane ran</td></tr>
        <tr><td class="k">recorded</td><td>the label learned into memory, or null</td></tr>
        <tr><td class="k">held</td><td>margin (permille) if the teacher was too unsure to learn, else null</td></tr>
        <tr><td class="k">disputed</td><td>true if the verifier held it back</td></tr>
        <tr><td class="k">expected</td><td>expected rank (score mode)</td></tr>
        <tr><td class="k">ms</td><td>total latency; raw[9]=lookup ms, raw[8]=xlm ms</td></tr>
      </table>
    </div>

    <div class="ep">
      <div><span class="m">GET</span><span class="sig">/api/worker-status</span></div>
      <p>Proxies the worker's <code>/api/status</code> (no auth) so you can check health
        without leaving the UI.</p>
      <div class="row" style="margin:6px 0">
        <button class="ghost" id="pingWorker" type="button">Check worker</button>
        <span class="hint" id="pingHint"></span>
      </div>
      <pre id="workerOut" hidden></pre>
    </div>

    <h2>The XLM worker API <span class="hint">(bare-metal server, port 4780)</span></h2>

    <div class="ep">
      <div><span class="m">GET</span><span class="sig">/api/status</span></div>
      <p>Health and identity. No token required.</p>
      <pre>curl -s http://$S1_WORKER_HOST:4780/api/status | python3 -m json.tool
# service, model, model_sha256, engine_tier, cores_online, ip, ready, …</pre>
    </div>

    <div class="ep">
      <div><span class="m">POST</span><span class="sig">/api/auth</span></div>
      <p>Exchange the credentials for a session token.</p>
      <pre>TOKEN=$(curl -s -X POST http://$S1_WORKER_HOST:4780/api/auth \
          -d '{"username":"&lt;user&gt;","password":"&lt;pass&gt;"}' \
        | python3 -c 'import sys,json; print(json.load(sys.stdin)["token"])')</pre>
      <p class="hint">Credentials live in <code>~/.config/maned/xlm.env</code> (mode 600); never put them in a repo or a URL.</p>
    </div>

    <div class="ep">
      <div><span class="m">POST</span><span class="sig">/api/embed</span></div>
      <p>XLM-R-large mean-pool embedding for up to 512 token ids (<code>&lt;s&gt;</code>=0,
        <code>&lt;/s&gt;</code>=2). The token goes in the <code>X-Caramel-Token</code> header.</p>
      <pre>curl -s -X POST http://$S1_WORKER_HOST:4780/api/embed \
     -H "X-Caramel-Token: $TOKEN" \
     -d '{"ids":[0,35378,8999,2]}' | python3 -m json.tool
# { "vector":[1024 ints], "scale":n (value = int*10^-n),
#   "tokens":k, "model_sha256":"…", "sha256":"…" }</pre>
      <p class="hint">The integers are exact: two workers given the same ids return the same bytes.
        The tutorial's <code>02_*.mnd</code> programs call this through maned-run's <code>device{}</code> block.</p>
    </div>
  </div>

</div>
<script>
const DEFAULTS = {
  choice: [
    ["urgent","This message needs action right now: an outage, an emergency, a deadline today."],
    ["later","This message can wait: an update, a newsletter, something for next week."],
    ["careful","This message needs care before acting: a contract, a legal clause, a payment detail."],
  ],
  yesno: [
    ["yes","This message asks for money to be sent"],
    ["no","It is not the case that this message asks for money to be sent"],
  ],
  score: [
    ["1","no action"],["2","look this week"],["3","act today"],
  ],
};
const EXAMPLE = {
  choice:"Our servers crashed again, customers cannot log in, fix it within the hour.",
  yesno:"Please wire the deposit today.",
  score:"The kitchen will be repainted next spring.",
};
let mode = "choice";
const $ = s => document.querySelector(s);
const $$ = s => [...document.querySelectorAll(s)];

// ---- tabs
$$('.tabs button').forEach(b=>b.onclick=()=>{
  $$('.tabs button').forEach(x=>x.setAttribute('aria-selected', x===b));
  $('#panel-decide').hidden = b.dataset.tab!=='decide';
  $('#panel-api').hidden   = b.dataset.tab!=='api';
});

function renderLabels(){
  const box = $("#labels"); box.innerHTML = "";
  const rows = DEFAULTS[mode];
  const fixed = (mode!=="choice");
  $("#labelsLabel").textContent = mode==="yesno" ? "Statement (yes) / negation (no)"
    : mode==="score" ? "Ranks 1..3 and what each means" : "Labels & descriptions";
  $("#addLabel").style.display = fixed ? "none" : "";
  rows.forEach(([n,d])=>{
    const r = document.createElement("div"); r.className="lrow";
    r.innerHTML = `<input class="name" type="text" value="${n.replace(/"/g,'&quot;')}" ${fixed?'readonly':''} placeholder="label">
      <input class="desc" type="text" value="${d.replace(/"/g,'&quot;')}" placeholder="description">
      ${fixed?'':'<button type="button" class="rm">×</button>'}`;
    box.appendChild(r);
  });
  box.querySelectorAll(".rm").forEach(b=>b.onclick=()=>b.parentElement.remove());
}
$("#addLabel").onclick=()=>{
  const r=document.createElement("div"); r.className="lrow";
  r.innerHTML=`<input class="name" type="text" placeholder="label">
    <input class="desc" type="text" placeholder="description">
    <button type="button" class="rm">×</button>`;
  r.querySelector(".rm").onclick=()=>r.remove();
  $("#labels").appendChild(r);
};
$("#mode").querySelectorAll("button").forEach(b=>b.onclick=()=>{
  mode=b.dataset.m;
  $("#mode").querySelectorAll("button").forEach(x=>x.setAttribute("aria-pressed", x===b));
  $("#text").value = EXAMPLE[mode];
  renderLabels();
});
$("#risk").querySelectorAll("button").forEach(b=>b.onclick=()=>
  $("#risk").querySelectorAll("button").forEach(x=>x.setAttribute("aria-pressed", x===b)));

function tierClass(t){return t==="auto"?"b-auto":t==="verify"?"b-verify":"b-review";}
function esc(s){return String(s).replace(/[&<>]/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;'}[c]));}

function render(d){
  if(d.error){ $("#out").innerHTML = `<div class="card"><div class="err">⚠ ${esc(d.error)}</div></div>`; return; }
  const pct = v => (v/10).toFixed(1)+"%";
  const raw = d.raw||[];               // [how,best,p_best,tier,known,p_xlm,disputed,t_answer,t_xlm,t_lookup]
  const tLookup = raw[9], tXlm = raw[8];
  let bars = Object.entries(d.p).map(([n,v])=>`
    <div class="bar"><div class="bn" title="${esc(n)}">${esc(n)}</div>
      <div class="bt"><div class="bf" style="width:${Math.min(100,v/10)}%"></div></div>
      <div class="bv">${pct(v)}</div></div>`).join("");
  let extra = "";
  if(d.mode==="yesno") extra = `<div class="meta">P(yes) = <b>${pct(d.p.yes||0)}</b></div>`;
  if(d.mode==="score") extra = `<div class="meta">expected rank = <b>${(d.expected).toFixed(2)}</b></div>`;

  // the two lanes: what the memory's judge saw, and what the worker said (if it ran)
  const cov = d.known ? ` · known, coverage ${d.coverage[0]}/${d.coverage[1]}` : "";
  let lanes = `<div class="lane"><div class="who">memory</div>
      <div class="what">judge → <b>${esc(d.best)}</b> at ${pct(d.p_best)}${cov}</div>
      <div class="ms">${tLookup!=null?tLookup+" ms":""}</div></div>`;
  if(d.xlm) lanes += `<div class="lane"><div class="who">worker</div>
      <div class="what">XLM → <b>${esc(d.xlm)}</b></div>
      <div class="ms">${tXlm!=null?tXlm+" ms":""}</div></div>`;

  let note = "";
  if(d.disputed) note = `<div class="note note-review">⚠ DISPUTED — the XLM contradicted a confident memory; held for review (work/review.tsv), not learned.</div>`;
  else if(d.held!=null) note = `<div class="note note-hold">⏸ HELD — the teacher's margin (${d.held}‰) is below the S1_LEARN gate; answered but not learned (work/pending.tsv). Resolve later with <code>decide.py --resolve</code>.</div>`;
  else if(d.recorded) note = `<div class="note note-ok">✓ memory learned this as <b>${esc(d.recorded)}</b></div>`;

  $("#out").innerHTML = `<div class="card">
    <div class="answer">${esc(d.answer)}</div>
    <span class="badge ${tierClass(d.tier)}">${d.tier}</span>
    <span class="meta">via ${esc(d.via)} · ${d.ms} ms</span>
    ${extra}
    <div class="lanes">${lanes}</div>
    <div class="bars">${bars}</div>
    ${note}
    <details><summary>raw response</summary><pre>${esc(JSON.stringify(d,null,2))}</pre></details>
  </div>`;
}

$("#go").onclick=async()=>{
  const labels=[...document.querySelectorAll("#labels .lrow")].map(r=>({
    name:r.querySelector(".name").value.trim(),
    desc:r.querySelector(".desc").value.trim(),
  })).filter(l=>l.name);
  const body={ mode,
    text:$("#text").value,
    risk:[...$("#risk").querySelectorAll("button")].find(b=>b.getAttribute("aria-pressed")==="true").dataset.r,
    train:$("#train").checked, labels };
  const btn=$("#go"); btn.disabled=true; btn.textContent="Deciding…";
  try{
    const r=await fetch("/api/decide",{method:"POST",headers:{"Content-Type":"application/json"},body:JSON.stringify(body)});
    render(await r.json());
  }catch(e){ render({error:String(e)}); }
  btn.disabled=false; btn.textContent="Decide";
};

// ---- API tab: live worker health check
$("#pingWorker").onclick=async()=>{
  const btn=$("#pingWorker"), hint=$("#pingHint"), out=$("#workerOut");
  btn.disabled=true; hint.textContent="checking…";
  try{
    const r=await fetch("/api/worker-status");
    const j=await r.json();
    out.hidden=false; out.textContent=JSON.stringify(j,null,2);
    hint.textContent = j.error ? "unreachable" : (j.ready? "ready · "+(j.engine_tier||"") : (j.status_line||"responded"));
  }catch(e){ out.hidden=false; out.textContent=String(e); hint.textContent="error"; }
  btn.disabled=false;
};

// ---- header: host, port, learning gate (fills the curl examples too)
fetch("/api/host").then(r=>r.json()).then(j=>{
  $("#host").textContent = j.host || "(unset)";
  $("#learn").textContent = j.learn;
  $$(".uiport").forEach(e=>e.textContent = j.port);
});
renderLabels();
</script>
</body></html>"""


class H(BaseHTTPRequestHandler):
    def _send(self, code, body, ctype="application/json"):
        b = body if isinstance(body, bytes) else body.encode()
        self.send_response(code)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(b)))
        self.end_headers()
        self.wfile.write(b)

    def log_message(self, *a):
        pass

    def do_GET(self):
        if self.path == "/" or self.path.startswith("/index"):
            self._send(200, PAGE, "text/html; charset=utf-8")
        elif self.path == "/api/host":
            self._send(200, json.dumps({"host": worker_host() or "(unset)", "port": PORT, "learn": effective_learn()}))
        elif self.path == "/api/worker-status":
            self._send(200, json.dumps(worker_status()))
        else:
            self._send(404, json.dumps({"error": "not found"}))

    def do_POST(self):
        if self.path != "/api/decide":
            self._send(404, json.dumps({"error": "not found"}))
            return
        try:
            n = int(self.headers.get("Content-Length", 0))
            req = json.loads(self.rfile.read(n) or b"{}")
        except Exception as e:
            self._send(400, json.dumps({"error": "bad request: %s" % e}))
            return
        mode = req.get("mode", "choice")
        text = (req.get("text") or "").strip()
        risk = req.get("risk", "medium")
        train = bool(req.get("train"))
        labels = {l["name"]: (l.get("desc") or l["name"]) for l in req.get("labels", []) if l.get("name")}
        if not text or not labels:
            self._send(400, json.dumps({"error": "need text and at least one label"}))
            return
        ordinal = {n: int(n) for n in labels} if mode == "score" else None
        try:
            with LOCK:
                d = engine.decide(text, labels, risk=risk, ordinal=ordinal, train=train)
            d["mode"] = mode
            self._send(200, json.dumps(d))
        except SystemExit as e:  # decide.py uses sys.exit on a failed maned-run (e.g. worker down)
            self._send(200, json.dumps({"error": str(e.code)}))
        except Exception as e:
            self._send(200, json.dumps({"error": "%s: %s" % (type(e).__name__, e)}))


if __name__ == "__main__":
    host = worker_host() or "(unset)"
    print("System One UI  ->  http://127.0.0.1:%d" % PORT)
    print("worker: %s  (slow lane needs it reachable)  ·  S1_LEARN=%d" % (host, effective_learn()))
    ThreadingHTTPServer(("127.0.0.1", PORT), H).serve_forever()
