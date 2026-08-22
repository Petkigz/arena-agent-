package com.arena.voice.api

import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.flow.first
import kotlinx.coroutines.withContext
import okhttp3.MediaType.Companion.toMediaTypeOrNull
import okhttp3.OkHttpClient
import okhttp3.Request
import okhttp3.RequestBody.Companion.toRequestBody
import org.json.JSONObject
import java.util.concurrent.TimeUnit
import javax.inject.Inject
import javax.inject.Singleton
import com.arena.voice.util.SettingsRepository

/**
 * General JSON API client — mirrors the web/desktop REST calls (Pansophy
 * knowledge graph, files, memories, models). Shares the backend endpoint with
 * the web UI and the native desktop app.
 */
@Singleton
class ApiClient @Inject constructor(
    private val settings: SettingsRepository,
) {
    private val client = OkHttpClient.Builder()
        .connectTimeout(15, TimeUnit.SECONDS)
        .readTimeout(60, TimeUnit.SECONDS)
        .build()

    /** Returns the raw response body (or null on failure). Parsing happens in callers. */
    private suspend fun call(path: String, method: String = "GET", body: String? = null): String? =
        withContext(Dispatchers.IO) {
            try {
                val base = settings.httpBaseUrl()
                val builder = Request.Builder()
                    .url("$base$path")
                    .apply {
                        val key = settings.apiKey.first()
                        if (key.isNotBlank()) header("X-API-Key", key)
                    }
                if (method == "POST") {
                    builder.post((body ?: "{}").toRequestBody("application/json".toMediaTypeOrNull()))
                }
                client.newCall(builder.build()).execute().use { resp ->
                    if (resp.isSuccessful) resp.body?.string() else null
                }
            } catch (e: Exception) {
                null
            }
        }

    suspend fun knowledgeGraph(): String? = call("/knowledge/graph")

    suspend fun memories(): String? = call("/memories")

    suspend fun searchFiles(query: String): String? =
        call("/filesystem/search", "POST", JSONObject().put("query", query).toString())

    suspend fun models(): String? = call("/models")
}
