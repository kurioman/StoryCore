// StoryCore mobile: an Android shell around the SHARED engine (app/backend) and the built interface.
// Nothing of the engine is copied by hand: every build takes the current app/backend, Lorepack and Music folders.
plugins {
    id("com.android.application")
    id("org.jetbrains.kotlin.android")
    id("com.chaquo.python")
}

val repoRoot: File = rootDir.resolve("../..").canonicalFile
val generatedAssets: File = layout.buildDirectory.get().asFile.resolve("generated/storycoreAssets")

// The APK carries the engine's version (app/backend/story/config.py, APP_VERSION): same number on PC and mobile.
val engineVersion: String = Regex("""APP_VERSION\s*=\s*"([^"]+)"""")
    .find(repoRoot.resolve("app/backend/story/config.py").readText())?.groupValues?.get(1) ?: "0.0.0"

// Final (self-updating) APK: GitHub Actions passes the release tag ("v0.7.3" -> "0.7.3") and the secret key.
val releaseVersion: String = (System.getenv("STORYCORE_VERSION") ?: "").trimStart('v', 'V').ifBlank { engineVersion }
// 0.7.3 -> 7003, 1.2.10 -> 1002010: always grows with the version, as Android requires for an update.
val releaseVersionCode: Int = releaseVersion.split('.', '-').take(3).map { it.toIntOrNull() ?: 0 }
    .let { p -> (p.getOrElse(0) { 0 } * 1_000_000) + (p.getOrElse(1) { 0 } * 1_000) + p.getOrElse(2) { 0 } }
    .coerceAtLeast(1)
val releaseKeystore: String? = System.getenv("STORYCORE_KEYSTORE")?.takeIf { it.isNotBlank() && file(it).exists() }
val releaseKeystorePassword: String? = System.getenv("STORYCORE_KEYSTORE_PASSWORD")

android {
    namespace = "com.kurio.storycore"
    compileSdk = 35

    defaultConfig {
        applicationId = "com.kurio.storycore"
        minSdk = 24  // Android 7.0, the lowest Chaquopy allows
        targetSdk = 35
        if (System.getenv("STORYCORE_VERSION").isNullOrBlank()) {
            // test APK: the run number, so each test build installs over the previous one
            versionCode = (System.getenv("GITHUB_RUN_NUMBER") ?: "1").toInt()
            versionName = engineVersion
        } else {
            // final APK: the number of the published version (also what the updater compares)
            versionCode = releaseVersionCode
            versionName = releaseVersion
        }
        buildConfigField("String", "UPDATE_REPO", "\"\"")
        ndk {
            // 64-bit ARM: every phone of the last ~8 years. (Python 3.13 on Android has no 32-bit build.)
            abiFilters += listOf("arm64-v8a")
        }
    }

    signingConfigs {
        getByName("debug") {
            // Fixed TEST key (public, in git): every test APK can be installed over the previous one without losing
            // the games. Never used for a public release: that one will get its own secret key.
            storeFile = file("test-debug.keystore")
            storePassword = "android"
            keyAlias = "androiddebugkey"
            keyPassword = "android"
        }
        if (releaseKeystore != null) {
            // SECRET key of the final APK (never in git: _release/signing on Kurio's PC + GitHub Secrets).
            // Losing it means the installed app can no longer be updated.
            create("release") {
                storeFile = file(releaseKeystore)
                storePassword = releaseKeystorePassword
                keyAlias = "storycore"
                keyPassword = releaseKeystorePassword
            }
        }
    }

    buildFeatures {
        buildConfig = true
    }

    buildTypes {
        debug {
            // Test APKs: no automatic updates (they are signed with the public test key).
            buildConfigField("boolean", "SELF_UPDATE", "false")
        }
        release {
            isMinifyEnabled = false
            if (releaseKeystore != null) signingConfig = signingConfigs.getByName("release")
            // Final APK: looks for a newer version in the GitHub Releases at every start.
            buildConfigField("boolean", "SELF_UPDATE", "true")
            buildConfigField("String", "UPDATE_REPO", "\"kurioman/StoryCore\"")
        }
    }
    compileOptions {
        sourceCompatibility = JavaVersion.VERSION_17
        targetCompatibility = JavaVersion.VERSION_17
    }
    kotlinOptions {
        jvmTarget = "17"
    }
    androidResources {
        // The default pattern skips files and folders starting with "_" or "."; Lore packs and the interface may use them.
        ignoreAssetsPattern = "!.svn:!.git:!.ds_store:!*.scc:!CVS:!thumbs.db:!picasa.ini:!*~"
    }
    sourceSets["main"].assets.srcDir(generatedAssets)
}

// Interface + Lore packs + music -> APK assets "storycore/...". MainActivity copies them to the phone at first start
// and after every update.
val syncStoryCoreAssets by tasks.registering(Sync::class) {
    description = "Copies the built interface, the Lore packs and the music into the APK."
    into(generatedAssets.resolve("storycore"))
    from(repoRoot.resolve("app/frontend/dist")) { into("web") }
    from(repoRoot.resolve("Lorepack")) { into("Lorepack") }
    from(repoRoot.resolve("Music")) { into("Music") }
}
tasks.named("preBuild") { dependsOn(syncStoryCoreAssets) }

chaquopy {
    defaultConfig {
        version = "3.13"
        pip {
            // pydantic-core has no Android build on PyPI: GitHub Actions compiles it into mobile/android/wheels.
            options("--find-links", rootDir.resolve("wheels").path)
            install("-r", "requirements-mobile.txt")
        }
        // The engine reads its own files (migrations, data) from disk: unpack it instead of reading it from the APK.
        extractPackages("story")
    }
    sourceSets {
        getByName("main") {
            srcDir(repoRoot.resolve("app/backend").path)  // the shared engine, exactly as on PC
        }
    }
}
