#!/usr/bin/env python3
"""A Python app that IS a System One, accuracy edition: the known-text lookup
runs in-process through the manedpy binding; the prototype judge, the
entailment teacher and the two records are maned-run processes.

    pip install manedpy sentencepiece                     # manedpy 0.4.2 or newer
    python3 consumers/python/decide.py                    # the three demo questions
    python3 consumers/python/decide.py [--risk low|medium|high] [--train] "text" label[=description]...
    python3 consumers/python/decide.py --yesno "text" "statement" ["negation"]
    python3 consumers/python/decide.py --score "text" 1="..." 2="..." 3="..."
    python3 consumers/python/decide.py --pending          # answers held for review
    python3 consumers/python/decide.py --resolve [accept] # confirm them, then learn

What `decide` does per question, in order:
  1. lookup   01_lookup.mnd through manedpy: a KNOWN text answers from the count memory in ~8 ms
  2. proto    else maned-run 02_proto_classify.mnd: one XLM-R embedding, scored against the
              learned centroids (protos.dqt). Margin >= t_auto with >= min_n texts learned
              under the winning label (proto_policy.csv): the judge answers, "proto:auto"
  3. nli      else nli/nli_lane.py asks the entailment worker about every candidate
              hypothesis and 02_nli_classify.mnd picks the most entailed: "nli"
  4. learn    whenever the teacher ran: its label goes into BOTH memories (03_record.mnd,
              03_record_proto.mnd) when the rule holds - by default when the XLM-R zero-shot
              verdict (the anchor) agrees and the NLI margin clears S1_LEARN (250 permille); otherwise the answer
              is held in work/pending.tsv with both verdicts and the text's vector
Training mode (train=True, --train): both lanes run on every request; the learn rule still decides.
Env: S1_LEARN, S1_LEARN_RULE=agree|nli|all, S1_SELF_LEARN=1, MANED_RUN, S1_HYPOTHESES; the
workers' addresses and logins from ~/.config/maned/xlm.env and ~/.config/maned/nli.env.
Strings, files and processes are the app's; every number is a program's.
"""
import os
import re
import subprocess
import sys
import time

from manedpy import maned as mnd

PROJECT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
os.chdir(PROJECT)                      # every path in the .mnd files is relative to the project folder
MANED_RUN = os.environ.get("MANED_RUN", "maned-run")
PYTHON = os.environ.get("S1_PYTHON", sys.executable)
TIERS = ["review", "verify", "auto"]
RISK = {"low": 0, "medium": 1, "high": 2}
DEFAULT_LEARN = 250                    # min NLI margin (permille of P(entail)) to learn; measured: 75% of learned labels right at 250 under `agree`
ZERO_VEC = ",".join(["0.000"] * 256)


def load_env():
    """the XLM-R worker's address and login from ~/.config/maned/xlm.env, unless already in the
    environment (the device blocks read them with env()); nli/nli_lane.py reads nli.env itself"""
    path = os.path.expanduser("~/.config/maned/xlm.env")
    if os.path.exists(path):
        for line in open(path):
            m = re.match(r"\s*(?:export\s+)?(\w+)=(.*)", line)
            if m:
                os.environ.setdefault(m.group(1), m.group(2).strip().strip('"'))


def run_mnd(name):
    """maned-run PROGRAM -> {output: [raw ints]} from the lines 'name : [shape] = [values]'"""
    r = subprocess.run([MANED_RUN, name], capture_output=True, text=True)
    if r.returncode:
        sys.exit("%s failed:\n%s%s" % (name, r.stdout, r.stderr))
    return {m.group(1): [int(v) for v in m.group(2).split(",")]
            for m in re.finditer(r"^(\w+) : \[[^\]]*\] = \[([^\]]*)\]", r.stdout, re.M)}


def lines(path):
    return [l.rstrip("\n") for l in open(path, encoding="utf-8")] if os.path.exists(path) else []


def col_of(name):
    """work/labels.tsv: line i is column i of both memories; a new name takes the next column"""
    names = lines("work/labels.tsv")
    if name not in names:
        names.append(name)
        open("work/labels.tsv", "a", encoding="utf-8").write(name + "\n")
    return names.index(name)


def hypothesis_of(name, desc):
    """the sentence the NLI worker tests the text against: $S1_HYPOTHESES, else corpus/hypotheses.tsv, else the description"""
    for path in (os.environ.get("S1_HYPOTHESES", ""), "corpus/hypotheses.tsv"):
        for l in lines(path) if path else []:
            n, _, h = l.partition("\t")
            if n == name and h:
                return h
    return desc


def describe(name, desc):
    """each (label, description) is embedded once on the worker: work/descs.tsv row i = work/labels_u.csv row i;
    the label's hypothesis goes to work/descs_nli.tsv (nothing embedded)"""
    hyp = "%s\t%s" % (name, hypothesis_of(name, desc))
    if hyp not in lines("work/descs_nli.tsv"):
        open("work/descs_nli.tsv", "a", encoding="utf-8").write(hyp + "\n")
    if "%s\t%s" % (name, desc) in lines("work/descs.tsv"):
        return
    open("work/q/new_descs.txt", "w", encoding="utf-8").write(desc + "\n")
    run_mnd("02_label_embed.mnd")
    open("work/labels_u.csv", "a").write(open("work/q/new_u.csv").read())
    open("work/descs.tsv", "a", encoding="utf-8").write("%s\t%s\n" % (name, desc))


def req_csv(names, risk, ordinal):
    """the [4,32] request: candidate columns, their ranks, the risk level"""
    cand, ordv = [0] * 32, [0] * 32
    for n in names:
        cand[col_of(n)] = 1
        ordv[col_of(n)] = ordinal.get(n, 0)
    rows = [cand, ordv, [risk] + [0] * 31, [0] * 32]
    return "".join(",".join(str(v) for v in r) + "\n" for r in rows)


def values(part):
    """an out:: csv part, decoded at quantres 3 ('0.955'), back to raw ints (955)"""
    return [int(round(float(x) * 1000)) for x in part.decode().strip().split(",")]


def mask_csv(registry, names):
    """work/q/cand_d.csv: 1 for the registry rows of the candidates (written 0.001 -> raw 1 at quantres 3)"""
    rows = [l.split("\t", 1)[0] for l in lines(registry)]
    open("work/q/cand_d.csv", "w").write(",".join("0.001" if r in names else "0.000" for r in rows) + "\n")
    return rows


def label_margin(rows, names, s):
    """top1 - top2 (x10^6) over the candidate LABELS, each scored by the max over its registry rows"""
    bylabel = {}
    for i, dn in enumerate(rows):
        if dn in names and i < len(s):
            bylabel[dn] = max(bylabel.get(dn, -10 ** 9), s[i])
    top = sorted(bylabel.values(), reverse=True)
    return (top[0] - top[1]) if len(top) >= 2 else 10 ** 9


# the lookup opens work/q/text.txt and work/q/req.csv when it loads; decide() rewrites them on
# every call, so a fresh checkout only needs the two placeholders to exist
os.makedirs("work/q/out", exist_ok=True)
for _f, _blank in (("work/q/text.txt", "\n"), ("work/q/req.csv", ("0," * 31 + "0\n") * 4)):
    if not os.path.exists(_f):
        open(_f, "w").write(_blank)
lookup = mnd.load("01_lookup.mnd")


def proto(names):
    """02_proto_classify.mnd: the anchor verdict and the prototype judge from ONE embedding; u lands in work/q/u.csv"""
    descs = mask_csv("work/descs.tsv", names)
    open("work/q/d2l.csv", "w").write("".join(
        ",".join("0.001" if j == col_of(dn) else "0.000" for j in range(32)) + "\n" for dn in descs))
    t = time.time()
    out = run_mnd("02_proto_classify.mnd")
    label = lines("work/labels.tsv")
    arow = out["best"][0]
    pcol = out["pbest"][0]
    return {"anchor": label[col_of(descs[arow])], "anchor_cos": out["s"][arow] / 1e6, "anchor_margin": label_margin(descs, names, out["s"]),
            "name": label[pcol], "col": pcol, "cos": out["ps"][pcol] / 1e6, "margin": out["pmargin"][0],
            "tier": out["ptier"][0], "n": out["nbest"][0], "ms": int((time.time() - t) * 1000)}


def nli(names):
    """nli/nli_lane.py on every candidate hypothesis, then 02_nli_classify.mnd: the most entailed label"""
    rows = mask_csv("work/descs_nli.tsv", names)
    m = open("work/q/cand_d.csv").read().strip().split(",")
    open("work/q/cand_m.csv", "w").write(",".join("1.000" if float(v) > 0 else "0.000" for v in m) + "\n")
    open("work/q/cand_one.csv", "w").write(",".join("1.000" for _ in m) + "\n")
    t = time.time()
    r = subprocess.run([PYTHON, "nli/nli_lane.py"], capture_output=True, text=True)
    if r.returncode:
        sys.exit("the NLI worker call failed:\n%s%s" % (r.stdout, r.stderr))
    out = run_mnd("02_nli_classify.mnd")
    row = out["best"][0]
    label = lines("work/labels.tsv")
    return {"name": label[col_of(rows[row])], "col": col_of(rows[row]), "p": out["s"][row] / 1e6,
            "margin": label_margin(rows, names, out["s"]), "ms": int((time.time() - t) * 1000)}


def record_both(name, vec=None):
    """both memories learn (text in work/q/text.txt, NAME): 03_record.mnd and 03_record_proto.mnd rewrite their
    .dqt files; one line goes to work/memory.tsv and its vector (or 256 zeros) to work/vectors.csv"""
    global lookup
    if vec is not None:
        open("work/q/u.csv", "w").write(vec.strip() + "\n")
    elif not os.path.exists("work/q/u.csv") or not open("work/q/u.csv").read().strip():
        open("work/q/u.csv", "w").write(ZERO_VEC + "\n")
    open("work/q/label.csv", "w").write("%d\n" % col_of(name))
    run_mnd("03_record.mnd")
    run_mnd("03_record_proto.mnd")
    open("work/memory.tsv", "a", encoding="utf-8").write("%s\t%s\n" % (name, open("work/q/text.txt", encoding="utf-8").read().rstrip("\n")))
    open("work/vectors.csv", "a").write(open("work/q/u.csv").read().strip() + "\n")
    lookup.close()
    lookup = mnd.load("01_lookup.mnd")      # the memory it loaded has changed on disk


def decide(text, labels, risk="medium", ordinal=None, train=False):
    """labels: {name: description}; ordinal: {name: rank} for Score questions -> the typed decision"""
    text = " ".join(text.split())
    names = list(labels)
    os.makedirs("work/q", exist_ok=True)
    open("work/q/text.txt", "w", encoding="utf-8").write(text + "\n")   # for the maned-run lanes
    open("work/q/u.csv", "w").write("")
    t0 = time.time()
    out = lookup.run_files(msg=text.encode(), req=req_csv(names, RISK[risk], ordinal or {}).encode())
    v = {k: values(b) for k, b in out.items()}
    t_lookup = int((time.time() - t0) * 1000)
    best, p_best, tier, known, kbest = v["best"][0], v["p_best"][0], v["tier"][0], v["known"][0], v["kbest"][0]
    p, label = v["p"], lines("work/labels.tsv")
    answer = via = None
    how, pr, nl, agree, recorded, held = 0, None, None, None, None, None
    if known:
        answer, via, how = label[kbest], "memory:known", 0
    if answer is None or train:
        for n, d in labels.items():
            describe(n, d)
        pr = proto(names)
        if answer is None and pr["tier"] == 2:
            answer, via, how = pr["name"], "proto:auto", 4
        if answer is None or train:
            nl = nli(names)
            if answer is None:
                answer, via, how = nl["name"], "nli", 3
            agree = pr["anchor"] == nl["name"]   # the fixed zero-shot verdict, not the judge's own: no feedback loop
            learn = int(os.environ.get("S1_LEARN", DEFAULT_LEARN))
            rule = os.environ.get("S1_LEARN_RULE", "agree")
            confident = {"agree": agree and nl["margin"] >= learn * 1000,
                         "nli": nl["margin"] >= learn * 1000, "all": True}[rule]
            if known and nl["name"] == label[kbest]:
                pass
            elif confident:
                record_both(nl["name"])
                recorded = nl["name"]
            else:
                held = nl["margin"] // 1000
                open("work/pending.tsv", "a", encoding="utf-8").write("%s\t%d\t%s\t%s\t%s\t%s\n" % (
                    nl["name"], held, pr["name"], "|".join(names), text, open("work/q/u.csv").read().strip()))
        elif os.environ.get("S1_SELF_LEARN") == "1":
            record_both(pr["name"])
            recorded = pr["name"]
    t_answer = t_lookup + {4: pr["ms"] if pr else 0, 3: (pr["ms"] if pr else 0) + (nl["ms"] if nl else 0)}.get(how, 0)
    return {"answer": answer, "via": via, "tier": TIERS[tier], "known": bool(known),
            "p": {n: p[col_of(n)] for n in names}, "expected": v["expected"][0] / 1000.0,
            "proto": pr, "nli": nl, "agree": agree, "recorded": recorded, "held": held, "ms": t_answer,
            "best": label[best], "p_best": p_best, "coverage": (v["cov_best"][0], v["q"][0]),
            # the row an evaluation keeps: how, best, p_best, tier, known, teacher col, t_answer, t_lookup
            "raw": [how, best, p_best, tier, known, (nl or pr or {}).get("col", -1), t_answer, t_lookup]}


def transcript(d):
    """the decision as the tutorial's lines"""
    out = "memory  %-10s p %d%%o  tier %s  known %d" % (d["best"], d["p_best"], d["tier"], d["known"])
    if d["known"]:
        out += " (coverage %d/%d)" % d["coverage"]
    out += "   %d ms\n" % d["raw"][7]
    pr, nl = d["proto"], d["nli"]
    if pr:
        out += "proto   %-10s cos %.3f  margin %d%%o  tier %s  from %d texts   anchor %s (cos %.3f)   %d ms\n" % (
            pr["name"], pr["cos"], pr["margin"] // 1000, TIERS[pr["tier"]], pr["n"], pr["anchor"], pr["anchor_cos"], pr["ms"])
    if nl:
        out += "nli     %-10s P(entail) %.3f  margin %d%%o   %s   %d ms\n" % (
            nl["name"], nl["p"], nl["margin"] // 1000, "AGREE" if d["agree"] else "DISAGREE", nl["ms"])
    out += "ANSWER  %-10s via %s in %d ms" % (d["answer"], d["via"], d["ms"])
    if d["recorded"]:
        out += "  (recorded as %s)" % d["recorded"]
    if d.get("held") is not None:
        out += "\nHELD    %s (NLI margin %d%%o) -> work/pending.tsv, not learned" % (
            "low teacher confidence" if d["agree"] else "the two lanes disagree", d["held"])
    return out


def show_pending():
    """print the answers held for review (work/pending.tsv): teacher, margin, judge, candidates, text"""
    rows = lines("work/pending.tsv")
    if not rows:
        print("nothing held for review")
        return
    print("teacher\tmargin\tjudge\tcandidates\ttext")
    for r in rows:
        print("\t".join(r.split("\t")[:5]))


def resolve(args):
    """learn the held answers. `--resolve` confirms each one; `--resolve accept` takes the
    teacher's label for every row without asking. A corrected label, or `s` to skip, is read
    from the keyboard; skipped rows stay in the queue. The row's vector feeds the centroid memory."""
    accept_all = bool(args) and args[0] == "accept"
    rows = lines("work/pending.tsv")
    if not rows:
        print("nothing held for review")
        return
    kept = []
    for r in rows:
        f = r.split("\t")
        if len(f) < 5:
            continue
        teacher, margin, judge, cands, text = f[:5]
        vec = f[5] if len(f) > 5 and f[5] else None
        name = teacher
        if not accept_all:
            try:
                ans = input("\n%s\n  candidates: %s\n  teacher: %s (margin %s%%o), judge: %s\n  [Enter]=accept the teacher, a label, or s=skip: "
                            % (text, cands.replace("|", ", "), teacher, margin, judge)).strip()
            except EOFError:
                ans = "s"
            if ans == "s":
                kept.append(r)
                continue
            if ans:
                name = ans
        open("work/q/text.txt", "w", encoding="utf-8").write(text + "\n")
        record_both(name, vec or ZERO_VEC)
        print("  learned: %s" % name)
    open("work/pending.tsv", "w", encoding="utf-8").write("".join(x + "\n" for x in kept))


def main(argv):
    """the command line: a Choice, yes/no or Score question, the review queue, or the demos"""
    load_env()
    if argv and argv[0] == "--pending":
        return show_pending()
    if argv and argv[0] == "--resolve":
        return resolve(argv[1:])
    risk, kind, train = "medium", "choice", False
    while argv and argv[0].startswith("--"):
        flag = argv.pop(0)
        if flag == "--risk":
            risk = argv.pop(0)
        elif flag == "--train":
            train = True
        elif flag in ("--yesno", "--score"):
            kind = flag[2:]
        else:
            sys.exit("unknown flag " + flag)
    if not argv:
        return demo()
    text, args = argv[0], argv[1:]
    if kind == "yesno":
        statement = args[0]
        negation = args[1] if len(args) > 1 else "It is not the case that " + statement[0].lower() + statement[1:]
        d = decide(text, {"yes": statement, "no": negation}, risk, train=train)
        print(transcript(d) + "\nP(yes)  %d%%o" % d["p"]["yes"])
    elif kind == "score":
        labels = dict(a.split("=", 1) for a in args)
        d = decide(text, labels, risk, ordinal={n: int(n) for n in labels}, train=train)
        print(transcript(d) + "\nexpected rank %.2f" % d["expected"])
    else:
        labels = {}
        for a in args:          # name, or name=description; a bare name uses the corpus descriptions, else itself
            name, _, desc = a.partition("=")
            corpus = [l.split("\t", 1)[1] for l in lines("corpus/labels.tsv") if l.startswith(name + "\t")]
            for d in corpus[1:]:
                describe(name, d)
            labels[name] = desc or (corpus[0] if corpus else name)
        print(transcript(decide(text, labels, risk, train=train)))


def demo():
    choice = decide("Our servers crashed again, customers cannot log in, fix it within the hour.",
                    {"urgent": "This message needs action right now: an outage, an emergency, a deadline today.",
                     "later": "This message can wait: an update, a newsletter, something for next week.",
                     "careful": "This message needs care before acting: a contract, a legal clause, a payment detail."})
    print("choice: %s  (via %s, %d ms)" % (choice["answer"], choice["via"], choice["ms"]))

    statement = "This message asks for money to be sent"
    yesno = decide("Please wire the deposit today.",
                   {"yes": statement, "no": "It is not the case that " + statement[0].lower() + statement[1:]})
    print("yes/no: %s  (P(yes) %d‰, via %s, %d ms)" % (yesno["answer"], yesno["p"]["yes"], yesno["via"], yesno["ms"]))

    score = decide("The kitchen will be repainted next spring.",
                   {"1": "no action", "2": "look this week", "3": "act today"}, ordinal={"1": 1, "2": 2, "3": 3})
    print("score:  rank %s, expected %.2f  (via %s, %d ms)" % (score["answer"], score["expected"], score["via"], score["ms"]))


if __name__ == "__main__":
    main(sys.argv[1:])
