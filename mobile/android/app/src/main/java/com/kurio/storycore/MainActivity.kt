package com.kurio.storycore

import android.annotation.SuppressLint
import android.app.Activity
import android.content.Intent
import android.graphics.Color
import android.os.Build
import android.os.Bundle
import android.text.TextUtils
import android.view.WindowInsets
import android.webkit.WebChromeClient
import android.webkit.WebResourceRequest
import android.webkit.WebView
import android.webkit.WebViewClient
import android.widget.FrameLayout
import com.chaquo.python.Python
import com.chaquo.python.android.AndroidPlatform
import org.json.JSONObject
import java.io.File
import kotlin.concurrent.thread

/**
 * StoryCore mobile: starts the shared engine (Python, through Chaquopy) on the phone, then shows the interface it
 * serves on http://127.0.0.1:8765 in a full-screen WebView. No PC needed.
 */
class MainActivity : Activity() {

    private lateinit var web: WebView

    @SuppressLint("SetJavaScriptEnabled")
    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)

        val root = FrameLayout(this).apply { setBackgroundColor(Color.parseColor(NIGHT_BLUE)) }
        web = WebView(this).apply { setBackgroundColor(Color.parseColor(NIGHT_BLUE)) }
        root.addView(web, FrameLayout.LayoutParams(FrameLayout.LayoutParams.MATCH_PARENT, FrameLayout.LayoutParams.MATCH_PARENT))
        setContentView(root)
        keepClearOfSystemBars(root)

        web.settings.apply {
            javaScriptEnabled = true
            domStorageEnabled = true
            mediaPlaybackRequiresUserGesture = false  // background music
        }
        web.webChromeClient = WebChromeClient()
        web.webViewClient = object : WebViewClient() {
            override fun shouldOverrideUrlLoading(view: WebView, request: WebResourceRequest): Boolean {
                val host = request.url.host
                if (host == "127.0.0.1" || host == "localhost") return false
                // Links to the outside world (Discord, OpenRouter...) open in the phone's browser.
                runCatching { startActivity(Intent(Intent.ACTION_VIEW, request.url)) }
                return true
            }
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

    @Deprecated("Still the simplest way to handle Back on every Android version this app supports.")
    override fun onBackPressed() {
        if (web.canGoBack()) web.goBack() else @Suppress("DEPRECATION") super.onBackPressed()
    }

    private fun showHtml(html: String) =
        web.loadDataWithBaseURL(null, html, "text/html", "utf-8", null)

    private fun loadingPage() = page(
        """
        <h1>StoryCore</h1>
        <p>Démarrage du moteur…</p>
        <p class="small">Le tout premier lancement prépare les histoires : il peut prendre une minute.</p>
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
          body { background:$NIGHT_BLUE; color:#e8e6f0; font-family:sans-serif; padding:24px; }
          h1 { color:#e3b341; letter-spacing:2px; font-weight:600; }
          h2 { color:#e3b341; font-size:16px; margin-top:24px; }
          .small { color:#9aa3c0; font-size:14px; }
          pre { white-space:pre-wrap; word-break:break-word; font-size:12px; background:#121c3d; padding:10px; border-radius:6px; }
        </style></head><body>$body</body></html>
    """.trimIndent()

    companion object {
        const val NIGHT_BLUE = "#0b1430"
    }
}
