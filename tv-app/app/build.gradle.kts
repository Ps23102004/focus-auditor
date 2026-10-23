plugins {
    id("com.android.application")
    id("org.jetbrains.kotlin.android")
}

android {
    namespace = "com.focusauditor.tv"
    compileSdk = 34
    defaultConfig {
        applicationId = "com.focusauditor.tv"
        minSdk = 22
        targetSdk = 34
        versionCode = 1
        versionName = "0.1.0"
    }
    compileOptions {
        sourceCompatibility = JavaVersion.VERSION_1_8
        targetCompatibility = JavaVersion.VERSION_1_8
    }
    kotlinOptions { jvmTarget = "1.8" }
    // The dashboard (web/) is copied into assets at build time so the TV app shows the same report.
    sourceSets["main"].assets.srcDirs("build/generated/dashboard")
}

val copyDashboard by tasks.registering(Copy::class) {
    from("../../web") { exclude("test/**") }
    into("build/generated/dashboard/web")
}
tasks.named("preBuild") { dependsOn(copyDashboard) }

dependencies {
    implementation("androidx.webkit:webkit:1.8.0")
}
