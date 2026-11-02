plugins {
    kotlin("jvm") version "2.3.21"
    application
}
repositories { mavenLocal(); mavenCentral() }   // mavenLocal: dev.maned 0.4.3 (loads host-side spm() init) until it is on Maven Central

dependencies {
    implementation("dev.maned:maned:0.4.3")
    // the engine library for this machine; linux-x86_64 and linux-aarch64 exist too
    runtimeOnly("dev.maned:maned:0.4.3:macos-universal")
}

application {
    mainClass.set("DecideKt")
    applicationDefaultJvmArgs = listOf("--enable-native-access=ALL-UNNAMED")   // the binding calls the engine through the FFM API
}
tasks.named<JavaExec>("run") {
    // the .mnd files name their inputs relative to the project folder
    workingDir = projectDir.parentFile.parentFile
}
