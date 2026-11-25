package com.kurio.storycore

import android.annotation.SuppressLint
import android.app.Activity
import android.content.Intent
import android.graphics.Color
import android.net.Uri
import android.os.Build
import android.os.Bundle
import android.text.TextUtils
import android.view.WindowInsets
import android.webkit.JavascriptInterface
import android.webkit.ValueCallback
import android.webkit.WebChromeClient
import android.webkit.WebResourceRequest
import android.webkit.WebView
import android.webkit.WebViewClient
import android.widget.FrameLayout
import android.widget.Toast
import com.chaquo.python.Python
import com.chaquo.python.android.AndroidPlatform
import org.json.JSONObject
import java.io.File
import kotlin.concurrent.thread

/**
 * StoryCore mobile: starts the shared engine (Python, through Chaquopy) on the phone, then shows the interface it
 * serves on http://127.0.0.1:8765 in a full-screen WebView. No PC needed.
 *
 * The interface knows it runs here through the user agent ("StoryCoreAndroid/<version>", see lib/remote.js) and talks
 * to the app through window.StoryCoreAndroid (files the interface makes itself). Everything works by touch: Android's
 * Back key is only a shortcut (closes the open window, then goes back).
 */
class MainActivity : Activity() {

    private lateinit var web: WebView
    private var fileChooserCallback: ValueCallback<Array<Uri>>? = null
    private var pendingSave: FileTransfers.Pending? = null

    @SuppressLint("SetJavaScriptEnabled")
    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)

        val root = FrameLayout(this).apply { setBackgroundColor(Color.parseColor(NIGHT_BLUE)) }
        web = WebView(this).apply { setBackgroundColor(Color.parseColor(NIGHT_BLUE)) }
        root.addView(web, FrameLayout.LayoutParams(FrameLayout.LayoutParams.MATCH_PARENT, FrameLayout.LayoutParams.MATCH_PARENT))
        setContentView(root)
        keepClearOfSystemBars(root)

        val version = runCatching { packageManager.getPackageInfo(packageName, 0).versionName }.getOrNull() ?: "?"
        web.settings.apply {
            javaScriptEnabled = true
            domStorageEnabled = true
            mediaPlaybackRequiresUserGesture = false  // background music
            userAgentString = "$userAgentString StoryCoreAndroid/$version"  // -> mobile mode of the interface
        }
        web.addJavascriptInterface(Bridge(), "StoryCoreAndroid")
        web.webChromeClient = object : WebChromeClient() {
            // <input type="file">: import a Lore pack, a story, a portrait, music...
            override fun onShowFileChooser(
                view: WebView, callback: ValueCallback<Array<Uri>>, params: WebChromeClient.FileChooserParams,
            ): Boolean {
                fileChooserCallback?.onReceiveValue(null)
                fileChooserCallback = callback
                return runCatching {
                    startActivityForResult(FileTransfers.chooserIntent(params), REQUEST_OPEN)
                    true
                }.getOrElse {
                    fileChooserCallback = null
                    toast("Aucune application pour choisir un fichier.")
                    false
                }
            }
        }
        web.webViewClient = object : WebViewClient() {
            override fun shouldOverrideUrlLoading(view: WebView, request: WebResourceRequest): Boolean {
                val host = request.url.host
                if (host == "127.0.0.1" || host == "localhost") return false
                // Links to the outside world (Discord, OpenRouter...) open in the phone's browser.
                runCatching { startActivity(Intent(Intent.ACTION_VIEW, request.url)) }
                return true
            }
        }
        // Files served by the engine (story export, backups, bug report): ask where to save, then copy.
        web.setDownloadListener { url, _, contentDisposition, mimeType, _ ->
            askWhereToSave(FileTransfers.Pending.fromUrl(url, contentDisposition, mimeType))
        }

        showHtml(loadingPage())
        thread(name = "storycore-boot") { boot() }
    }

    private fun boot() {
        val home = File(filesDir, "storycore")
        try {
            AssetSync.syncIfNeeded(this, home)
            if (!Python.isStarted()) Python.start(AndroidPlatform(this))
            val url = Python.getInstance().getModule("mobile_boot")
                .callAttr("start", home.path, File(home, "web").path).toString()
            runOnUiThread { if (!isDestroyed) web.loadUrl(url) }
        } catch (e: Throwable) {
            val report = runCatching {
                Python.getInstance().getModule("mobile_boot").callAttr("status_json").toString()
            }.getOrDefault("")
            runOnUiThread { if (!isDestroyed) showHtml(errorPage(e, report)) }
        }
    }

    // ------------------------------------------------------------------------------------------- files
    /** Called from the interface (lib/util.js saveBlob) for files it makes itself (JSON exports, bug report). */
    inner class Bridge {
        @JavascriptInterface
        fun saveFile(name: String, mimeType: String, base64: String) {
            val pending = runCatching { FileTransfers.Pending.fromBase64(name, mimeType, base64) }.getOrNull()
            runOnUiThread { if (pending != null) askWhereToSave(pending) else toast("Fichier illisible.") }
        }
    }

    private fun askWhereToSave(p: FileTransfers.Pending) {
        pendingSave = p
        runCatching { startActivityForResult(FileTransfers.saveIntent(p), REQUEST_SAVE) }
            .onFailure { pendingSave = null; toast("Impossible d'enregistrer le fichier sur ce téléphone.") }
    }

    // the framework's result API: fine for this single-screen app without AndroidX
    override fun onActivityResult(requestCode: Int, resultCode: Int, data: Intent?) {
        when (requestCode) {
            REQUEST_OPEN -> {
                fileChooserCallback?.onReceiveValue(FileTransfers.chosenFiles(resultCode, data))
                fileChooserCallback = null
            }
            REQUEST_SAVE -> {
                val p = pendingSave
                pendingSave = null
                val target = data?.data
                if (resultCode != RESULT_OK || p == null || target == null) return
                thread(name = "storycore-save") {
                    val ok = runCatching { FileTransfers.write(this, p, target) }.isSuccess
                    runOnUiThread { toast(if (ok) "Fichier enregistré : ${p.name}" else "L'enregistrement a échoué.") }
                }
            }
            else -> super.onActivityResult(requestCode, resultCode, data)
        }
    }

    // -------------------------------------------------------------------------------------- navigation
    /** Optional shortcut: closes the open window (as the Escape key does), otherwise goes back, otherwise leaves. */
    @Deprecated("Still the simplest way to handle Back on every Android version this app supports.")
    override fun onBackPressed() {
        web.evaluateJavascript(CLOSE_TOP_WINDOW_JS) { result ->
            if (result?.contains("closed") == true) return@evaluateJavascript
            if (web.canGoBack()) web.goBack() else @Suppress("DEPRECATION") super.onBackPressed()
        }
    }

    /** Android 11+: draw edge to edge ourselves and keep the page clear of the status bar, navigation bar and keyboard. */
    private fun keepClearOfSystemBars(root: FrameLayout) {
        if (Build.VERSION.SDK_INT < Build.VERSION_CODES.R) return  // older phones resize the window themselves
        window.setDecorFitsSystemWindows(false)
        root.setOnApplyWindowInsetsListener { v, insets ->
            val bars = insets.getInsets(
                WindowInsets.Type.systemBars() or WindowInsets.Type.displayCutout() or WindowInsets.Type.ime()
            )
            v.setPadding(bars.left, bars.top, bars.right, bars.bottom)
            WindowInsets.CONSUMED
        }
    }

    // ------------------------------------------------------------------------------------------- pages
    private fun toast(text: String) = Toast.makeText(this, text, Toast.LENGTH_LONG).show()

    private fun showHtml(html: String) =
        web.loadDataWithBaseURL(null, html, "text/html", "utf-8", null)

    private fun loadingPage() = page(
        """
        <div class="center">
          ${Splash.LOGO_SVG}
          <h1>StoryCore</h1>
          <p>Démarrage du moteur…</p>
          <p class="small">Le tout premier lancement prépare les histoires : il peut prendre une minute.</p>
          <div class="bar"><div></div></div>
        </div>
        """
    )

    private fun errorPage(e: Throwable, reportJson: String): String {
        var lines = ""
        var trace = ""
        runCatching {
            val o = JSONObject(reportJson)
            val r = o.getJSONArray("report")
            lines = (0 until r.length()).joinToString("\n") { r.getString(it) }
            trace = o.optString("error", "")
        }
        if (trace.isBlank() || trace == "null") trace = e.stackTraceToString()
        return page(
            """
            <h1>StoryCore</h1>
            <p><b>Le moteur n'a pas pu démarrer.</b></p>
            <p class="small">Fais une capture d'écran de cette page (ou copie le texte) et envoie-la à Claude.</p>
            <h2>Rapport</h2><pre>${TextUtils.htmlEncode(lines)}</pre>
            <h2>Détail</h2><pre>${TextUtils.htmlEncode(trace)}</pre>
            """
        )
    }

    private fun page(body: String) = """
        <!doctype html><html><head><meta charset="utf-8">
        <meta name="viewport" content="width=device-width, initial-scale=1">
        <style>
          html, body { margin:0; min-height:100%; }
          body { background:radial-gradient(ellipse at 50% 30%, #16224a 0%, $NIGHT_BLUE 70%); color:#ece6d8;
                 font-family:sans-serif; padding:24px; box-sizing:border-box; }
          .center { min-height:85vh; display:flex; flex-direction:column; align-items:center; justify-content:center; text-align:center; }
          .center svg { width:96px; height:96px; margin-bottom:8px; }
          h1 { color:#f3dca0; letter-spacing:3px; font-family:serif; font-weight:700; margin:8px 0; }
          h2 { color:#e2bd72; font-size:16px; margin-top:24px; }
          .small { color:#9aa3c0; font-size:14px; max-width:320px; }
          pre { white-space:pre-wrap; word-break:break-word; font-size:12px; background:#121c3d; padding:10px; border-radius:6px; }
          .bar { width:160px; height:3px; background:#e2bd7226; border-radius:2px; overflow:hidden; margin-top:18px; }
          .bar div { width:40%; height:100%; background:#e2bd72; animation:slide 1.4s ease-in-out infinite; }
          @keyframes slide { 0% { transform:translateX(-100%); } 100% { transform:translateX(250%); } }
        </style></head><body>$body</body></html>
    """.trimIndent()

    companion object {
        const val NIGHT_BLUE = "#0b1430"
        private const val REQUEST_OPEN = 1
        private const val REQUEST_SAVE = 2

        // Radix windows of the interface close on Escape; the narrow-screen side panels have a close button.
        private const val CLOSE_TOP_WINDOW_JS = """
            (function () {
              if (!document.querySelector('[role=dialog]')) return 'none';
              document.dispatchEvent(new KeyboardEvent('keydown', { key: 'Escape', code: 'Escape', keyCode: 27, bubbles: true }));
              return 'closed';
            })()
        """
    }
}
