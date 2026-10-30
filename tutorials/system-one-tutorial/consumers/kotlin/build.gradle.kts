plugins {
    kotlin("jvm") version "2.3.21"
    application
}
repositories { mavenCentral() }

dependencies {
    implementation("dev.maned:maned:0.4.2")
    // the engine library for this machine; linux-x86_64 and linux-aarch64 exist too
    runtimeOnly("dev.maned:maned:0.4.2:macos-universal")
}

application {
    mainClass.set("DecideKt")
    applicationDefaultJvmArgs = listOf("--enable-native-access=ALL-UNNAMED")   // the binding calls the engine through the FFM API
}
tasks.named<JavaExec>("run") {
    // the .mnd files name their inputs relative to the project folder
    workingDir = projectDir.parentFile.parentFile
}
