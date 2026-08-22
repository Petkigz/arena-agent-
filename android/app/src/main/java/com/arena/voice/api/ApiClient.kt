package com.arena.voice.api

import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.flow.first
import kotlinx.coroutines.withContext
import okhttp3.MediaType.Companion.toMediaTypeOrNull
import okhttp3.MultipartBody
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

    // ── shared settings (wake word, voice, speed, theme, …) ──────────────────
    /** GET /settings → the backend's shared settings JSON (null on failure). */
    suspend fun getSharedSettings(): String? = call("/settings")

    /** POST /settings → merge a partial patch; returns the merged settings. */
    suspend fun updateSharedSettings(patch: JSONObject): String? =
        call("/settings", "POST", patch.toString())

    /** GET /voice/piper-voices → available Piper voices + active voice. */
    suspend fun listPiperVoices(): String? = call("/voice/piper-voices")

    /** POST /voice/piper/select → set the active Piper voice. */
    suspend fun selectPiperVoice(voiceId: String): String? =
        call("/voice/piper/select", "POST", JSONObject().put("profile_name", voiceId).toString())

    // ── vision / images ──────────────────────────────────────────────────────
    /** POST /vision/capture-and-analyze — capture the host PC's screen and analyse it. */
    suspend fun captureAndAnalyze(promptFocus: String? = null): String? {
        val path = if (promptFocus.isNullOrBlank()) "/vision/capture-and-analyze"
        else "/vision/capture-and-analyze?prompt_focus=" + java.net.URLEncoder.encode(promptFocus, "UTF-8")
        return call(path, "POST", "{}")
    }

    /** POST /vision/ocr — OCR an image already on the host. */
    suspend fun ocrImage(imagePath: String): String? =
        call("/vision/ocr", "POST", JSONObject().put("image_path", imagePath).toString())

    /** POST /vision/analyze — OCR + LLM analysis of an image on the host. */
    suspend fun analyzeImage(imagePath: String, promptFocus: String? = null): String? {
        val body = JSONObject()
            .put("image_path", imagePath)
            .put("prompt_focus", promptFocus ?: "")
        return call("/vision/analyze", "POST", body.toString())
    }

    /** POST /mobile/camera — upload an image; returns { file_path, file_url, ... }. */
    suspend fun uploadImage(filename: String, bytes: ByteArray, mime: String = "image/jpeg"): String? =
        withContext(Dispatchers.IO) {
            try {
                val base = settings.httpBaseUrl()
                val body = MultipartBody.Builder()
                    .setType(MultipartBody.FORM)
                    .addFormDataPart("file", filename, bytes.toRequestBody(mime.toMediaTypeOrNull()))
                    .build()
                val request = Request.Builder()
                    .url("$base/mobile/camera")
                    .post(body)
                    .apply {
                        val key = settings.apiKey.first()
                        if (key.isNotBlank()) header("X-API-Key", key)
                    }
                    .build()
                client.newCall(request).execute().use { resp ->
                    if (resp.isSuccessful) resp.body?.string() else null
                }
            } catch (e: Exception) {
                null
            }
        }

    // ── projects (P2 AGI: long-horizon + multi-session) ──────────────────────
    suspend fun getBackendProjectsRaw(): String? = call("/projects")
    suspend fun getBackendProjectRaw(projectId: String): String? = call("/projects/${java.net.URLEncoder.encode(projectId, "UTF-8")}")
    suspend fun createBackendProjectRaw(name: String, description: String = ""): String? =
        call("/projects", "POST", JSONObject().put("name", name).put("description", description).toString())

    // ── LoRA + VLM status ────────────────────────────────────────────────────
    suspend fun getVlmStatus(): String? = call("/vision/vlm-status")
    suspend fun getLoras(): String? = call("/loras")
    suspend fun getLoraStatus(): String? = call("/loras/status")
}
