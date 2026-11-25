package com.kurio.storycore

import android.app.Activity
import android.content.ClipData
import android.content.Context
import android.content.Intent
import android.net.Uri
import android.util.Base64
import android.webkit.MimeTypeMap
import android.webkit.URLUtil
import android.webkit.WebChromeClient.FileChooserParams
import java.net.HttpURLConnection
import java.net.URL

/**
 * Files in and out of the app, by touch only, without any storage permission: Android's own file picker to open,
 * and its "save as" screen (Storage Access Framework) to save. Works from Android 7.
 */
object FileTransfers {

    /** A file waiting for the player to choose where it goes: bytes made by the interface, or a URL of the engine. */
    class Pending private constructor(val name: String, val mimeType: String, val bytes: ByteArray?, val url: String?) {
        companion object {
            fun fromBase64(name: String, mimeType: String, base64: String) =
                Pending(safeName(name), mimeType.ifBlank { "application/octet-stream" }, Base64.decode(base64, Base64.DEFAULT), null)

            fun fromUrl(url: String, contentDisposition: String?, mimeType: String?): Pending {
                val mime = mimeType?.takeIf { it.isNotBlank() } ?: "application/octet-stream"
                return Pending(safeName(URLUtil.guessFileName(url, contentDisposition, mime)), mime, null, url)
            }

            private fun safeName(n: String) = n.replace(Regex("""[\\/:*?"<>|]"""), "_").ifBlank { "StoryCore" }
        }
    }

    fun saveIntent(p: Pending): Intent = Intent(Intent.ACTION_CREATE_DOCUMENT).apply {
        addCategory(Intent.CATEGORY_OPENABLE)
        type = p.mimeType
        putExtra(Intent.EXTRA_TITLE, p.name)
    }

    /** Copies the pending file to the place the player chose. Runs off the main thread. */
    fun write(context: Context, p: Pending, target: Uri) {
        context.contentResolver.openOutputStream(target)!!.use { out ->
            if (p.bytes != null) {
                out.write(p.bytes)
                return
            }
            val conn = URL(p.url).openConnection() as HttpURLConnection  // the engine, on this phone
            conn.connectTimeout = 15_000
            conn.readTimeout = 300_000
            try {
                if (conn.responseCode !in 200..299) error("HTTP ${conn.responseCode}")
                conn.inputStream.use { it.copyTo(out, 256 * 1024) }
            } finally {
                conn.disconnect()
            }
        }
    }

    /**
     * The picker for <input type="file" accept="...">. Android filters by MIME type only: images and music are
     * filtered; .zip / .json (whose MIME type varies between file managers) show every file so none is hidden.
     */
    fun chooserIntent(params: FileChooserParams): Intent {
        val mimes = params.acceptTypes.orEmpty()
            .flatMap { it.split(',') }
            .map { it.trim().lowercase() }
            .filter { it.isNotEmpty() }
            .map { if (it.startsWith(".")) MimeTypeMap.getSingleton().getMimeTypeFromExtension(it.drop(1)) ?: "*/*" else it }
            .distinct()
        val filtered = mimes.isNotEmpty() && mimes.all { it.startsWith("image/") || it.startsWith("audio/") }
        return Intent(Intent.ACTION_GET_CONTENT).apply {
            addCategory(Intent.CATEGORY_OPENABLE)
            type = if (filtered && mimes.size == 1) mimes[0] else "*/*"
            if (filtered && mimes.size > 1) putExtra(Intent.EXTRA_MIME_TYPES, mimes.toTypedArray())
            if (params.mode == FileChooserParams.MODE_OPEN_MULTIPLE) putExtra(Intent.EXTRA_ALLOW_MULTIPLE, true)
        }
    }

    fun chosenFiles(resultCode: Int, data: Intent?): Array<Uri>? {
        if (resultCode != Activity.RESULT_OK || data == null) return null
        val clip: ClipData? = data.clipData
        if (clip != null && clip.itemCount > 0) return Array(clip.itemCount) { clip.getItemAt(it).uri }
        return data.data?.let { arrayOf(it) }
    }
}
