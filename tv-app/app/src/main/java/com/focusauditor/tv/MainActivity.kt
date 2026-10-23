package com.focusauditor.tv

import android.app.Activity
import android.os.Bundle
import android.view.KeyEvent
import android.webkit.WebResourceRequest
import android.webkit.WebResourceResponse
import android.webkit.WebView
import android.webkit.WebViewClient
import androidx.webkit.WebViewAssetLoader

/** Shows the Focus Auditor report on the TV, in the dashboard's 10-foot mode, driven by the D-pad. */
class MainActivity : Activity() {
    private lateinit var web: WebView

    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        // Bundled assets are served over https://appassets.androidplatform.net so fetch() works without file:// access.
        val loader = WebViewAssetLoader.Builder()
            .addPathHandler("/assets/", WebViewAssetLoader.AssetsPathHandler(this))
            .build()
        web = WebView(this).apply {
            settings.javaScriptEnabled = true
            settings.allowFileAccess = false
            settings.allowContentAccess = false
            webViewClient = object : WebViewClient() {
                override fun shouldInterceptRequest(view: WebView, request: WebResourceRequest): WebResourceResponse? =
                    loader.shouldInterceptRequest(request.url)
            }
            isFocusable = true
            isFocusableInTouchMode = true
            setBackgroundColor(0xFFF5F5F7.toInt()) // dashboard canvas colour while loading, no white flash
            // 1 CSS px = 1 screen px, so the 10-foot layout matches the 1920x1080 design (default zoom is the density, ~2x).
            setInitialScale(100)
        }
        setContentView(web)
        web.loadUrl("https://appassets.androidplatform.net/assets/web/index.html?tv=1&app=1")
        web.requestFocus()
    }

    // BACK first acts as Escape inside the dashboard (return to the findings list); a second BACK leaves the app.
    private var lastBack = 0L
    override fun dispatchKeyEvent(event: KeyEvent): Boolean {
        if (event.keyCode == KeyEvent.KEYCODE_BACK && event.action == KeyEvent.ACTION_UP) {
            val now = System.currentTimeMillis()
            if (now - lastBack > 1500) {
                lastBack = now
                web.evaluateJavascript("document.dispatchEvent(new KeyboardEvent('keydown',{key:'Escape',bubbles:true}))", null)
                return true
            }
        }
        return super.dispatchKeyEvent(event)
    }
}
