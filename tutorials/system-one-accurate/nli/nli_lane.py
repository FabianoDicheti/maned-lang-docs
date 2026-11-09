#!/usr/bin/env python3
"""nli_lane.py - the entailment worker call of the accuracy edition.

For every candidate hypothesis row of work/descs_nli.tsv (the rows
work/q/cand_d.csv marks 1), POST the pair (work/q/text.txt, hypothesis) to the
NLI worker (maned-nli-bark, mDeBERTa-v3 as int32: POST /api/nli -> the three
logits entailment / neutral / contradiction) and write

  work/q/nli_e.csv    one row: the ENTAILMENT logit per hypothesis row
                      (decimal, 6 places; 0 for non-candidates) - the input
                      of 02_nli_classify.mnd
  work/q/nli_raw.json every reply (logits, clamps, tokens), for a trace

The pair is tokenized like DebertaV2Tokenizer does: the checkpoint's
SentencePiece model (work/nli-spm.model, 00_download.sh) with its ids used
raw, [CLS] text [SEP] hypothesis [SEP], truncated to 512 ids by cutting the
longer side first.

Env: S1_NLI_HOST (else the lines of $S1_NLI_ENV, default ~/.config/maned/nli.env,
else S1_WORKER_HOST), NLI_USER / NLI_PASS (else that file's, else XLM_USER /
XLM_PASS), NLI_PORT (4780), NLI_TIMEOUT (20 s), S1_NLI_CACHE (a jsonl reply
cache: the worker is deterministic, so a pair asked before is answered from the
file), NLI_MODEL_SHA (else nli/model_nli.sha256: the model the worker must serve).
Exit non-zero on any worker error, so the shell stops.
Standard library only, plus the `sentencepiece` package.
"""
import hashlib
import json
import os
import struct
import sys
import time
import urllib.error
import urllib.request

HERE = os.path.dirname(os.path.realpath(__file__))
PAD, CLS, SEP, UNK = 0, 1, 2, 3
MAX_TOKENS = 512


class PairTokenizer:
    def __init__(self, model_file):
        import sentencepiece as spm
        self.sp = spm.SentencePieceProcessor(model_file=model_file)
        assert self.sp.id_to_piece(CLS) == "[CLS]" and self.sp.id_to_piece(SEP) == "[SEP]", "not a DeBERTa-v3 spm.model"

    def encode_pair(self, premise, hypothesis):
        a, b = [int(i) for i in self.sp.encode(premise)], [int(i) for i in self.sp.encode(hypothesis)]
        over = len(a) + len(b) + 3 - MAX_TOKENS
        while over > 0:  # longest_first: drop from the longer sequence's end
            if len(a) >= len(b):
                a.pop()
            else:
                b.pop()
            over -= 1
        return [CLS] + a + [SEP] + b + [SEP]


class Worker:
    """the worker's HTTP API: /api/auth for a token, /api/nli for the logits"""

    def __init__(self, host, port, user, password, timeout=20):
        self.base = "http://%s:%d" % (host, port)
        self.timeout = timeout
        self.user, self.password = user, password
        self.token = None

    def _req(self, method, path, body=None, auth=True):
        data = None if body is None else json.dumps(body).encode()
        req = urllib.request.Request(self.base + path, data=data, method=method)
        if data is not None:
            req.add_header("Content-Type", "application/json")
        if auth and self.token:
            req.add_header("X-Caramel-Token", self.token)
        try:
            with urllib.request.urlopen(req, timeout=self.timeout) as r:
                return r.status, json.loads(r.read() or b"{}")
        except urllib.error.HTTPError as e:
            try:
                return e.code, json.loads(e.read() or b"{}")
            except ValueError:
                return e.code, {}

    def login(self):
        code, j = self._req("POST", "/api/auth", {"username": self.user, "password": self.password}, auth=False)
        if code != 200 or "token" not in j:
            raise SystemExit("nli_lane: login failed (HTTP %s: %s)" % (code, j))
        self.token = j["token"]

    def nli(self, ids, model_sha=None):
        """-> (http code, reply); the reply's logits must hash to its sha256, and come from the expected model"""
        if self.token is None:
            self.login()
        code, j = self._req("POST", "/api/nli", {"ids": ids})
        if code == 401:  # the session token expired (long runs): log in again once
            self.login()
            code, j = self._req("POST", "/api/nli", {"ids": ids})
        if code == 200:
            z = j.get("logits", [])
            got = hashlib.sha256(struct.pack("<%di" % len(z), *z)).hexdigest()
            if len(z) != 3 or got != j.get("sha256"):
                raise SystemExit("nli_lane: reply corrupt - logits do not hash to their sha256: refused")
            if model_sha and not model_sha.startswith(j.get("model_sha256", "?")):
                raise SystemExit("nli_lane: the worker serves model %s, expected %s" % (j.get("model_sha256"), model_sha[:12]))
        return code, j


def call_with_retry(w, ids, sha, tries=6):
    """the platform serves one request at a time and a LAN drops the odd connection:
    a BUSY/5xx reply or a socket error is retried with backoff and logged to
    work/q/nli_lane.err; only a persistent failure stops the run"""
    last = None
    for k in range(tries):
        try:
            code, j = w.nli(ids, model_sha=sha)
            if code == 200:
                return code, j
            last = "HTTP %s: %s" % (code, j)
        except SystemExit:
            raise
        except Exception as e:  # URLError, timeout, a reset connection
            last = repr(e)
            w.token = None
        with open("work/q/nli_lane.err", "a") as f:
            f.write("%s try %d: %s\n" % (time.strftime("%H:%M:%S"), k + 1, last))
        time.sleep(0.5 * (k + 1))
    sys.exit("nli_lane: /api/nli failed %d times: %s" % (tries, last))


def nli_login():
    """the NLI worker's address and identity: the environment first, then
    ~/.config/maned/nli.env ($S1_NLI_ENV), then the XLM worker's own (one box, one login)"""
    kv = {}
    env = os.environ.get("S1_NLI_ENV", os.path.expanduser("~/.config/maned/nli.env"))
    if os.path.isfile(env):
        for line in open(env, encoding="utf-8"):
            line = line.strip()
            if line.startswith("export "):
                line = line[7:]
            if "=" in line and not line.startswith("#"):
                k, v = line.split("=", 1)
                kv[k.strip()] = v.strip().strip("'\"")
    host = os.environ.get("S1_NLI_HOST") or kv.get("S1_NLI_HOST") or os.environ.get("S1_WORKER_HOST")
    user = os.environ.get("NLI_USER") or kv.get("NLI_USER") or kv.get("XLM_USER") or os.environ.get("XLM_USER")
    pw = os.environ.get("NLI_PASS") or kv.get("NLI_PASS") or kv.get("XLM_PASS") or os.environ.get("XLM_PASS")
    if not (host and user and pw):
        sys.exit("nli_lane: set S1_NLI_HOST (and NLI_USER/NLI_PASS when its login differs) in the environment or %s" % env)
    return host, user, pw


def model_sha():
    s = os.environ.get("NLI_MODEL_SHA")
    if s is None:
        try:
            s = open(os.path.join(HERE, "model_nli.sha256")).read().strip()
        except OSError:
            s = ""
    return s or None


def main():
    host, user, pw = nli_login()
    w = Worker(host, int(os.environ.get("NLI_PORT", "4780")), user, pw, timeout=int(os.environ.get("NLI_TIMEOUT", "20")))
    spm_path = os.environ.get("NLI_SPM", "work/nli-spm.model")
    if not os.path.isfile(spm_path):
        sys.exit("nli_lane: %s is missing - run ./00_download.sh first" % spm_path)
    tok = PairTokenizer(spm_path)
    text = open("work/q/text.txt", encoding="utf-8").read().rstrip("\n")
    rows = [l.rstrip("\n").split("\t", 1) for l in open("work/descs_nli.tsv", encoding="utf-8") if l.strip()]
    mask = [float(v) > 0 for v in open("work/q/cand_d.csv").read().strip().split(",")]
    assert len(mask) == len(rows), (len(mask), len(rows))
    sha = model_sha()
    cache_path = os.environ.get("S1_NLI_CACHE")
    cache = {}
    if cache_path and os.path.isfile(cache_path):
        for line in open(cache_path, encoding="utf-8"):
            if line.strip():
                c = json.loads(line)
                if sha is None or c.get("model_sha256") == sha:
                    cache[(c["text"], c["hypothesis"])] = c
    e, raw = [], []
    for (name, hyp), on in zip(rows, mask):
        if not on:
            e.append("0.000000")
            continue
        c = cache.get((text, hyp))
        if c is None:
            code, j = call_with_retry(w, tok.encode_pair(text, hyp), sha)
            z = [v / 10.0 ** j["scale"] for v in j["logits"]]
            c = {"text": text, "hypothesis": hyp, "model_sha256": j.get("model_sha256", sha), "tokens": j.get("tokens"), "logits": z, "clamps": j.get("clamps")}
            if cache_path:
                with open(cache_path, "a", encoding="utf-8") as f:
                    f.write(json.dumps(c, ensure_ascii=False) + "\n")
        e.append("%.6f" % c["logits"][0])
        raw.append({"name": name, "hypothesis": hyp, "tokens": c["tokens"], "logits": c["logits"], "clamps": c["clamps"]})
    with open("work/q/nli_e.csv", "w") as f:
        f.write(",".join(e) + "\n")
    with open("work/q/nli_raw.json", "w") as f:
        json.dump({"text": text, "model_sha256": sha, "pairs": raw}, f)


if __name__ == "__main__":
    main()
