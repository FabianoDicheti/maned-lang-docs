// A Rust app that IS a System One: the memory lookup runs in-process through
// the `maned` crate, the worker and the record are maned-run processes.
//
//     cd consumers/rust && cargo run        (maned 0.4.2 or newer, from crates.io)
//
// The same loop as the Python app: lookup -> answer, or the XLM -> record.
// Strings, files and processes are the app's; every number is a program's.
use std::collections::BTreeMap;
use std::fs;
use std::path::{Path, PathBuf};
use std::process::Command;
use std::time::Instant;

type Outputs = BTreeMap<String, Vec<i64>>;
const TIERS: [&str; 3] = ["review", "verify", "auto"];

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
    use std::io::Write;
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

fn req_csv(names: &[&str], risk: i64, ordinal: &BTreeMap<&str, i64>) -> String {
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

struct Decision { answer: String, via: &'static str, tier: &'static str, p: BTreeMap<String, i64>, expected: f64, ms: u128 }

struct SystemOne { lookup: maned::Script }

impl SystemOne {
    fn open() -> Self { SystemOne { lookup: maned::load(project().join("01_lookup.mnd")).expect("01_lookup.mnd") } }

    fn decide(&mut self, text: &str, labels: &[(&str, &str)], risk: &str, ordinal: &BTreeMap<&str, i64>) -> Decision {
        let text = text.split_whitespace().collect::<Vec<_>>().join(" ");
        let names: Vec<&str> = labels.iter().map(|(n, _)| *n).collect();
        let risk_i = match risk { "low" => 0, "high" => 2, _ => 1 };
        fs::create_dir_all(project().join("work/q")).unwrap();
        fs::write(project().join("work/q/text.txt"), format!("{text}\n")).unwrap();
        let t0 = Instant::now();
        let out = self.lookup.run_files(&[("msg", text.as_bytes().to_vec()), ("req", req_csv(&names, risk_i, ordinal).into_bytes())]).expect("lookup");
        let v: Outputs = out.iter().map(|(k, b)| (k.clone(), values(b))).collect();
        let t_lookup = t0.elapsed().as_millis();
        let (best, tier) = (v["best"][0] as usize, v["tier"][0] as usize);
        let (known, kbest, p) = (v["known"][0] == 1, v["kbest"][0] as usize, &v["p"]);
        let label = lines("work/labels.tsv");
        let mut t_xlm = 0;
        let (answer, via) = if known { (label[kbest].clone(), "memory:known") }
        else if tier == 2 { (label[best].clone(), "memory:auto") }
        else {
            for (n, d) in labels { describe(n, d); }
            let descs: Vec<String> = lines("work/descs.tsv").iter().map(|l| l.split('\t').next().unwrap().to_string()).collect();
            let mask: Vec<&str> = descs.iter().map(|d| if names.contains(&d.as_str()) { "0.001" } else { "0.000" }).collect();
            fs::write(project().join("work/q/cand_d.csv"), mask.join(",") + "\n").unwrap();
            let t1 = Instant::now();
            let xcol = col_of(&descs[run_mnd("02_xlm_classify.mnd")["best"][0] as usize]);
            t_xlm = t1.elapsed().as_millis();
            let xlm = label[xcol].clone();
            let (answer, via) = if tier == 1 && best == xcol { (label[best].clone(), "memory:verified") } else { (xlm.clone(), "xlm") };
            if !(known && xlm == label[kbest]) {
                fs::write(project().join("work/q/label.csv"), format!("{xcol}\n")).unwrap();
                run_mnd("03_record.mnd");   // rewrites work/memory.dqt
                append("work/memory.tsv", &format!("{xlm}\t{text}\n"));
                self.lookup = maned::load(project().join("01_lookup.mnd")).expect("reload");   // the memory changed
            }
            (answer, via)
        };
        Decision { answer, via, tier: TIERS[tier], p: names.iter().map(|n| (n.to_string(), p[col_of(n)])).collect(),
                   expected: v["expected"][0] as f64 / 1000.0, ms: t_lookup + t_xlm }
    }
}

fn main() {
    load_env();
    std::env::set_current_dir(project()).unwrap();   // the .mnd files name their inputs relative to the project folder
    let mut s1 = SystemOne::open();
    let none = BTreeMap::new();
    let choice = s1.decide("Our servers crashed again, customers cannot log in, fix it within the hour.", &[
        ("urgent", "This message needs action right now: an outage, an emergency, a deadline today."),
        ("later", "This message can wait: an update, a newsletter, something for next week."),
        ("careful", "This message needs care before acting: a contract, a legal clause, a payment detail.")], "medium", &none);
    println!("choice: {}  (p {}‰, tier {}, via {}, {} ms)", choice.answer, choice.p[&choice.answer], choice.tier, choice.via, choice.ms);

    let statement = "This message asks for money to be sent";
    let negation = format!("It is not the case that {}{}", statement[..1].to_lowercase(), &statement[1..]);
    let yesno = s1.decide("Please wire the deposit today.", &[("yes", statement), ("no", &negation)], "medium", &none);
    println!("yes/no: {}  (P(yes) {}‰, tier {}, via {}, {} ms)", yesno.answer, yesno.p["yes"], yesno.tier, yesno.via, yesno.ms);

    let ranks = BTreeMap::from([("1", 1), ("2", 2), ("3", 3)]);
    let score = s1.decide("The kitchen will be repainted next spring.", &[("1", "no action"), ("2", "look this week"), ("3", "act today")], "medium", &ranks);
    println!("score:  rank {}, expected {:.2}  (tier {}, via {}, {} ms)", score.answer, score.expected, score.tier, score.via, score.ms);
}
