package com.kurio.storycore

import android.app.Activity
import android.app.AlertDialog
import android.app.PendingIntent
import android.content.BroadcastReceiver
import android.content.Context
import android.content.Intent
import android.content.IntentFilter
import android.content.pm.PackageInstaller
import android.net.Uri
import android.os.Build
import android.provider.Settings
import android.widget.LinearLayout
import android.widget.ProgressBar
import android.widget.TextView
import android.widget.Toast
import org.json.JSONArray
import java.io.File
import java.net.HttpURLConnection
import java.net.URL
import java.util.Locale
import kotlin.concurrent.thread

/**
 * Self-update of the final APK (release build only, see BuildConfig.SELF_UPDATE).
 *
 * At every start: reads the public GitHub Releases of the repo (the same ones the PC version updates from), takes the
 * newest published version that carries an .apk, and when it is newer than this app, offers to install it.
 * The APK is downloaded into the app's cache, then handed to Android's PackageInstaller: Android shows its own
 * "Update this app?" screen (and, the very first time, asks to allow StoryCore to install apps).
 * Games, Lore packs and settings stay: the new APK is signed with the same secret key.
 */
class Updater(private val activity: Activity) {

    private data class Release(val version: String, val name: String, val apkUrl: String, val apkName: String, val size: Long)

    private val fr = Locale.getDefault().language == "fr"
    private fun t(french: String, english: String) = if (fr) french else english

    private var waitingForPermission: File? = null
    private var receiver: BroadcastReceiver? = null

    /** Background check; silent when there is nothing new or no network. */
    fun checkInBackground() {
        if (!BuildConfig.SELF_UPDATE || BuildConfig.UPDATE_REPO.isBlank()) return
        thread(name = "storycore-update-check") {
            val release = runCatching { latestRelease() }.getOrNull() ?: return@thread
            val current = runCatching {
                activity.packageManager.getPackageInfo(activity.packageName, 0).versionName
            }.getOrNull() ?: return@thread
            if (compareVersions(release.version, current) <= 0) return@thread
            activity.runOnUiThread { if (!activity.isFinishing) offer(release, current) }
        }
    }

    /** Called from the activity's onResume: back from "allow installing apps" in the phone's settings. */
    fun onResume() {
        val apk = waitingForPermission ?: return
        if (!canInstall()) return
        waitingForPermission = null
        install(apk)
    }

    fun onDestroy() {
        receiver?.let { runCatching { activity.unregisterReceiver(it) } }
        receiver = null
    }

    // ------------------------------------------------------------------------------------------ GitHub
    private fun latestRelease(): Release? {
        val conn = (URL("https://api.github.com/repos/${BuildConfig.UPDATE_REPO}/releases?per_page=10")
            .openConnection() as HttpURLConnection).apply {
            connectTimeout = 10_000
            readTimeout = 15_000
            setRequestProperty("Accept", "application/vnd.github+json")
            setRequestProperty("User-Agent", "StoryCore-Android")
        }
        try {
            if (conn.responseCode != 200) return null
            val list = JSONArray(conn.inputStream.bufferedReader().use { it.readText() })
            for (i in 0 until list.length()) {  // newest first
                val r = list.getJSONObject(i)
                if (r.optBoolean("draft") || r.optBoolean("prerelease")) continue
                val assets = r.optJSONArray("assets") ?: continue
                for (j in 0 until assets.length()) {
                    val a = assets.getJSONObject(j)
                    val name = a.optString("name")
                    if (!name.endsWith(".apk", ignoreCase = true)) continue
                    val version = r.optString("tag_name").trimStart('v', 'V')
                    return Release(version, r.optString("name", version), a.getString("browser_download_url"), name, a.optLong("size"))
                }
            }
            return null
        } finally {
            conn.disconnect()
        }
    }

    // ---------------------------------------------------------------------------------------- dialogs
    private fun offer(release: Release, current: String) {
        val mb = if (release.size > 0) " (%.0f Mo)".format(release.size / 1_048_576.0) else ""
        AlertDialog.Builder(activity)
            .setTitle(t("Mise à jour disponible", "Update available"))
            .setMessage(
                t(
                    "StoryCore ${release.version} est disponible$mb.\nTu as la version $current.\n\nTes parties et tes réglages sont conservés.",
                    "StoryCore ${release.version} is available$mb.\nYou have version $current.\n\nYour games and settings are kept.",
                )
            )
            .setPositiveButton(t("Mettre à jour", "Update")) { _, _ -> download(release) }
            .setNegativeButton(t("Plus tard", "Later"), null)
            .show()
    }

    private fun download(release: Release) {
        val bar = ProgressBar(activity, null, android.R.attr.progressBarStyleHorizontal).apply { max = 100; isIndeterminate = true }
        val label = TextView(activity).apply { text = t("Téléchargement…", "Downloading…") }
        val box = LinearLayout(activity).apply {
            orientation = LinearLayout.VERTICAL
            val pad = (20 * resources.displayMetrics.density).toInt()
            setPadding(pad, pad / 2, pad, 0)
            addView(label)
            addView(bar)
        }
        var cancelled = false
        val dialog = AlertDialog.Builder(activity)
            .setTitle("StoryCore ${release.version}")
            .setView(box)
            .setCancelable(false)
            .setNegativeButton(t("Annuler", "Cancel")) { _, _ -> cancelled = true }
            .show()

        thread(name = "storycore-update-download") {
            val target = File(activity.cacheDir, "update.apk")
            val ok = runCatching {
                val conn = URL(release.apkUrl).openConnection() as HttpURLConnection
                conn.connectTimeout = 15_000
                conn.readTimeout = 30_000
                conn.setRequestProperty("User-Agent", "StoryCore-Android")
                conn.instanceFollowRedirects = true
                try {
                    if (conn.responseCode != 200) error("HTTP ${conn.responseCode}")
                    val total = conn.contentLengthLong.takeIf { it > 0 } ?: release.size
                    conn.inputStream.use { input ->
                        target.outputStream().use { out ->
                            val buf = ByteArray(64 * 1024)
                            var done = 0L
                            var lastPct = -1
                            while (!cancelled) {
                                val n = input.read(buf)
                                if (n < 0) break
                                out.write(buf, 0, n)
                                done += n
                                if (total > 0) {
                                    val pct = (done * 100 / total).toInt()
                                    if (pct != lastPct) {
                                        lastPct = pct
                                        activity.runOnUiThread {
                                            bar.isIndeterminate = false
                                            bar.progress = pct
                                            label.text = t("Téléchargement… $pct %", "Downloading… $pct%")
                                        }
                                    }
                                }
                            }
                        }
                    }
                } finally {
                    conn.disconnect()
                }
                !cancelled
            }.getOrDefault(false)

            activity.runOnUiThread {
                runCatching { dialog.dismiss() }
                when {
                    cancelled -> target.delete()
                    !ok -> {
                        target.delete()
                        toast(t("Le téléchargement a échoué. Réessaie plus tard.", "Download failed. Try again later."))
                    }
                    !canInstall() -> askPermission(target)
                    else -> install(target)
                }
            }
        }
    }

    // ----------------------------------------------------------------------------------------- install
    private fun canInstall(): Boolean =
        Build.VERSION.SDK_INT < Build.VERSION_CODES.O || activity.packageManager.canRequestPackageInstalls()

    /** Android 8+: the user allows StoryCore to install apps once, in the phone's settings. */
    private fun askPermission(apk: File) {
        AlertDialog.Builder(activity)
            .setTitle(t("Une autorisation est nécessaire", "Permission needed"))
            .setMessage(
                t(
                    "Pour se mettre à jour, StoryCore doit pouvoir installer des applications.\n\nSur l'écran suivant, active « Autoriser depuis cette source », puis reviens dans StoryCore.",
                    "To update itself, StoryCore must be allowed to install apps.\n\nOn the next screen, turn on \"Allow from this source\", then come back to StoryCore.",
                )
            )
            .setPositiveButton(t("Ouvrir les réglages", "Open settings")) { _, _ ->
                waitingForPermission = apk
                runCatching {
                    activity.startActivity(
                        Intent(Settings.ACTION_MANAGE_UNKNOWN_APP_SOURCES, Uri.parse("package:${activity.packageName}"))
                    )
                }.onFailure { waitingForPermission = null; toast(t("Réglages introuvables.", "Settings not found.")) }
            }
            .setNegativeButton(t("Plus tard", "Later"), null)
            .show()
    }

    private fun install(apk: File) {
        runCatching {
            listenForResult()
            val installer = activity.packageManager.packageInstaller
            val params = PackageInstaller.SessionParams(PackageInstaller.SessionParams.MODE_FULL_INSTALL).apply {
                setAppPackageName(activity.packageName)
            }
            val id = installer.createSession(params)
            installer.openSession(id).use { session ->
                apk.inputStream().use { input ->
                    session.openWrite("storycore.apk", 0, apk.length()).use { out ->
                        input.copyTo(out, 64 * 1024)
                        session.fsync(out)
                    }
                }
                val flags = PendingIntent.FLAG_UPDATE_CURRENT or
                    (if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.S) PendingIntent.FLAG_MUTABLE else 0)
                val status = PendingIntent.getBroadcast(
                    activity, id, Intent(ACTION_STATUS).setPackage(activity.packageName), flags,
                )
                session.commit(status.intentSender)
            }
        }.onFailure {
            toast(t("L'installation n'a pas pu démarrer : ${it.message}", "Could not start the install: ${it.message}"))
        }
    }

    private fun listenForResult() {
        if (receiver != null) return
        val r = object : BroadcastReceiver() {
            override fun onReceive(context: Context, intent: Intent) {
                when (intent.getIntExtra(PackageInstaller.EXTRA_STATUS, PackageInstaller.STATUS_FAILURE)) {
                    PackageInstaller.STATUS_PENDING_USER_ACTION -> {
                        // Android's own confirmation screen ("Update this app?")
                        @Suppress("DEPRECATION")
                        val confirm = if (Build.VERSION.SDK_INT >= 33)
                            intent.getParcelableExtra(Intent.EXTRA_INTENT, Intent::class.java)
                        else intent.getParcelableExtra(Intent.EXTRA_INTENT)
                        confirm?.let { runCatching { activity.startActivity(it.addFlags(Intent.FLAG_ACTIVITY_NEW_TASK)) } }
                    }
                    PackageInstaller.STATUS_SUCCESS -> Unit  // Android restarts the app with the new version
                    PackageInstaller.STATUS_FAILURE_ABORTED -> Unit  // the user said no
                    else -> {
                        val msg = intent.getStringExtra(PackageInstaller.EXTRA_STATUS_MESSAGE) ?: "?"
                        toast(t("La mise à jour a échoué : $msg", "Update failed: $msg"))
                    }
                }
            }
        }
        val filter = IntentFilter(ACTION_STATUS)
        if (Build.VERSION.SDK_INT >= 33) activity.registerReceiver(r, filter, Context.RECEIVER_NOT_EXPORTED)
        else @Suppress("UnspecifiedRegisterReceiverFlag") activity.registerReceiver(r, filter)
        receiver = r
    }

    private fun toast(text: String) = Toast.makeText(activity, text, Toast.LENGTH_LONG).show()

    companion object {
        private const val ACTION_STATUS = "com.kurio.storycore.UPDATE_INSTALL_STATUS"

        /** "0.7.10" > "0.7.9"; missing parts count as 0; any text after a "-" is ignored. */
        fun compareVersions(a: String, b: String): Int {
            fun parts(v: String) = v.substringBefore('-').split('.').map { it.trim().toIntOrNull() ?: 0 }
            val pa = parts(a)
            val pb = parts(b)
            for (i in 0 until maxOf(pa.size, pb.size)) {
                val c = pa.getOrElse(i) { 0 }.compareTo(pb.getOrElse(i) { 0 })
                if (c != 0) return c
            }
            return 0
        }
    }
}
