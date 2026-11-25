package com.kurio.storycore

import android.content.Context
import android.content.res.AssetManager
import java.io.File

/**
 * Copies what the APK carries (assets/storycore: web, Lorepack, Music) into the app's private folder, where the
 * engine reads it like the project folder on PC.
 *
 * Runs at the first start and after every install or update of the APK, never otherwise. The player's own data
 * (storycore/data: database, saves, API keys) is never touched. Only the Lore packs shipped in the APK are replaced;
 * a pack the player made on the phone stays.
 */
object AssetSync {
    private const val ROOT = "storycore"
    private const val MARKER = ".apk_stamp"

    fun syncIfNeeded(context: Context, home: File) {
        val info = context.packageManager.getPackageInfo(context.packageName, 0)
        val stamp = "${info.lastUpdateTime}"
        val marker = File(home, MARKER)
        if (marker.isFile && marker.readText() == stamp) return

        val assets = context.assets
        home.mkdirs()
        File(home, "web").deleteRecursively()  // the interface is always replaced as a whole
        for (pack in assets.list("$ROOT/Lorepack").orEmpty()) File(home, "Lorepack/$pack").deleteRecursively()
        for (top in assets.list(ROOT).orEmpty()) copy(assets, "$ROOT/$top", File(home, top))
        marker.writeText(stamp)
    }

    private fun copy(assets: AssetManager, path: String, target: File) {
        val children = assets.list(path).orEmpty()
        if (children.isEmpty()) {
            // a file (an empty folder also lists nothing: then there is nothing to copy)
            runCatching {
                assets.open(path).use { input ->
                    target.parentFile?.mkdirs()
                    target.outputStream().use { input.copyTo(it, 256 * 1024) }
                }
            }
            return
        }
        target.mkdirs()
        for (c in children) copy(assets, "$path/$c", File(target, c))
    }
}
