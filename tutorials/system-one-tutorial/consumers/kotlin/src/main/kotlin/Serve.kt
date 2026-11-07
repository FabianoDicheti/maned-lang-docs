// The --serve web UI for the Kotlin consumer: the same two-tab page as the
// Python and Rust UIs (Decide + API), served from the JDK's built-in
// com.sun.net.httpserver.HttpServer (no web framework, no JSON library). Each
// request calls the in-process decide(); calls are serialized on a lock, since
// decide() reloads the shared `lookup`. Start it with:  gradle run --args='--serve [port]'
import com.sun.net.httpserver.HttpExchange
import com.sun.net.httpserver.HttpServer
import java.net.HttpURLConnection
import java.net.InetSocketAddress
import java.net.URL
import java.util.Locale
import java.util.concurrent.CountDownLatch

// the page lives in src/main/resources/ui.html (so its JS ${...} isn't seen as a Kotlin template)
private val PAGE: String =
    object {}.javaClass.getResourceAsStream("/ui.html")?.bufferedReader()?.use { it.readText() }
        ?: "<h1>ui.html resource missing</h1>"

private val serveLock = Any()

// ----------------------------- a tiny JSON reader -----------------------------
private class JsonParser(val s: String) {
    var i = 0
    fun parse(): Any? = value()
    private fun ws() { while (i < s.length && s[i].isWhitespace()) i++ }
    private fun lit(t: String) { require(s.startsWith(t, i)); i += t.length }
    private fun value(): Any? { ws(); return when (s[i]) {
        '{' -> obj(); '[' -> arr(); '"' -> str()
        't' -> { lit("true"); true }; 'f' -> { lit("false"); false }; 'n' -> { lit("null"); null }
        else -> num()
    } }
    private fun str(): String {
        i++; val sb = StringBuilder()
        while (i < s.length) { val c = s[i++]; when (c) {
            '"' -> return sb.toString()
            '\\' -> { val e = s[i++]; when (e) {
                '"' -> sb.append('"'); '\\' -> sb.append('\\'); '/' -> sb.append('/')
                'n' -> sb.append('\n'); 't' -> sb.append('\t'); 'r' -> sb.append('\r')
                'b' -> sb.append('\b'); 'f' -> sb.append('\u000C')
                'u' -> { val h = s.substring(i, i + 4); i += 4; sb.append(h.toInt(16).toChar()) }
                else -> {} } }
            else -> sb.append(c) } }
        error("unterminated string")
    }
    private fun num(): Double { val start = i; while (i < s.length && (s[i].isDigit() || s[i] in "+-.eE")) i++; return s.substring(start, i).toDouble() }
    private fun arr(): List<Any?> {
        i++; val l = ArrayList<Any?>(); ws(); if (s[i] == ']') { i++; return l }
        while (true) { l.add(value()); ws(); when (s[i]) { ',' -> i++; ']' -> { i++; return l }; else -> error("array") } }
    }
    private fun obj(): Map<String, Any?> {
        i++; val m = LinkedHashMap<String, Any?>(); ws(); if (s[i] == '}') { i++; return m }
        while (true) { ws(); val k = str(); ws(); require(s[i] == ':'); i++; m[k] = value(); ws()
            when (s[i]) { ',' -> i++; '}' -> { i++; return m }; else -> error("object") } }
    }
}

// ----------------------------- JSON writing -----------------------------
private fun jstr(s: String): String {
    val sb = StringBuilder("\"")
    for (c in s) when (c) {
        '"' -> sb.append("\\\""); '\\' -> sb.append("\\\\"); '\n' -> sb.append("\\n")
        '\r' -> sb.append("\\r"); '\t' -> sb.append("\\t")
        else -> if (c.code < 0x20) sb.append("\\u%04x".format(c.code)) else sb.append(c)
    }
    return sb.append("\"").toString()
}

private fun decisionJson(d: Decision, mode: String): String {
    val p = d.p.entries.joinToString(",") { "${jstr(it.key)}:${it.value}" }
    val xlm = d.xlm?.let { jstr(it) } ?: "null"
    val rec = d.recorded?.let { jstr(it) } ?: "null"
    val held = d.held?.toString() ?: "null"
    return "{" +
        "\"answer\":${jstr(d.answer)},\"via\":${jstr(d.via)},\"tier\":${jstr(tiers[d.tier])},\"known\":${d.known}," +
        "\"best\":${jstr(d.best)},\"p_best\":${d.pBest},\"coverage\":[${d.coverage.first},${d.coverage.second}]," +
        "\"p\":{$p},\"expected\":${"%.3f".format(Locale.ROOT, d.expected)},\"xlm\":$xlm,\"recorded\":$rec," +
        "\"disputed\":${d.disputed},\"held\":$held,\"t_lookup\":${d.tLookup},\"t_xlm\":${d.tXlm},\"ms\":${d.ms},\"mode\":${jstr(mode)}}"
}

// GET the worker's /api/status (no auth), stdlib HttpURLConnection
private fun workerStatus(host: String): String {
    if (host.isBlank()) return """{"error":"S1_WORKER_HOST is not set (source ~/.config/maned/xlm.env)"}"""
    return try {
        val c = URL("http://$host:4780/api/status").openConnection() as HttpURLConnection
        c.connectTimeout = 5000; c.readTimeout = 5000
        c.inputStream.bufferedReader().use { it.readText() }.trim()
    } catch (e: Exception) { """{"error":${jstr(e.toString())}}""" }
}

private fun learnKnob() = (env["S1_LEARN"] ?: "$DEFAULT_LEARN").toInt()

private fun handleDecide(body: String): String {
    val req = (JsonParser(body).parse() as? Map<*, *>) ?: return """{"error":"bad JSON"}"""
    val mode = req["mode"] as? String ?: "choice"
    val text = (req["text"] as? String ?: "").trim()
    val risk = req["risk"] as? String ?: "medium"
    val train = req["train"] as? Boolean ?: false
    val labels = LinkedHashMap<String, String>()
    (req["labels"] as? List<*>)?.forEach { l ->
        (l as? Map<*, *>)?.let {
            val n = (it["name"] as? String)?.trim()
            if (!n.isNullOrEmpty()) { labels[n] = (it["desc"] as? String)?.takeIf { s -> s.isNotEmpty() } ?: n }
        }
    }
    if (text.isEmpty() || labels.isEmpty()) return """{"error":"need text and at least one label"}"""
    val ordinal = if (mode == "score") labels.keys.associateWith { it.toIntOrNull() ?: 0 } else emptyMap()
    val d = decide(text, labels, risk, ordinal, train)
    return decisionJson(d, mode)
}

private fun send(ex: HttpExchange, code: Int, ctype: String, body: String) {
    val bytes = body.toByteArray(Charsets.UTF_8)
    ex.responseHeaders.add("Content-Type", ctype)
    ex.sendResponseHeaders(code, bytes.size.toLong())
    ex.responseBody.use { it.write(bytes) }
}

fun serve(host: String, port: Int) {
    val server = HttpServer.create(InetSocketAddress("127.0.0.1", port), 0)
    server.createContext("/") { ex ->
        try {
            val path = ex.requestURI.path
            val method = ex.requestMethod
            when {
                method == "GET" && (path == "/" || path == "/index.html") -> send(ex, 200, "text/html; charset=utf-8", PAGE)
                method == "GET" && path == "/api/host" ->
                    send(ex, 200, "application/json",
                        "{\"host\":${jstr(if (host.isBlank()) "(unset)" else host)},\"port\":$port,\"learn\":${learnKnob()}}")
                method == "GET" && path == "/api/worker-status" -> send(ex, 200, "application/json", workerStatus(host))
                method == "POST" && path == "/api/decide" -> {
                    val body = ex.requestBody.readBytes().toString(Charsets.UTF_8)
                    val out = synchronized(serveLock) { handleDecide(body) }
                    send(ex, 200, "application/json", out)
                }
                else -> send(ex, 404, "application/json", """{"error":"not found"}""")
            }
        } catch (e: Exception) {
            try { send(ex, 200, "application/json", """{"error":${jstr(e.toString())}}""") } catch (_: Exception) {}
        }
    }
    server.executor = null   // run handlers on the dispatch thread: serial, matching the decide() lock
    server.start()
    println("System One (Kotlin) UI  ->  http://127.0.0.1:$port")
    println("worker: ${if (host.isBlank()) "(unset)" else host}   S1_LEARN=${learnKnob()}")
    println("note: a failed maned-run (e.g. worker unreachable on a novel text) returns an error to the page; the server stays up")
    CountDownLatch(1).await()   // block the main thread; the server runs until the process is stopped
}
