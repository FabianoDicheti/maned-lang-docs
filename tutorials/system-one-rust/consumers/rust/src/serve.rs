// The --serve web UI for the Rust consumer: the same two-tab page as
// consumers/python/test_ui.py (Decide + API), served from the standard library
// alone (no web framework, no serde). Each request calls the in-process
// decide(); the accept loop is single-threaded, so requests serialize like the
// Python UI's lock. Start it with:  cargo run -- --serve [port]
use crate::{Decision, SystemOne, DEFAULT_LEARN, TIERS};
use std::collections::BTreeMap;
use std::io::{BufRead, BufReader, Read, Write};
use std::net::{TcpListener, TcpStream};
use std::time::Duration;

// ----------------------------- a tiny JSON reader -----------------------------
#[allow(dead_code)]   // Num's value is parsed for well-formedness but our request schema never reads it
enum Json { Null, Bool(bool), Num(f64), Str(String), Arr(Vec<Json>), Obj(Vec<(String, Json)>) }

impl Json {
    fn get(&self, k: &str) -> Option<&Json> {
        if let Json::Obj(v) = self { v.iter().find(|(kk, _)| kk == k).map(|(_, vv)| vv) } else { None }
    }
    fn as_str(&self) -> Option<&str> { if let Json::Str(s) = self { Some(s) } else { None } }
    fn as_bool(&self) -> bool { matches!(self, Json::Bool(true)) }
    fn as_arr(&self) -> &[Json] { if let Json::Arr(v) = self { v } else { &[] } }
}

struct P<'a> { b: &'a [u8], i: usize }

impl<'a> P<'a> {
    fn ws(&mut self) { while self.i < self.b.len() && (self.b[self.i] as char).is_ascii_whitespace() { self.i += 1 } }
    fn lit(&mut self, s: &str) -> Option<()> {
        if self.b[self.i..].starts_with(s.as_bytes()) { self.i += s.len(); Some(()) } else { None }
    }
    fn val(&mut self) -> Option<Json> {
        self.ws();
        match *self.b.get(self.i)? {
            b'{' => self.obj(),
            b'[' => self.arr(),
            b'"' => self.strv().map(Json::Str),
            b't' => { self.lit("true")?; Some(Json::Bool(true)) }
            b'f' => { self.lit("false")?; Some(Json::Bool(false)) }
            b'n' => { self.lit("null")?; Some(Json::Null) }
            _ => self.num(),
        }
    }
    fn strv(&mut self) -> Option<String> {
        self.i += 1;                 // opening quote
        let mut out: Vec<u8> = Vec::new();
        while self.i < self.b.len() {
            let c = self.b[self.i]; self.i += 1;
            match c {
                b'"' => return String::from_utf8(out).ok(),
                b'\\' => {
                    let e = *self.b.get(self.i)?; self.i += 1;
                    match e {
                        b'"' => out.push(b'"'), b'\\' => out.push(b'\\'), b'/' => out.push(b'/'),
                        b'n' => out.push(b'\n'), b't' => out.push(b'\t'), b'r' => out.push(b'\r'),
                        b'b' => out.push(8), b'f' => out.push(12),
                        b'u' => {
                            let hex = std::str::from_utf8(self.b.get(self.i..self.i + 4)?).ok()?;
                            let n = u32::from_str_radix(hex, 16).ok()?; self.i += 4;
                            let ch = char::from_u32(n).unwrap_or('\u{fffd}');
                            let mut buf = [0u8; 4];
                            out.extend_from_slice(ch.encode_utf8(&mut buf).as_bytes());
                        }
                        _ => return None,
                    }
                }
                _ => out.push(c),        // raw UTF-8 bytes pass through unchanged
            }
        }
        None
    }
    fn num(&mut self) -> Option<Json> {
        let start = self.i;
        while self.i < self.b.len() && matches!(self.b[self.i], b'0'..=b'9' | b'-' | b'+' | b'.' | b'e' | b'E') { self.i += 1 }
        std::str::from_utf8(&self.b[start..self.i]).ok()?.parse().ok().map(Json::Num)
    }
    fn arr(&mut self) -> Option<Json> {
        self.i += 1; let mut v = Vec::new(); self.ws();
        if self.b.get(self.i) == Some(&b']') { self.i += 1; return Some(Json::Arr(v)); }
        loop {
            v.push(self.val()?); self.ws();
            match self.b.get(self.i) {
                Some(b',') => { self.i += 1 }
                Some(b']') => { self.i += 1; return Some(Json::Arr(v)); }
                _ => return None,
            }
        }
    }
    fn obj(&mut self) -> Option<Json> {
        self.i += 1; let mut v = Vec::new(); self.ws();
        if self.b.get(self.i) == Some(&b'}') { self.i += 1; return Some(Json::Obj(v)); }
        loop {
            self.ws();
            if self.b.get(self.i) != Some(&b'"') { return None; }
            let k = self.strv()?; self.ws();
            if self.b.get(self.i) != Some(&b':') { return None; }
            self.i += 1;
            let val = self.val()?; v.push((k, val)); self.ws();
            match self.b.get(self.i) {
                Some(b',') => { self.i += 1 }
                Some(b'}') => { self.i += 1; return Some(Json::Obj(v)); }
                _ => return None,
            }
        }
    }
}

fn parse(s: &str) -> Option<Json> { P { b: s.as_bytes(), i: 0 }.val() }

// ----------------------------- JSON writing -----------------------------
fn esc(s: &str) -> String {
    let mut o = String::with_capacity(s.len() + 2);
    for c in s.chars() {
        match c {
            '"' => o.push_str("\\\""), '\\' => o.push_str("\\\\"),
            '\n' => o.push_str("\\n"), '\r' => o.push_str("\\r"), '\t' => o.push_str("\\t"),
            c if (c as u32) < 0x20 => o.push_str(&format!("\\u{:04x}", c as u32)),
            c => o.push(c),
        }
    }
    o
}

fn decision_json(d: &Decision, mode: &str) -> String {
    let p: String = d.p.iter().map(|(k, v)| format!("\"{}\":{}", esc(k), v)).collect::<Vec<_>>().join(",");
    let opt = |o: &Option<String>| match o { Some(s) => format!("\"{}\"", esc(s)), None => "null".into() };
    let held = match d.held { Some(h) => h.to_string(), None => "null".into() };
    format!(
        "{{\"answer\":\"{}\",\"via\":\"{}\",\"tier\":\"{}\",\"known\":{},\"best\":\"{}\",\"p_best\":{},\
          \"coverage\":[{},{}],\"p\":{{{}}},\"expected\":{:.3},\"xlm\":{},\"recorded\":{},\
          \"disputed\":{},\"held\":{},\"how\":{},\"p_xlm\":{},\"t_lookup\":{},\"t_xlm\":{},\"ms\":{},\"mode\":\"{}\"}}",
        esc(&d.answer), esc(&d.via), TIERS[d.tier], d.known, esc(&d.best), d.p_best,
        d.coverage.0, d.coverage.1, p, d.expected, opt(&d.xlm), opt(&d.recorded),
        d.disputed, held, d.how, d.p_xlm, d.t_lookup, d.t_xlm, d.ms, esc(mode)
    )
}

// GET the worker's /api/status (no auth) over a raw HTTP/1.0 request, no deps
fn worker_status(host: &str) -> String {
    if host.is_empty() { return "{\"error\":\"S1_WORKER_HOST is not set (source ~/.config/maned/xlm.env)\"}".into(); }
    match TcpStream::connect((host, 4780u16)) {
        Ok(mut s) => {
            let _ = s.set_read_timeout(Some(Duration::from_secs(5)));
            let req = format!("GET /api/status HTTP/1.0\r\nHost: {host}\r\nConnection: close\r\n\r\n");
            if s.write_all(req.as_bytes()).is_err() { return "{\"error\":\"write to worker failed\"}".into(); }
            let mut buf = Vec::new();
            let _ = s.read_to_end(&mut buf);
            let text = String::from_utf8_lossy(&buf);
            match text.find("\r\n\r\n") {
                Some(i) => text[i + 4..].trim().to_string(),
                None => "{\"error\":\"no response body from worker\"}".into(),
            }
        }
        Err(e) => format!("{{\"error\":\"{}\"}}", esc(&e.to_string())),
    }
}

// ----------------------------- the HTTP server -----------------------------
fn learn_knob() -> i64 {
    std::env::var("S1_LEARN").ok().and_then(|x| x.parse().ok()).unwrap_or(DEFAULT_LEARN)
}

fn handle_decide(body: &[u8], s1: &mut SystemOne) -> String {
    let req = match std::str::from_utf8(body).ok().and_then(parse) { Some(j) => j, None => return "{\"error\":\"bad JSON\"}".into() };
    let mode = req.get("mode").and_then(|j| j.as_str()).unwrap_or("choice").to_string();
    let text = req.get("text").and_then(|j| j.as_str()).unwrap_or("").trim().to_string();
    let risk = req.get("risk").and_then(|j| j.as_str()).unwrap_or("medium").to_string();
    let train = req.get("train").map(|j| j.as_bool()).unwrap_or(false);
    let mut labels: Vec<(String, String)> = Vec::new();
    if let Some(arr) = req.get("labels") {
        for l in arr.as_arr() {
            if let Some(n) = l.get("name").and_then(|j| j.as_str()) {
                if !n.is_empty() {
                    let d = l.get("desc").and_then(|j| j.as_str()).filter(|s| !s.is_empty()).unwrap_or(n);
                    labels.push((n.to_string(), d.to_string()));
                }
            }
        }
    }
    if text.is_empty() || labels.is_empty() { return "{\"error\":\"need text and at least one label\"}".into(); }
    let ordinal: BTreeMap<String, i64> = if mode == "score" {
        labels.iter().map(|(n, _)| (n.clone(), n.parse().unwrap_or(0))).collect()
    } else { BTreeMap::new() };
    let d = s1.decide(&text, &labels, &risk, &ordinal, train);
    decision_json(&d, &mode)
}

fn respond(mut s: TcpStream, code: u16, ctype: &str, body: &str) {
    let reason = match code { 200 => "OK", 404 => "Not Found", 400 => "Bad Request", _ => "Error" };
    let head = format!("HTTP/1.1 {code} {reason}\r\nContent-Type: {ctype}\r\nContent-Length: {}\r\nConnection: close\r\n\r\n", body.len());
    let _ = s.write_all(head.as_bytes());
    let _ = s.write_all(body.as_bytes());
    let _ = s.flush();
}

fn handle(stream: TcpStream, s1: &mut SystemOne, host: &str, port: u16) {
    let writer = match stream.try_clone() { Ok(w) => w, Err(_) => return };
    let mut reader = BufReader::new(stream);
    let mut line = String::new();
    if reader.read_line(&mut line).unwrap_or(0) == 0 { return; }
    let mut it = line.split_whitespace();
    let method = it.next().unwrap_or("").to_string();
    let path = it.next().unwrap_or("").to_string();
    let mut clen = 0usize;
    loop {
        let mut h = String::new();
        if reader.read_line(&mut h).unwrap_or(0) == 0 { break; }
        if h == "\r\n" || h == "\n" { break; }
        if let Some(v) = h.to_ascii_lowercase().strip_prefix("content-length:") { clen = v.trim().parse().unwrap_or(0); }
    }
    let mut body = vec![0u8; clen];
    if clen > 0 && reader.read_exact(&mut body).is_err() { return; }

    let (code, ctype, out): (u16, &str, String) = match (method.as_str(), path.as_str()) {
        ("GET", "/") | ("GET", "/index.html") => (200, "text/html; charset=utf-8", PAGE.to_string()),
        ("GET", "/api/host") => (200, "application/json",
            format!("{{\"host\":\"{}\",\"port\":{},\"learn\":{}}}",
                if host.is_empty() { "(unset)".to_string() } else { esc(host) }, port, learn_knob())),
        ("GET", "/api/worker-status") => (200, "application/json", worker_status(host)),
        ("POST", "/api/decide") => (200, "application/json", handle_decide(&body, s1)),
        _ => (404, "application/json", "{\"error\":\"not found\"}".into()),
    };
    respond(writer, code, ctype, &out);
}

pub fn run(mut s1: SystemOne, host: String, port: u16) {
    let listener = match TcpListener::bind(("127.0.0.1", port)) {
        Ok(l) => l,
        Err(e) => { eprintln!("cannot bind 127.0.0.1:{port}: {e}"); std::process::exit(1); }
    };
    println!("System One (Rust) UI  ->  http://127.0.0.1:{port}");
    println!("worker: {}   S1_LEARN={}", if host.is_empty() { "(unset)".to_string() } else { host.clone() }, learn_knob());
    println!("note: a failed maned-run (e.g. worker unreachable on a novel text) ends the server, like the CLI");
    for stream in listener.incoming() {
        if let Ok(s) = stream { handle(s, &mut s1, &host, port); }
    }
}

// The page: same structure as the Python test UI. The JS reads the decide()
// fields this server emits directly (t_lookup / t_xlm, no raw[] array).
const PAGE: &str = r###"<!doctype html>
<html lang="en"><head>
<meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1">
<title>System One (Rust)</title>
<style>
  :root{--bg:#f6f7f9;--card:#fff;--ink:#1a1c20;--muted:#6b7280;--line:#e4e7ec;--accent:#b7410e;
    --auto:#15803d;--verify:#b45309;--review:#b91c1c;--bar:#ead9cf;--barfill:#b7410e;--code:#f0f2f6;--ok:#15803d;--tag:#f6e6dc;--tagink:#8a3208}
  @media (prefers-color-scheme:dark){:root:not([data-theme=light]){--bg:#0f1115;--card:#181b20;--ink:#e7e9ee;--muted:#9aa2af;--line:#2a2f37;
    --accent:#f0845a;--auto:#4ade80;--verify:#fbbf24;--review:#f87171;--bar:#2a211c;--barfill:#f0845a;--code:#11141a;--ok:#4ade80;--tag:#2a211c;--tagink:#f0a07a}}
  *{box-sizing:border-box} body{margin:0;background:var(--bg);color:var(--ink);font:15px/1.5 -apple-system,BlinkMacSystemFont,"Segoe UI",Roboto,sans-serif}
  .wrap{max-width:760px;margin:0 auto;padding:24px 16px 64px} h1{font-size:20px;margin:0 0 2px} h2{font-size:16px;margin:26px 0 10px}
  .sub{color:var(--muted);font-size:13px;margin-bottom:18px} .sub b{color:var(--ink);font-weight:600}
  .tabs{display:inline-flex;border:1px solid var(--line);border-radius:10px;overflow:hidden;margin-bottom:18px}
  .tabs button{border:0;background:transparent;color:var(--ink);padding:9px 20px;font:inherit;font-weight:600;cursor:pointer}
  .tabs button[aria-selected=true]{background:var(--accent);color:#fff} .panel[hidden]{display:none}
  .card{background:var(--card);border:1px solid var(--line);border-radius:12px;padding:16px;margin-bottom:16px}
  label{display:block;font-size:12px;font-weight:600;color:var(--muted);text-transform:uppercase;letter-spacing:.04em;margin:0 0 6px}
  textarea,input[type=text]{width:100%;padding:10px;border:1px solid var(--line);border-radius:8px;background:transparent;color:var(--ink);font:inherit}
  textarea{resize:vertical;min-height:70px}
  .seg{display:inline-flex;border:1px solid var(--line);border-radius:8px;overflow:hidden}
  .seg button{border:0;background:transparent;color:var(--ink);padding:8px 12px;font:inherit;cursor:pointer}
  .seg button[aria-pressed=true]{background:var(--accent);color:#fff}
  .labels .lrow{display:flex;gap:8px;margin-bottom:8px} .labels .lrow input.name{flex:0 0 120px} .labels .lrow input.desc{flex:1}
  .labels .lrow button{flex:0 0 auto;border:1px solid var(--line);background:transparent;color:var(--muted);border-radius:8px;cursor:pointer;padding:0 12px}
  .addbtn{border:1px dashed var(--line);background:transparent;color:var(--accent);border-radius:8px;padding:8px 12px;cursor:pointer;font:inherit}
  .row{display:flex;gap:10px;flex-wrap:wrap;align-items:center}
  .go{background:var(--accent);color:#fff;border:0;border-radius:8px;padding:12px 20px;font:inherit;font-weight:600;cursor:pointer} .go:disabled{opacity:.5;cursor:progress}
  .ghost{background:transparent;border:1px solid var(--line);color:var(--ink);border-radius:8px;padding:9px 16px;font:inherit;font-weight:600;cursor:pointer}
  .chk{display:flex;align-items:center;gap:8px;font-size:13px;color:var(--muted)} .chk input{width:auto}
  .answer{font-size:28px;font-weight:700;margin:2px 0 4px}
  .badge{display:inline-block;font-size:12px;font-weight:700;padding:3px 10px;border-radius:999px;color:#fff;text-transform:uppercase;letter-spacing:.04em}
  .b-auto{background:var(--auto)} .b-verify{background:var(--verify)} .b-review{background:var(--review)}
  .meta{color:var(--muted);font-size:13px;margin-top:8px} .meta b{color:var(--ink)}
  .lanes{margin-top:14px;border:1px solid var(--line);border-radius:8px;overflow:hidden}
  .lane{display:flex;align-items:center;gap:10px;padding:8px 12px;font-size:13px} .lane+.lane{border-top:1px solid var(--line)}
  .lane .who{flex:0 0 76px;font-weight:600;color:var(--muted);text-transform:uppercase;letter-spacing:.03em;font-size:11px}
  .lane .what{flex:1} .lane .ms{flex:0 0 auto;color:var(--muted);font-variant-numeric:tabular-nums}
  .bars{margin-top:14px} .bar{display:flex;align-items:center;gap:10px;margin:6px 0}
  .bar .bn{flex:0 0 90px;font-size:13px;overflow:hidden;text-overflow:ellipsis;white-space:nowrap}
  .bar .bt{flex:1;height:18px;background:var(--bar);border-radius:6px;overflow:hidden} .bar .bf{height:100%;background:var(--barfill);border-radius:6px}
  .bar .bv{flex:0 0 52px;text-align:right;font-variant-numeric:tabular-nums;font-size:13px}
  .note{margin-top:12px;padding:10px;border-radius:8px;font-size:13px;font-weight:600}
  .note-review{background:color-mix(in srgb,var(--review) 15%,transparent);color:var(--review)}
  .note-hold{background:color-mix(in srgb,var(--verify) 16%,transparent);color:var(--verify)}
  .note-ok{background:color-mix(in srgb,var(--ok) 15%,transparent);color:var(--ok)}
  .err{color:var(--review);font-weight:600;white-space:pre-wrap}
  details{margin-top:12px}summary{cursor:pointer;color:var(--muted);font-size:13px}
  pre{overflow:auto;background:var(--code);border:1px solid var(--line);border-radius:8px;padding:12px;font-size:12.5px;line-height:1.45;margin:8px 0}
  code{background:var(--code);border-radius:4px;padding:1px 5px;font-size:13px}
  .hint{color:var(--muted);font-size:12px;margin-top:4px}
  .ep{border:1px solid var(--line);border-radius:10px;padding:14px 16px;margin-bottom:12px;background:var(--card)}
  .ep .sig{font-family:ui-monospace,Menlo,monospace;font-size:14px;font-weight:600}
  .ep .m{display:inline-block;font-size:11px;font-weight:700;padding:2px 7px;border-radius:5px;background:var(--tag);color:var(--tagink);margin-right:8px}
  .ep p{color:var(--muted);font-size:13px;margin:8px 0 4px}
</style></head>
<body><div class="wrap">
  <h1>System One <span style="color:var(--accent)">· Rust</span></h1>
  <div class="sub">memory answers first · the XLM worker teaches it · worker <b id="host">…</b> · gate S1_LEARN=<b id="learn">…</b>‰ · served by the <code>maned</code> crate</div>
  <div class="tabs" role="tablist">
    <button role="tab" data-tab="decide" aria-selected="true">Decide</button>
    <button role="tab" data-tab="api" aria-selected="false">API</button>
  </div>

  <div class="panel" id="panel-decide" role="tabpanel">
  <div class="card">
    <label>Mode</label>
    <div class="seg" id="mode">
      <button data-m="choice" aria-pressed="true">Choice</button>
      <button data-m="yesno" aria-pressed="false">Yes / No</button>
      <button data-m="score" aria-pressed="false">Score</button>
    </div>
    <div style="margin-top:14px"><label>Text</label>
      <textarea id="text">Our servers crashed again, customers cannot log in, fix it within the hour.</textarea></div>
    <div style="margin-top:14px"><label id="labelsLabel">Labels &amp; descriptions</label>
      <div class="labels" id="labels"></div>
      <button class="addbtn" id="addLabel" type="button">+ add label</button></div>
    <div class="row" style="margin-top:16px">
      <div><label>Risk</label><div class="seg" id="risk">
        <button data-r="low" aria-pressed="false">Low</button>
        <button data-r="medium" aria-pressed="true">Medium</button>
        <button data-r="high" aria-pressed="false">High</button></div></div>
      <div style="flex:0 0 auto"><label>&nbsp;</label>
        <label class="chk"><input type="checkbox" id="train"> training mode (XLM always runs &amp; teaches)</label></div>
    </div>
    <div style="margin-top:16px"><button class="go" id="go">Decide</button></div>
  </div>
  <div id="out"></div>
  </div>

  <div class="panel" id="panel-api" role="tabpanel" hidden>
    <p class="sub">The same HTTP endpoints as the Python UI, served from Rust's standard library.
      Examples use <code>http://127.0.0.1:<span class="uiport">PORT</span></code> and <code>$S1_WORKER_HOST:4780</code>.</p>
    <h2>This UI's test API</h2>
    <div class="ep"><div><span class="m">GET</span><span class="sig">/api/host</span></div>
      <p>Worker host, this UI's port, and the learning gate.</p>
      <pre>curl -s http://127.0.0.1:<span class="uiport">PORT</span>/api/host</pre></div>
    <div class="ep"><div><span class="m">POST</span><span class="sig">/api/decide</span></div>
      <p>Body: <code>{mode, text, risk, train, labels:[{name,desc}]}</code>. Returns the decide() result
        (answer, via, tier, p{}, best, p_best, coverage, xlm, recorded, held, disputed, t_lookup, t_xlm, ms).</p>
      <pre>curl -s http://127.0.0.1:<span class="uiport">PORT</span>/api/decide -H 'Content-Type: application/json' \
  -d '{"mode":"choice","risk":"medium","train":false,"text":"the house is on fire",
       "labels":[{"name":"urgent","desc":"act now: an outage or emergency"},
                 {"name":"later","desc":"can wait: a newsletter"},
                 {"name":"careful","desc":"read closely: a contract"}]}'</pre></div>
    <div class="ep"><div><span class="m">GET</span><span class="sig">/api/worker-status</span></div>
      <p>Proxies the worker's <code>/api/status</code> (no auth).</p>
      <div class="row" style="margin:6px 0"><button class="ghost" id="pingWorker" type="button">Check worker</button>
        <span class="hint" id="pingHint"></span></div>
      <pre id="workerOut" hidden></pre></div>
    <h2>The XLM worker API <span class="hint">(bare-metal server, port 4780)</span></h2>
    <div class="ep"><div><span class="m">GET</span><span class="sig">/api/status</span></div>
      <pre>curl -s http://$S1_WORKER_HOST:4780/api/status | python3 -m json.tool</pre></div>
    <div class="ep"><div><span class="m">POST</span><span class="sig">/api/auth</span> → <span class="m">POST</span><span class="sig">/api/embed</span></div>
      <pre>TOKEN=$(curl -s -X POST http://$S1_WORKER_HOST:4780/api/auth \
          -d '{"username":"&lt;user&gt;","password":"&lt;pass&gt;"}' \
        | python3 -c 'import sys,json;print(json.load(sys.stdin)["token"])')
curl -s -X POST http://$S1_WORKER_HOST:4780/api/embed -H "X-Caramel-Token: $TOKEN" \
     -d '{"ids":[0,35378,8999,2]}' | python3 -m json.tool
# -> { "vector":[1024 ints], "scale":n, "tokens":k, "model_sha256":"…", "sha256":"…" }</pre>
      <p class="hint">Credentials live in <code>~/.config/maned/xlm.env</code> (mode 600); never put them in a repo or a URL.</p></div>
  </div>
</div>
<script>
const DEFAULTS={choice:[["urgent","This message needs action right now: an outage, an emergency, a deadline today."],
  ["later","This message can wait: an update, a newsletter, something for next week."],
  ["careful","This message needs care before acting: a contract, a legal clause, a payment detail."]],
  yesno:[["yes","This message asks for money to be sent"],["no","It is not the case that this message asks for money to be sent"]],
  score:[["1","no action"],["2","look this week"],["3","act today"]]};
const EXAMPLE={choice:"Our servers crashed again, customers cannot log in, fix it within the hour.",
  yesno:"Please wire the deposit today.",score:"The kitchen will be repainted next spring."};
let mode="choice"; const $=s=>document.querySelector(s); const $$=s=>[...document.querySelectorAll(s)];
$$('.tabs button').forEach(b=>b.onclick=()=>{$$('.tabs button').forEach(x=>x.setAttribute('aria-selected',x===b));
  $('#panel-decide').hidden=b.dataset.tab!=='decide'; $('#panel-api').hidden=b.dataset.tab!=='api';});
function renderLabels(){const box=$("#labels");box.innerHTML="";const rows=DEFAULTS[mode];const fixed=(mode!=="choice");
  $("#labelsLabel").textContent=mode==="yesno"?"Statement (yes) / negation (no)":mode==="score"?"Ranks 1..3 and what each means":"Labels & descriptions";
  $("#addLabel").style.display=fixed?"none":"";
  rows.forEach(([n,d])=>{const r=document.createElement("div");r.className="lrow";
    r.innerHTML=`<input class="name" type="text" value="${n.replace(/"/g,'&quot;')}" ${fixed?'readonly':''} placeholder="label">
      <input class="desc" type="text" value="${d.replace(/"/g,'&quot;')}" placeholder="description">${fixed?'':'<button type="button" class="rm">×</button>'}`;
    box.appendChild(r);}); box.querySelectorAll(".rm").forEach(b=>b.onclick=()=>b.parentElement.remove());}
$("#addLabel").onclick=()=>{const r=document.createElement("div");r.className="lrow";
  r.innerHTML=`<input class="name" type="text" placeholder="label"><input class="desc" type="text" placeholder="description"><button type="button" class="rm">×</button>`;
  r.querySelector(".rm").onclick=()=>r.remove();$("#labels").appendChild(r);};
$("#mode").querySelectorAll("button").forEach(b=>b.onclick=()=>{mode=b.dataset.m;
  $("#mode").querySelectorAll("button").forEach(x=>x.setAttribute("aria-pressed",x===b));$("#text").value=EXAMPLE[mode];renderLabels();});
$("#risk").querySelectorAll("button").forEach(b=>b.onclick=()=>$("#risk").querySelectorAll("button").forEach(x=>x.setAttribute("aria-pressed",x===b)));
function tierClass(t){return t==="auto"?"b-auto":t==="verify"?"b-verify":"b-review";}
function esc(s){return String(s).replace(/[&<>]/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;'}[c]));}
function render(d){
  if(d.error){$("#out").innerHTML=`<div class="card"><div class="err">⚠ ${esc(d.error)}</div></div>`;return;}
  const pct=v=>(v/10).toFixed(1)+"%";
  let bars=Object.entries(d.p).map(([n,v])=>`<div class="bar"><div class="bn" title="${esc(n)}">${esc(n)}</div>
    <div class="bt"><div class="bf" style="width:${Math.min(100,v/10)}%"></div></div><div class="bv">${pct(v)}</div></div>`).join("");
  let extra="";
  if(d.mode==="yesno")extra=`<div class="meta">P(yes) = <b>${pct(d.p.yes||0)}</b></div>`;
  if(d.mode==="score")extra=`<div class="meta">expected rank = <b>${(d.expected).toFixed(2)}</b></div>`;
  const cov=d.known?` · known, coverage ${d.coverage[0]}/${d.coverage[1]}`:"";
  let lanes=`<div class="lane"><div class="who">memory</div><div class="what">judge → <b>${esc(d.best)}</b> at ${pct(d.p_best)}${cov}</div><div class="ms">${d.t_lookup} ms</div></div>`;
  if(d.xlm)lanes+=`<div class="lane"><div class="who">worker</div><div class="what">XLM → <b>${esc(d.xlm)}</b></div><div class="ms">${d.t_xlm} ms</div></div>`;
  let note="";
  if(d.disputed)note=`<div class="note note-review">⚠ DISPUTED — the XLM contradicted a confident memory; held for review, not learned.</div>`;
  else if(d.held!=null)note=`<div class="note note-hold">⏸ HELD — teacher margin ${d.held}‰ below the S1_LEARN gate; answered but not learned (work/pending.tsv).</div>`;
  else if(d.recorded)note=`<div class="note note-ok">✓ memory learned this as <b>${esc(d.recorded)}</b></div>`;
  $("#out").innerHTML=`<div class="card"><div class="answer">${esc(d.answer)}</div>
    <span class="badge ${tierClass(d.tier)}">${d.tier}</span><span class="meta">via ${esc(d.via)} · ${d.ms} ms</span>
    ${extra}<div class="lanes">${lanes}</div><div class="bars">${bars}</div>${note}
    <details><summary>raw response</summary><pre>${esc(JSON.stringify(d,null,2))}</pre></details></div>`;
}
$("#go").onclick=async()=>{
  const labels=[...document.querySelectorAll("#labels .lrow")].map(r=>({name:r.querySelector(".name").value.trim(),desc:r.querySelector(".desc").value.trim()})).filter(l=>l.name);
  const body={mode,text:$("#text").value,risk:[...$("#risk").querySelectorAll("button")].find(b=>b.getAttribute("aria-pressed")==="true").dataset.r,train:$("#train").checked,labels};
  const btn=$("#go");btn.disabled=true;btn.textContent="Deciding…";
  try{const r=await fetch("/api/decide",{method:"POST",headers:{"Content-Type":"application/json"},body:JSON.stringify(body)});render(await r.json());}
  catch(e){render({error:String(e)});} btn.disabled=false;btn.textContent="Decide";
};
$("#pingWorker").onclick=async()=>{const btn=$("#pingWorker"),hint=$("#pingHint"),out=$("#workerOut");btn.disabled=true;hint.textContent="checking…";
  try{const j=await (await fetch("/api/worker-status")).json();out.hidden=false;out.textContent=JSON.stringify(j,null,2);
    hint.textContent=j.error?"unreachable":(j.ready?"ready · "+(j.engine_tier||""):(j.status_line||"responded"));}
  catch(e){out.hidden=false;out.textContent=String(e);hint.textContent="error";} btn.disabled=false;};
fetch("/api/host").then(r=>r.json()).then(j=>{$("#host").textContent=j.host||"(unset)";$("#learn").textContent=j.learn;$$(".uiport").forEach(e=>e.textContent=j.port);});
renderLabels();
</script>
</body></html>"###;
