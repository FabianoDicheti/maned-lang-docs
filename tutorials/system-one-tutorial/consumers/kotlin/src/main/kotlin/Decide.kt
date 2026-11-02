// A Kotlin app that IS a System One: the memory lookup runs in-process through
// the dev.maned binding, the worker and the record are maned-run processes.
//
//     cd consumers/kotlin && gradle run --args='"the text" urgent later careful'
//     gradle run --args='--yesno "Please wire the deposit today." "This asks for money"'
//     gradle run --args='--score "Repaint next spring." 1="no action" 2="soon" 3="now"'
//     gradle run --args='--train "..." urgent later careful'   # XLM always runs and teaches
//     gradle run --args='--pending'                            # answers held for review
//     gradle run --args='--resolve accept'                     # confirm them, then learn
//     gradle run                                               # the three demos
//
// The same loop, CLI and review workflow as the Python reference
// (consumers/python/decide.py). Strings, files and processes are the app's;
// every number is a program's.
import dev.maned.Maned
import java.io.File
import java.util.Locale
import kotlin.system.exitProcess

val project: File = generateSequence(File(Decide::class.java.protectionDomain.codeSource.location.toURI())) { it.parentFile }
    .first { File(it, "01_lookup.mnd").isFile }
val manedRun = System.getenv("MANED_RUN") ?: "maned-run"
val tiers = listOf("review", "verify", "auto")
val risks = mapOf("low" to 0, "medium" to 1, "high" to 2)
val DEFAULT_LEARN = 70   // min teacher cosine margin to learn (permille); override with S1_LEARN. 70 calibrated on the worker: ~87% of learned labels right vs 70% ungated (see README).
val env = HashMap(System.getenv())
object Decide

fun loadEnv() {   // the worker's address and login from ~/.config/maned/xlm.env, unless already set
    val f = File(System.getProperty("user.home"), ".config/maned/xlm.env")
    if (!f.isFile) return
    for (line in f.readLines()) {
        val m = Regex("""\s*(?:export\s+)?(\w+)=(.*)""").matchEntire(line) ?: continue
        env.putIfAbsent(m.groupValues[1], m.groupValues[2].trim().trim('"'))
    }
}

fun wf(name: String) = File(project, name)
fun lines(name: String): List<String> = wf(name).let { if (it.isFile) it.readLines() else emptyList() }

fun runMnd(name: String): Map<String, List<Int>> {   // maned-run PROGRAM -> {output: raw ints}
    val pb = ProcessBuilder(manedRun, name).directory(project).redirectErrorStream(true)
    pb.environment().putAll(env)
    val p = pb.start()
    val out = p.inputStream.bufferedReader().readText()
    if (p.waitFor() != 0) { System.err.println("$name failed:\n$out"); exitProcess(1) }
    return Regex("""(?m)^(\w+) : \[[^\]]*\] = \[([^\]]*)\]""").findAll(out)
        .associate { it.groupValues[1] to it.groupValues[2].split(",").map { v -> v.trim().toInt() } }
}

fun colOf(name: String): Int {   // work/labels.tsv: line i is memory column i
    val names = lines("work/labels.tsv").toMutableList()
    if (name !in names) { names.add(name); wf("work/labels.tsv").appendText(name + "\n") }
    return names.indexOf(name)
}

fun describe(name: String, desc: String) {   // each (label, description) is embedded once on the worker
    if ("$name\t$desc" in lines("work/descs.tsv")) return
    wf("work/q/new_descs.txt").writeText(desc + "\n")
    runMnd("02_label_embed.mnd")
    wf("work/labels_u.csv").appendText(wf("work/q/new_u.csv").readText())
    wf("work/descs.tsv").appendText("$name\t$desc\n")
}

fun reqCsv(names: List<String>, risk: Int, ordinal: Map<String, Int>): String {
    val cand = IntArray(32); val ordv = IntArray(32)
    for (n in names) { cand[colOf(n)] = 1; ordv[colOf(n)] = ordinal[n] ?: 0 }
    val riskRow = IntArray(32).also { it[0] = risk }
    return listOf(cand, ordv, riskRow, IntArray(32)).joinToString("") { it.joinToString(",") + "\n" }
}

fun values(part: ByteArray): List<Int> =   // an out:: csv part at quantres 3 ('0.955') -> raw ints (955)
    String(part).trim().split(",").map { Math.round(it.toDouble() * 1000).toInt() }

data class Decision(val answer: String, val via: String, val tier: Int, val known: Boolean,
                    val best: String, val pBest: Int, val coverage: Pair<Int, Int>,
                    val p: Map<String, Int>, val expected: Double,
                    val xlm: String?, val recorded: String?, val disputed: Boolean, val held: Int?,
                    val tLookup: Long, val tXlm: Long, val ms: Long)

fun transcript(d: Decision): String {
    val sb = StringBuilder()
    sb.append(String.format(Locale.ROOT, "memory  %-10s p %d%%o  tier %s  known %d", d.best, d.pBest, tiers[d.tier], if (d.known) 1 else 0))
    if (d.known) sb.append(String.format(Locale.ROOT, " (coverage %d/%d)", d.coverage.first, d.coverage.second))
    sb.append(String.format(Locale.ROOT, "   %d ms\n", d.tLookup))
    if (d.xlm != null) sb.append(String.format(Locale.ROOT, "xlm     %-10s %d ms\n", d.xlm, d.tXlm))
    sb.append(String.format(Locale.ROOT, "ANSWER  %-10s via %s in %d ms", d.answer, d.via, d.ms))
    if (d.recorded != null) sb.append("  (recorded as ${d.recorded})")
    if (d.disputed) sb.append("  DISPUTED: held back for review, not learned")
    if (d.held != null) sb.append(String.format(Locale.ROOT, "\nHELD    low teacher confidence (margin %d%%o) -> work/pending.tsv, not learned", d.held))
    return sb.toString()
}

// the lookup opens work/q/text.txt and work/q/req.csv when it loads; decide() rewrites them on
// every call, so a fresh checkout only needs the two placeholders to exist
private val placeholders = run {
    wf("work/q/out").mkdirs()
    wf("work/q/text.txt").let { if (!it.isFile) it.writeText("\n") }
    wf("work/q/req.csv").let { if (!it.isFile) it.writeText(("0,".repeat(31) + "0\n").repeat(4)) }
}
var lookup = Maned.load(wf("01_lookup.mnd").path)

fun decide(text0: String, labels: Map<String, String>, risk: String = "medium",
           ordinal: Map<String, Int> = emptyMap(), train: Boolean = false): Decision {
    val text = text0.trim().split(Regex("\\s+")).joinToString(" ")
    val names = labels.keys.toList()
    wf("work/q").mkdirs()
    wf("work/q/text.txt").writeText(text + "\n")
    val t0 = System.currentTimeMillis()
    val out = lookup.runFiles("msg" to text.toByteArray(), "req" to reqCsv(names, risks.getValue(risk), ordinal).toByteArray())
    val v = out.mapValues { values(it.value) }
    val tLookup = System.currentTimeMillis() - t0
    val best = v.getValue("best")[0]; val pBest = v.getValue("p_best")[0]; val tier = v.getValue("tier")[0]
    val known = v.getValue("known")[0] == 1; val kbest = v.getValue("kbest")[0]; val p = v.getValue("p")
    val label = lines("work/labels.tsv")
    var answer: String? = null; var via = "xlm"; var how = 3; var tXlm = 0L
    var xlm: String? = null; var recorded: String? = null; var disputed = false; var held: Int? = null
    if (known) { answer = label[kbest]; via = "memory:known"; how = 0 }
    else if (tier == 2) { answer = label[best]; via = "memory:auto"; how = 1 }
    if (answer == null || train) {
        for ((n, d) in labels) describe(n, d)
        val descs = lines("work/descs.tsv").map { it.substringBefore("\t") }
        wf("work/q/cand_d.csv").writeText(descs.joinToString(",") { if (it in names) "0.001" else "0.000" } + "\n")
        val t1 = System.currentTimeMillis()
        val cls = runMnd("02_xlm_classify.mnd")
        val xcol = colOf(descs[cls.getValue("best")[0]])
        tXlm = System.currentTimeMillis() - t1
        xlm = label[xcol]
        val pXlm = p[xcol]
        // the teacher's confidence: the cosine margin between its best and second-best candidate label
        val s = cls["s"] ?: emptyList()
        val byLabel = HashMap<String, Int>()
        descs.forEachIndexed { i, dn -> if (dn in names && i < s.size) byLabel[dn] = maxOf(byLabel[dn] ?: Int.MIN_VALUE, s[i]) }
        val top = byLabel.values.sortedDescending()
        val margin = if (top.size >= 2) top[0] - top[1] else Int.MAX_VALUE
        val learn = (env["S1_LEARN"] ?: "$DEFAULT_LEARN").toInt()
        val confident = train || (tier == 1 && best == xcol) || margin >= learn * 1000
        if (answer == null) {
            if (tier == 1 && best == xcol) { answer = label[best]; via = "memory:verified"; how = 2 }
            else { answer = label[xcol]; via = "xlm"; how = 3 }
        }
        // the verifier: a confident, informed memory contradicted by a label it gives little weight
        disputed = v.getValue("informed")[0] == 1 && tier == 2 && best != xcol && pXlm < v.getValue("t_dispute")[0]
        if (disputed) {
            wf("work/review.tsv").appendText("${label[xcol]}\t${label[best]}\t$pBest\t$pXlm\t$text\n")
        } else if (!(known && xcol == kbest)) {
            if (confident) {
                wf("work/q/label.csv").writeText("$xcol\n")
                runMnd("03_record.mnd")   // rewrites work/memory.dqt
                wf("work/memory.tsv").appendText("${label[xcol]}\t$text\n")
                recorded = label[xcol]
                lookup.close()
                lookup = Maned.load(wf("01_lookup.mnd").path, reload = true)   // the memory it loaded has changed
            } else {   // the teacher was too unsure to learn from unprompted: hold it for review
                held = margin / 1000
                wf("work/pending.tsv").appendText("${label[xcol]}\t${margin / 1000}\t${names.joinToString("|")}\t$text\n")
            }
        }
    }
    val tAnswer = tLookup + if (how >= 2) tXlm else 0L
    return Decision(answer!!, via, tier, known, label[best], pBest, Pair(v.getValue("cov_best")[0], v.getValue("q")[0]),
        names.associateWith { p[colOf(it)] }, v.getValue("expected")[0] / 1000.0, xlm, recorded, disputed, held, tLookup, tXlm, tAnswer)
}

// ---- the review queue (work/pending.tsv): teacher label, margin, candidates, text
fun showPending() {
    val rows = lines("work/pending.tsv")
    if (rows.isEmpty()) { println("nothing held for review"); return }
    println("teacher\tmargin\tcandidates\ttext")
    rows.forEach { println(it) }
}

fun commit(name: String, text: String) {
    // record one confirmed (text, label) into the memory, the way decide's record path does
    wf("work/q").mkdirs()
    wf("work/q/text.txt").writeText(text + "\n")
    wf("work/q/label.csv").writeText("${colOf(name)}\n")
    runMnd("03_record.mnd")
    wf("work/memory.tsv").appendText("$name\t$text\n")
    lookup.close()
    lookup = Maned.load(wf("01_lookup.mnd").path, reload = true)
}

fun resolve(args: List<String>) {
    // `--resolve` confirms each held answer; `--resolve accept` takes the teacher's label for every row.
    val acceptAll = args.firstOrNull() == "accept"
    val rows = lines("work/pending.tsv")
    if (rows.isEmpty()) { println("nothing held for review"); return }
    val kept = ArrayList<String>()
    for (r in rows) {
        val f = r.split("\t", limit = 4)
        if (f.size < 4) continue
        val (teacher, margin, cands, text) = f
        var name = teacher
        if (!acceptAll) {
            print("\n$text\n  candidates: ${cands.replace("|", ", ")}\n  teacher: $teacher (margin $margin%o)\n  [Enter]=accept, a label, or s=skip: ")
            val ans = (readLine() ?: "s").trim()
            if (ans == "s") { kept.add(r); continue }
            if (ans.isNotEmpty()) name = ans
        }
        commit(name, text)
        println("  learned: $name")
    }
    wf("work/pending.tsv").writeText(kept.joinToString("") { it + "\n" })
}

fun demo() {
    val choice = decide("Our servers crashed again, customers cannot log in, fix it within the hour.", linkedMapOf(
        "urgent" to "This message needs action right now: an outage, an emergency, a deadline today.",
        "later" to "This message can wait: an update, a newsletter, something for next week.",
        "careful" to "This message needs care before acting: a contract, a legal clause, a payment detail."))
    println("choice: ${choice.answer}  (p ${choice.p[choice.answer]}‰, tier ${tiers[choice.tier]}, via ${choice.via}, ${choice.ms} ms)")

    val statement = "This message asks for money to be sent"
    val yesno = decide("Please wire the deposit today.",
        linkedMapOf("yes" to statement, "no" to "It is not the case that " + statement.replaceFirstChar { it.lowercase() }))
    println("yes/no: ${yesno.answer}  (P(yes) ${yesno.p["yes"]}‰, tier ${tiers[yesno.tier]}, via ${yesno.via}, ${yesno.ms} ms)")

    val score = decide("The kitchen will be repainted next spring.",
        linkedMapOf("1" to "no action", "2" to "look this week", "3" to "act today"), ordinal = mapOf("1" to 1, "2" to 2, "3" to 3))
    println("score:  rank ${score.answer}, expected ${"%.2f".format(Locale.ROOT, score.expected)}  (tier ${tiers[score.tier]}, via ${score.via}, ${score.ms} ms)")
}

fun main(argsIn: Array<String>) {
    loadEnv()
    val argv = argsIn.toMutableList()
    if (argv.firstOrNull() == "--pending") { showPending(); lookup.close(); return }
    if (argv.firstOrNull() == "--resolve") { resolve(argv.drop(1)); lookup.close(); return }
    if (argv.firstOrNull() == "--serve") {
        val port = argv.getOrNull(1)?.toIntOrNull() ?: 8808
        serve(env["S1_WORKER_HOST"] ?: "", port)   // blocks until the process is stopped
        return
    }

    var risk = "medium"; var kind = "choice"; var train = false
    while (argv.isNotEmpty() && argv[0].startsWith("--")) {
        when (val flag = argv.removeAt(0)) {
            "--risk" -> risk = argv.removeAt(0)
            "--train" -> train = true
            "--yesno" -> kind = "yesno"
            "--score" -> kind = "score"
            else -> { System.err.println("unknown flag $flag"); exitProcess(1) }
        }
    }
    if (argv.isEmpty()) { demo(); lookup.close(); return }
    val text = argv.removeAt(0)
    val rest = argv

    when (kind) {
        "yesno" -> {
            val statement = rest.getOrElse(0) { "" }
            val negation = rest.getOrNull(1) ?: ("It is not the case that " + statement.replaceFirstChar { it.lowercase() })
            val d = decide(text, linkedMapOf("yes" to statement, "no" to negation), risk, train = train)
            println(transcript(d) + "\nP(yes)  ${d.p["yes"]}%o")
        }
        "score" -> {
            val labels = LinkedHashMap<String, String>()
            for (a in rest) { val n = a.substringBefore("="); labels[n] = if (a.contains("=")) a.substringAfter("=") else "" }
            val ordinal = labels.keys.associateWith { it.toIntOrNull() ?: 0 }
            val d = decide(text, labels, risk, ordinal, train)
            println(transcript(d) + "\nexpected rank ${"%.2f".format(Locale.ROOT, d.expected)}")
        }
        else -> {
            val labels = LinkedHashMap<String, String>()
            for (a in rest) {   // name, or name=description; a bare name uses the corpus descriptions, else itself
                val name = a.substringBefore("=")
                val desc = if (a.contains("=")) a.substringAfter("=") else ""
                val corpus = lines("corpus/labels.tsv").filter { it.startsWith("$name\t") }.map { it.substringAfter("\t") }
                corpus.drop(1).forEach { describe(name, it) }
                labels[name] = if (desc.isNotEmpty()) desc else (corpus.firstOrNull() ?: name)
            }
            println(transcript(decide(text, labels, risk, train = train)))
        }
    }
    lookup.close()
}
