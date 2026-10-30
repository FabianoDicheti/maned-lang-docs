// A Kotlin app that IS a System One: the memory lookup runs in-process through
// the dev.maned binding, the worker and the record are maned-run processes.
//
//     cd consumers/kotlin && gradle run        (dev.maned:maned 0.4.2 or newer, from Maven Central)
//
// The same loop as the Python app: lookup -> answer, or the XLM -> record.
// Strings, files and processes are the app's; every number is a program's.
import dev.maned.Maned
import java.io.File
import java.util.Locale
import kotlin.system.exitProcess

val project: File = generateSequence(File(Decide::class.java.protectionDomain.codeSource.location.toURI())) { it.parentFile }
    .first { File(it, "01_lookup.mnd").isFile }
val manedRun = System.getenv("MANED_RUN") ?: "maned-run"
val tiers = listOf("review", "verify", "auto")
val risks = mapOf("low" to 0, "medium" to 1, "high" to 2)
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

data class Decision(val answer: String, val via: String, val tier: String, val p: Map<String, Int>,
                    val expected: Double, val xlm: String?, val ms: Long)

var lookup = Maned.load(wf("01_lookup.mnd").path)

fun decide(text0: String, labels: Map<String, String>, risk: String = "medium", ordinal: Map<String, Int> = emptyMap()): Decision {
    val text = text0.trim().split(Regex("\\s+")).joinToString(" ")
    val names = labels.keys.toList()
    wf("work/q").mkdirs()
    wf("work/q/text.txt").writeText(text + "\n")
    val t0 = System.currentTimeMillis()
    val out = lookup.runFiles("msg" to text.toByteArray(), "req" to reqCsv(names, risks.getValue(risk), ordinal).toByteArray())
    val v = out.mapValues { values(it.value) }
    val tLookup = System.currentTimeMillis() - t0
    val best = v.getValue("best")[0]; val tier = v.getValue("tier")[0]
    val known = v.getValue("known")[0] == 1; val kbest = v.getValue("kbest")[0]; val p = v.getValue("p")
    val label = lines("work/labels.tsv")
    var answer: String; var via: String; var xlm: String? = null; var tXlm = 0L
    if (known) { answer = label[kbest]; via = "memory:known" }
    else if (tier == 2) { answer = label[best]; via = "memory:auto" }
    else {
        for ((n, d) in labels) describe(n, d)
        val descs = lines("work/descs.tsv").map { it.substringBefore("\t") }
        wf("work/q/cand_d.csv").writeText(descs.joinToString(",") { if (it in names) "0.001" else "0.000" } + "\n")
        val t1 = System.currentTimeMillis()
        val xcol = colOf(descs[runMnd("02_xlm_classify.mnd").getValue("best")[0]])
        tXlm = System.currentTimeMillis() - t1
        xlm = label[xcol]
        if (tier == 1 && best == xcol) { answer = label[best]; via = "memory:verified" } else { answer = xlm; via = "xlm" }
        if (!(known && xlm == label[kbest])) {
            wf("work/q/label.csv").writeText("$xcol\n")
            runMnd("03_record.mnd")   // rewrites work/memory.dqt
            wf("work/memory.tsv").appendText("$xlm\t$text\n")
            lookup.close()
            lookup = Maned.load(wf("01_lookup.mnd").path, reload = true)   // the memory it loaded has changed
        }
    }
    return Decision(answer, via, tiers[tier], names.associateWith { p[colOf(it)] },
        v.getValue("expected")[0] / 1000.0, xlm, tLookup + tXlm)
}

fun main() {
    loadEnv()
    val choice = decide("Our servers crashed again, customers cannot log in, fix it within the hour.", mapOf(
        "urgent" to "This message needs action right now: an outage, an emergency, a deadline today.",
        "later" to "This message can wait: an update, a newsletter, something for next week.",
        "careful" to "This message needs care before acting: a contract, a legal clause, a payment detail."))
    println("choice: ${choice.answer}  (p ${choice.p[choice.answer]}‰, tier ${choice.tier}, via ${choice.via}, ${choice.ms} ms)")

    val statement = "This message asks for money to be sent"
    val yesno = decide("Please wire the deposit today.",
        mapOf("yes" to statement, "no" to "It is not the case that " + statement.replaceFirstChar { it.lowercase() }))
    println("yes/no: ${yesno.answer}  (P(yes) ${yesno.p["yes"]}‰, tier ${yesno.tier}, via ${yesno.via}, ${yesno.ms} ms)")

    val score = decide("The kitchen will be repainted next spring.",
        mapOf("1" to "no action", "2" to "look this week", "3" to "act today"), ordinal = mapOf("1" to 1, "2" to 2, "3" to 3))
    println("score:  rank ${score.answer}, expected ${"%.2f".format(Locale.ROOT, score.expected)}  (tier ${score.tier}, via ${score.via}, ${score.ms} ms)")
    lookup.close()
}
