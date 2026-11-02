plugins {
    kotlin("jvm") version "2.3.21"
    application
}
repositories { mavenCentral(); mavenLocal() }   // mavenLocal second: a locally published dev.maned also resolves

// the jar with the engine library for this machine (0.4.3 or newer: its library loads the host-side spm() initializer)
val os = System.getProperty("os.name").lowercase()
val arch = System.getProperty("os.arch").lowercase()
val classifier = when {
    os.contains("mac") -> "macos-universal"
    arch == "aarch64" || arch == "arm64" -> "linux-aarch64"
    else -> "linux-x86_64"
}

dependencies {
    implementation("dev.maned:maned:0.4.3")
    runtimeOnly("dev.maned:maned:0.4.3:$classifier")
}

application {
    mainClass.set("DecideKt")
    applicationDefaultJvmArgs = listOf("--enable-native-access=ALL-UNNAMED")   // the binding calls the engine through the FFM API
}
tasks.named<JavaExec>("run") {
    // the .mnd files name their inputs relative to the project folder
    workingDir = projectDir.parentFile.parentFile
}
