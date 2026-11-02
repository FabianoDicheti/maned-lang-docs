// A Rust app that IS a System One: the memory lookup runs in-process through
// the `maned` crate, the worker and the record are maned-run processes.
//
//     cd consumers/rust && cargo run -- "the text" urgent later careful
//     cargo run -- --yesno "Please wire the deposit today." "This asks for money"
//     cargo run -- --score "Repaint the kitchen next spring." 1="no action" 2="soon" 3="now"
//     cargo run -- --train "..." urgent later careful    # XLM always runs and teaches
//     cargo run -- --pending                             # answers held for review
//     cargo run -- --resolve [accept]                    # confirm them, then learn
//     cargo run                                          # the three demos
//
// The same loop, CLI and review workflow as the Python reference
// (consumers/python/decide.py). Strings, files and processes are the app's;
// every number is a program's.
use std::collections::BTreeMap;
use std::fs;
use std::io::Write;
use std::path::{Path, PathBuf};
use std::process::Command;
use std::time::Instant;

mod serve;   // the --serve web UI (same page as consumers/python/test_ui.py), stdlib only

type Outputs = BTreeMap<String, Vec<i64>>;
const TIERS: [&str; 3] = ["review", "verify", "auto"];
const DEFAULT_LEARN: i64 = 70;   // min teacher cosine margin to learn (permille); override with S1_LEARN. 70 calibrated on the worker: ~87% of learned labels right vs 70% ungated (see README).

fn project() -> PathBuf {
    let mut d = PathBuf::from(env!("CARGO_MANIFEST_DIR"));
    while !d.join("01_lookup.mnd").is_file() {
        d = d.parent().expect("the project folder (01_lookup.mnd) above consumers/rust").to_path_buf();
    }
    d
}

fn load_env() {
    // the worker's address and login from ~/.config/maned/xlm.env, unless already set
    let Some(home) = std::env::var_os("HOME") else { return };
    let Ok(text) = fs::read_to_string(Path::new(&home).join(".config/maned/xlm.env")) else { return };
    for line in text.lines() {
        let line = line.trim().trim_start_matches("export ").trim();
        if let Some((k, v)) = line.split_once('=') {
            if std::env::var_os(k).is_none() {
                std::env::set_var(k, v.trim().trim_matches('"'));
            }
        }
    }
}

fn lines(name: &str) -> Vec<String> {
    fs::read_to_string(project().join(name)).map(|t| t.lines().map(String::from).collect()).unwrap_or_default()
}

fn append(name: &str, text: &str) {
    let mut f = fs::OpenOptions::new().create(true).append(true).open(project().join(name)).unwrap();
    f.write_all(text.as_bytes()).unwrap();
}

fn run_mnd(name: &str) -> Outputs {
    // maned-run PROGRAM -> {output: raw ints} from the lines "name : [shape] = [values]"
    let maned_run = std::env::var("MANED_RUN").unwrap_or_else(|_| "maned-run".into());
    let out = Command::new(maned_run).arg(name).current_dir(project()).output().expect("maned-run");
    let text = String::from_utf8_lossy(&out.stdout).to_string() + &String::from_utf8_lossy(&out.stderr);
    if !out.status.success() {
        eprintln!("{name} failed:\n{text}");
        std::process::exit(1);
    }
    let mut m = Outputs::new();
    for line in text.lines() {
        if let Some((head, tail)) = line.split_once(" : [") {
            if let Some((_, vals)) = tail.split_once("] = [") {
                let vals = vals.trim_end_matches(']');
                m.insert(head.to_string(), vals.split(',').filter_map(|v| v.trim().parse().ok()).collect());
            }
        }
    }
    m
}

fn col_of(name: &str) -> usize {
    // work/labels.tsv: line i is memory column i
    let names = lines("work/labels.tsv");
    match names.iter().position(|n| n == name) {
        Some(i) => i,
        None => { append("work/labels.tsv", &format!("{name}\n")); names.len() }
    }
}

fn describe(name: &str, desc: &str) {
    // each (label, description) is embedded once on the worker
    if lines("work/descs.tsv").iter().any(|l| l == &format!("{name}\t{desc}")) { return; }
    fs::write(project().join("work/q/new_descs.txt"), format!("{desc}\n")).unwrap();
    run_mnd("02_label_embed.mnd");
    append("work/labels_u.csv", &fs::read_to_string(project().join("work/q/new_u.csv")).unwrap());
    append("work/descs.tsv", &format!("{name}\t{desc}\n"));
}

fn req_csv(names: &[String], risk: i64, ordinal: &BTreeMap<String, i64>) -> String {
    let (mut cand, mut ordv, mut riskrow) = ([0i64; 32], [0i64; 32], [0i64; 32]);
    for n in names { cand[col_of(n)] = 1; ordv[col_of(n)] = *ordinal.get(n).unwrap_or(&0); }
    riskrow[0] = risk;
    [cand, ordv, riskrow, [0; 32]].iter()
        .map(|r| r.iter().map(|v| v.to_string()).collect::<Vec<_>>().join(",") + "\n").collect()
}

fn values(part: &[u8]) -> Vec<i64> {
    // an out:: csv part at quantres 3 ("0.955") -> raw ints (955)
    String::from_utf8_lossy(part).trim().split(',').map(|x| (x.parse::<f64>().unwrap() * 1000.0).round() as i64).collect()
}

struct Decision {
    answer: String, via: String, tier: usize, known: bool,
    best: String, p_best: i64, coverage: (i64, i64),
    p: BTreeMap<String, i64>, expected: f64,
    xlm: Option<String>, recorded: Option<String>, disputed: bool, held: Option<i64>,
    how: i32, p_xlm: i64, t_lookup: u128, t_xlm: u128, ms: u128,
}

fn transcript(d: &Decision) -> String {
    let mut out = format!("memory  {:<10} p {}%o  tier {}  known {}",
        d.best, d.p_best, TIERS[d.tier], if d.known { 1 } else { 0 });
    if d.known { out += &format!(" (coverage {}/{})", d.coverage.0, d.coverage.1); }
    out += &format!("   {} ms\n", d.t_lookup);
    if let Some(x) = &d.xlm { out += &format!("xlm     {:<10} {} ms\n", x, d.t_xlm); }
    out += &format!("ANSWER  {:<10} via {} in {} ms", d.answer, d.via, d.ms);
    if let Some(r) = &d.recorded { out += &format!("  (recorded as {r})"); }
    if d.disputed { out += "  DISPUTED: held back for review, not learned"; }
    if let Some(h) = d.held {
        out += &format!("\nHELD    low teacher confidence (margin {h}%o) -> work/pending.tsv, not learned");
    }
    out
}

struct SystemOne { lookup: maned::Script }

impl SystemOne {
    fn open() -> Self {
        // the lookup opens work/q/text.txt and work/q/req.csv when it loads; decide() rewrites them
        // on every call, so a fresh checkout only needs the two placeholders to exist
        fs::create_dir_all(project().join("work/q/out")).expect("work/q/out");
        for (f, blank) in [("work/q/text.txt", "\n".to_string()), ("work/q/req.csv", ("0,".repeat(31) + "0\n").repeat(4))] {
            let p = project().join(f);
            if !p.is_file() { fs::write(&p, blank).expect(f); }
        }
        SystemOne { lookup: maned::load(project().join("01_lookup.mnd")).expect("01_lookup.mnd") }
    }

    fn reload(&mut self) { self.lookup = maned::load(project().join("01_lookup.mnd")).expect("reload"); }

    fn decide(&mut self, text: &str, labels: &[(String, String)], risk: &str,
              ordinal: &BTreeMap<String, i64>, train: bool) -> Decision {
        let text = text.split_whitespace().collect::<Vec<_>>().join(" ");
        let names: Vec<String> = labels.iter().map(|(n, _)| n.clone()).collect();
        let risk_i = match risk { "low" => 0, "high" => 2, _ => 1 };
        fs::create_dir_all(project().join("work/q")).unwrap();
        fs::write(project().join("work/q/text.txt"), format!("{text}\n")).unwrap();
        let t0 = Instant::now();
        let out = self.lookup.run_files(&[("msg", text.as_bytes().to_vec()), ("req", req_csv(&names, risk_i, ordinal).into_bytes())]).expect("lookup");
        let v: Outputs = out.iter().map(|(k, b)| (k.clone(), values(b))).collect();
        let t_lookup = t0.elapsed().as_millis();
        let g = |k: &str| v[k][0];
        let (best, p_best, tier, kbest) = (g("best") as usize, g("p_best"), g("tier") as usize, g("kbest") as usize);
        let known = g("known") == 1;
        let p = &v["p"];
        let label = lines("work/labels.tsv");

        let mut answer: Option<String> = None;
        let mut via = "xlm";
        let mut how = 3i32;
        let mut t_xlm = 0u128;
        let mut xlm: Option<String> = None;
        let mut recorded: Option<String> = None;
        let mut disputed = false;
        let mut held: Option<i64> = None;
        let mut p_xlm: i64 = 0;

        if known { answer = Some(label[kbest].clone()); via = "memory:known"; how = 0; }
        else if tier == 2 { answer = Some(label[best].clone()); via = "memory:auto"; how = 1; }

        if answer.is_none() || train {
            for (n, d) in labels { describe(n, d); }
            let descs: Vec<String> = lines("work/descs.tsv").iter().map(|l| l.split('\t').next().unwrap().to_string()).collect();
            let mask: Vec<&str> = descs.iter().map(|d| if names.contains(d) { "0.001" } else { "0.000" }).collect();
            fs::write(project().join("work/q/cand_d.csv"), mask.join(",") + "\n").unwrap();
            let t1 = Instant::now();
            let cls = run_mnd("02_xlm_classify.mnd");
            let xcol = col_of(&descs[cls["best"][0] as usize]);
            t_xlm = t1.elapsed().as_millis();
            xlm = Some(label[xcol].clone());
            p_xlm = p[xcol];
            // the teacher's confidence: the cosine margin between its best and second-best candidate LABEL
            let s = cls.get("s").cloned().unwrap_or_default();
            let mut by_label: BTreeMap<&str, i64> = BTreeMap::new();
            for (i, dn) in descs.iter().enumerate() {
                if names.contains(dn) && i < s.len() {
                    let e = by_label.entry(dn.as_str()).or_insert(i64::MIN);
                    if s[i] > *e { *e = s[i]; }
                }
            }
            let mut tops: Vec<i64> = by_label.values().cloned().collect();
            tops.sort_unstable_by(|a, b| b.cmp(a));
            let margin = if tops.len() >= 2 { tops[0] - tops[1] } else { i64::MAX };
            let learn: i64 = std::env::var("S1_LEARN").ok().and_then(|x| x.parse().ok()).unwrap_or(DEFAULT_LEARN);
            let confident = train || (tier == 1 && best == xcol) || margin >= learn * 1000;

            if answer.is_none() {
                if tier == 1 && best == xcol { answer = Some(label[best].clone()); via = "memory:verified"; how = 2; }
                else { answer = Some(label[xcol].clone()); via = "xlm"; how = 3; }
            }
            // the verifier: a confident, informed memory contradicted by a label it gives little weight
            disputed = g("informed") == 1 && tier == 2 && best != xcol && p_xlm < g("t_dispute");
            if disputed {
                append("work/review.tsv", &format!("{}\t{}\t{}\t{}\t{}\n", label[xcol], label[best], p_best, p_xlm, text));
            } else if !(known && xcol == kbest) {
                if confident {
                    fs::write(project().join("work/q/label.csv"), format!("{xcol}\n")).unwrap();
                    run_mnd("03_record.mnd");   // rewrites work/memory.dqt
                    append("work/memory.tsv", &format!("{}\t{text}\n", label[xcol]));
                    recorded = Some(label[xcol].clone());
                    self.reload();              // the memory it loaded has changed on disk
                } else {   // the teacher was too unsure to learn from unprompted: hold it for review
                    held = Some(margin / 1000);
                    append("work/pending.tsv", &format!("{}\t{}\t{}\t{text}\n", label[xcol], margin / 1000, names.join("|")));
                }
            }
        }
        let t_answer = t_lookup + if how >= 2 { t_xlm } else { 0 };
        Decision {
            answer: answer.unwrap(), via: via.to_string(), tier, known,
            best: label[best].clone(), p_best, coverage: (g("cov_best"), g("q")),
            p: names.iter().map(|n| (n.clone(), p[col_of(n)])).collect(),
            expected: g("expected") as f64 / 1000.0,
            xlm, recorded, disputed, held, how, p_xlm, t_lookup, t_xlm, ms: t_answer,
        }
    }

    // ---- the review queue (work/pending.tsv): teacher label, margin, candidates, text
    fn show_pending(&self) {
        let rows = lines("work/pending.tsv");
        if rows.is_empty() { println!("nothing held for review"); return; }
        println!("teacher\tmargin\tcandidates\ttext");
        for r in rows { println!("{r}"); }
    }

    fn commit(&mut self, name: &str, text: &str) {
        // record one confirmed (text, label) into the memory, the way decide's record path does
        fs::create_dir_all(project().join("work/q")).unwrap();
        fs::write(project().join("work/q/text.txt"), format!("{text}\n")).unwrap();
        fs::write(project().join("work/q/label.csv"), format!("{}\n", col_of(name))).unwrap();
        run_mnd("03_record.mnd");
        append("work/memory.tsv", &format!("{name}\t{text}\n"));
        self.reload();
    }

    fn resolve(&mut self, args: &[String]) {
        // `--resolve` confirms each held answer; `--resolve accept` takes the teacher's label for every row.
        let accept_all = args.first().map(|s| s == "accept").unwrap_or(false);
        let rows = lines("work/pending.tsv");
        if rows.is_empty() { println!("nothing held for review"); return; }
        let mut kept: Vec<String> = Vec::new();
        for r in &rows {
            let f: Vec<&str> = r.splitn(4, '\t').collect();
            if f.len() < 4 { continue; }
            let (teacher, margin, cands, text) = (f[0], f[1], f[2], f[3]);
            let mut name = teacher.to_string();
            if !accept_all {
                print!("\n{text}\n  candidates: {}\n  teacher: {teacher} (margin {margin}%o)\n  [Enter]=accept, a label, or s=skip: ",
                    cands.replace('|', ", "));
                std::io::stdout().flush().ok();
                let mut ans = String::new();
                if std::io::stdin().read_line(&mut ans).unwrap_or(0) == 0 { ans = "s".into(); }
                let ans = ans.trim();
                if ans == "s" { kept.push(r.clone()); continue; }
                if !ans.is_empty() { name = ans.to_string(); }
            }
            self.commit(&name, text);
            println!("  learned: {name}");
        }
        fs::write(project().join("work/pending.tsv"), kept.iter().map(|x| x.clone() + "\n").collect::<String>()).unwrap();
    }

    fn demo(&mut self) {
        let none = BTreeMap::new();
        let labels = |v: &[(&str, &str)]| v.iter().map(|(n, d)| (n.to_string(), d.to_string())).collect::<Vec<_>>();
        let choice = self.decide("Our servers crashed again, customers cannot log in, fix it within the hour.", &labels(&[
            ("urgent", "This message needs action right now: an outage, an emergency, a deadline today."),
            ("later", "This message can wait: an update, a newsletter, something for next week."),
            ("careful", "This message needs care before acting: a contract, a legal clause, a payment detail.")]), "medium", &none, false);
        println!("choice: {}  (p {}‰, tier {}, via {}, {} ms)", choice.answer, choice.p[&choice.answer], TIERS[choice.tier], choice.via, choice.ms);

        let statement = "This message asks for money to be sent";
        let negation = format!("It is not the case that {}{}", statement[..1].to_lowercase(), &statement[1..]);
        let yesno = self.decide("Please wire the deposit today.", &labels(&[("yes", statement), ("no", &negation)]), "medium", &none, false);
        println!("yes/no: {}  (P(yes) {}‰, tier {}, via {}, {} ms)", yesno.answer, yesno.p["yes"], TIERS[yesno.tier], yesno.via, yesno.ms);

        let ranks = BTreeMap::from([("1".to_string(), 1), ("2".to_string(), 2), ("3".to_string(), 3)]);
        let score = self.decide("The kitchen will be repainted next spring.", &labels(&[("1", "no action"), ("2", "look this week"), ("3", "act today")]), "medium", &ranks, false);
        println!("score:  rank {}, expected {:.2}  (tier {}, via {}, {} ms)", score.answer, score.expected, TIERS[score.tier], score.via, score.ms);
    }
}

fn main() {
    load_env();
    std::env::set_current_dir(project()).unwrap();   // the .mnd files name their inputs relative to the project folder
    let argv: Vec<String> = std::env::args().skip(1).collect();
    let mut s1 = SystemOne::open();

    if argv.first().map(|s| s == "--pending").unwrap_or(false) { s1.show_pending(); return; }
    if argv.first().map(|s| s == "--resolve").unwrap_or(false) { s1.resolve(&argv[1..]); return; }
    if argv.first().map(|s| s == "--serve").unwrap_or(false) {
        let port: u16 = argv.get(1).and_then(|x| x.parse().ok()).unwrap_or(8808);
        serve::run(s1, std::env::var("S1_WORKER_HOST").unwrap_or_default(), port);
        return;
    }

    let (mut risk, mut kind, mut train) = ("medium".to_string(), "choice", false);
    let mut i = 0;
    while i < argv.len() && argv[i].starts_with("--") {
        match argv[i].as_str() {
            "--risk" => { risk = argv.get(i + 1).cloned().unwrap_or_else(|| { eprintln!("--risk needs low|medium|high"); std::process::exit(1); }); i += 2; }
            "--train" => { train = true; i += 1; }
            "--yesno" => { kind = "yesno"; i += 1; }
            "--score" => { kind = "score"; i += 1; }
            other => { eprintln!("unknown flag {other}"); std::process::exit(1); }
        }
    }
    let rest = &argv[i..];
    if rest.is_empty() { s1.demo(); return; }
    let text = rest[0].clone();
    let args = &rest[1..];
    let none = BTreeMap::new();

    match kind {
        "yesno" => {
            let statement = args.first().cloned().unwrap_or_default();
            let negation = args.get(1).cloned().unwrap_or_else(||
                format!("It is not the case that {}{}", statement[..1].to_lowercase(), &statement[1..]));
            let labels = vec![("yes".to_string(), statement), ("no".to_string(), negation)];
            let d = s1.decide(&text, &labels, &risk, &none, train);
            println!("{}\nP(yes)  {}%o", transcript(&d), d.p["yes"]);
        }
        "score" => {
            let labels: Vec<(String, String)> = args.iter()
                .map(|a| { let (n, d) = a.split_once('=').unwrap_or((a.as_str(), "")); (n.to_string(), d.to_string()) }).collect();
            let ordinal: BTreeMap<String, i64> = labels.iter().map(|(n, _)| (n.clone(), n.parse().unwrap_or(0))).collect();
            let d = s1.decide(&text, &labels, &risk, &ordinal, train);
            println!("{}\nexpected rank {:.2}", transcript(&d), d.expected);
        }
        _ => {
            let mut labels: Vec<(String, String)> = Vec::new();
            for a in args {   // name, or name=description; a bare name uses the corpus descriptions, else itself
                let (name, desc) = a.split_once('=').map(|(n, d)| (n.to_string(), d.to_string())).unwrap_or((a.clone(), String::new()));
                let corpus: Vec<String> = lines("corpus/labels.tsv").iter()
                    .filter(|l| l.starts_with(&format!("{name}\t")))
                    .map(|l| l.splitn(2, '\t').nth(1).unwrap_or("").to_string()).collect();
                for d in corpus.iter().skip(1) { describe(&name, d); }
                let primary = if !desc.is_empty() { desc } else { corpus.first().cloned().unwrap_or_else(|| name.clone()) };
                labels.push((name, primary));
            }
            let d = s1.decide(&text, &labels, &risk, &none, train);
            println!("{}", transcript(&d));
        }
    }
}
