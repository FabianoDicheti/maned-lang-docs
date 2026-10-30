#!/usr/bin/env python3
"""A Python app that IS a System One: the memory lookup runs in-process through
the manedpy binding, the worker and the record are maned-run processes.

    pip install manedpy                                   # 0.4.2 or newer
    python3 consumers/python/decide.py                    # the three demo questions
    python3 consumers/python/decide.py [--risk low|medium|high] [--train] "text" label[=description]...
    python3 consumers/python/decide.py --yesno "text" "statement" ["negation"]
    python3 consumers/python/decide.py --score "text" 1="..." 2="..." 3="..."

What `decide` does per question, in order:
  1. lookup   01_lookup.mnd through manedpy, text bytes in, the decision's numbers out
  2. answer   at once when the text is known or the judge's tier is auto
  3. xlm      else maned-run 02_xlm_classify.mnd on the worker; tier verify is
              confirmed or overruled by it
  4. record   maned-run 03_record.mnd (it rewrites work/memory.dqt), then one
              line appended to work/memory.tsv; the script is reloaded
Training mode (train=True, --train): the XLM runs on every request and its
label is learned even when the memory answered alone, and the verifier holds
back a label a confident, informed memory contradicts (work/review.tsv).
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
TIERS = ["review", "verify", "auto"]
RISK = {"low": 0, "medium": 1, "high": 2}


def load_env():
    """the worker's address and login from ~/.config/maned/xlm.env, unless already in the environment (the device blocks read them with env())"""
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
    """work/labels.tsv: line i is memory column i; a new name takes the next column"""
    names = lines("work/labels.tsv")
    if name not in names:
        names.append(name)
        open("work/labels.tsv", "a", encoding="utf-8").write(name + "\n")
    return names.index(name)


def describe(name, desc):
    """each (label, description) is embedded once on the worker: work/descs.tsv row i = work/labels_u.csv row i"""
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


lookup = mnd.load("01_lookup.mnd")


def decide(text, labels, risk="medium", ordinal=None, train=False):
    """labels: {name: description}; ordinal: {name: rank} for Score questions -> the typed decision"""
    global lookup
    text = " ".join(text.split())
    names = list(labels)
    os.makedirs("work/q", exist_ok=True)
    open("work/q/text.txt", "w", encoding="utf-8").write(text + "\n")   # for the maned-run lanes
    t0 = time.time()
    out = lookup.run_files(msg=text.encode(), req=req_csv(names, RISK[risk], ordinal or {}).encode())
    v = {k: values(b) for k, b in out.items()}
    t_lookup = int((time.time() - t0) * 1000)
    best, p_best, tier, known, kbest = v["best"][0], v["p_best"][0], v["tier"][0], v["known"][0], v["kbest"][0]
    p, label = v["p"], lines("work/labels.tsv")
    answer = via = xlm = None
    how, t_xlm, recorded, disputed, p_xlm = 3, 0, None, False, 0
    if known:
        answer, via, how = label[kbest], "memory:known", 0
    elif tier == 2:
        answer, via, how = label[best], "memory:auto", 1
    if answer is None or train:
        for n, d in labels.items():
            describe(n, d)
        descs = [l.split("\t", 1)[0] for l in lines("work/descs.tsv")]
        open("work/q/cand_d.csv", "w").write(",".join("0.001" if d in names else "0.000" for d in descs) + "\n")
        t1 = time.time()
        xcol = col_of(descs[run_mnd("02_xlm_classify.mnd")["best"][0]])
        t_xlm = int((time.time() - t1) * 1000)
        xlm, p_xlm = label[xcol], p[xcol]
        if answer is None:
            if tier == 1 and best == xcol:
                answer, via, how = label[best], "memory:verified", 2
            else:
                answer, via, how = xlm, "xlm", 3
        # the verifier: a confident, informed memory contradicted by a label it gives little weight
        disputed = bool(v["informed"][0]) and tier == 2 and best != xcol and p_xlm < v["t_dispute"][0]
        if disputed:
            open("work/review.tsv", "a", encoding="utf-8").write("%s\t%s\t%d\t%d\t%s\n" % (xlm, label[best], p_best, p_xlm, text))
        elif not (known and xlm == label[kbest]):
            open("work/q/label.csv", "w").write("%d\n" % xcol)
            run_mnd("03_record.mnd")                 # rewrites work/memory.dqt
            open("work/memory.tsv", "a", encoding="utf-8").write("%s\t%s\n" % (xlm, text))
            recorded = xlm
            lookup.close()
            lookup = mnd.load("01_lookup.mnd")      # the memory it loaded has changed on disk
    t_answer = t_lookup + (t_xlm if how >= 2 else 0)
    return {"answer": answer, "via": via, "tier": TIERS[tier], "known": bool(known),
            "p": {n: p[col_of(n)] for n in names}, "expected": v["expected"][0] / 1000.0,
            "xlm": xlm, "recorded": recorded, "disputed": disputed, "ms": t_answer,
            # the lookup's own numbers, for a transcript or an evaluation row
            "best": label[best], "p_best": p_best, "coverage": (v["cov_best"][0], v["q"][0]),
            "raw": [how, best, p_best, tier, known, p_xlm, int(disputed), t_answer, t_xlm, t_lookup]}


def transcript(d):
    """the decision as three lines, the way the tutorial reads them"""
    out = "memory  %-10s p %d%%o  tier %s  known %d" % (d["best"], d["p_best"], d["tier"], d["known"])
    if d["known"]:
        out += " (coverage %d/%d)" % d["coverage"]
    out += "   %d ms\n" % d["raw"][9]
    if d["xlm"]:
        out += "xlm     %-10s %d ms\n" % (d["xlm"], d["raw"][8])
    out += "ANSWER  %-10s via %s in %d ms" % (d["answer"], d["via"], d["ms"])
    if d["recorded"]:
        out += "  (recorded as %s)" % d["recorded"]
    if d["disputed"]:
        out += "  DISPUTED: held back for review, not learned"
    return out


def main(argv):
    """the command line: a Choice, yes/no or Score question, or the three demo questions"""
    load_env()
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
    print("choice: %s  (p %d%%o, tier %s, via %s, %d ms)" % (
        choice["answer"], choice["p"][choice["answer"]], choice["tier"], choice["via"], choice["ms"]))

    statement = "This message asks for money to be sent"
    yesno = decide("Please wire the deposit today.",
                   {"yes": statement, "no": "It is not the case that " + statement[0].lower() + statement[1:]})
    print("yes/no: %s  (P(yes) %d%%o, tier %s, via %s, %d ms)" % (
        yesno["answer"], yesno["p"]["yes"], yesno["tier"], yesno["via"], yesno["ms"]))

    score = decide("The kitchen will be repainted next spring.",
                   {"1": "no action", "2": "look this week", "3": "act today"}, ordinal={"1": 1, "2": 2, "3": 3})
    print("score:  rank %s, expected %.2f  (tier %s, via %s, %d ms)" % (
        score["answer"], score["expected"], score["tier"], score["via"], score["ms"]))


if __name__ == "__main__":
    main(sys.argv[1:])
