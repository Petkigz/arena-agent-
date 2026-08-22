package com.arena.voice.api

import android.content.Context
import android.net.Uri
import android.provider.OpenableColumns
import android.util.Log
import com.arena.voice.util.SettingsRepository
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

/**
 * HTTP file upload client — mirrors the web UI's attachment flow
 * (POST /api/files/upload with X-API-Key when the backend is authenticated).
 */
@Singleton
class UploadClient @Inject constructor(
    private val settings: SettingsRepository,
) {
    private val client = OkHttpClient.Builder()
        .connectTimeout(15, TimeUnit.SECONDS)
        .readTimeout(120, TimeUnit.SECONDS)
        .build()

    sealed class Result {
        data class Success(val json: JSONObject) : Result()
        data class Failure(val error: String) : Result()
    }

    suspend fun uploadFile(context: Context, uri: Uri, conversationId: String? = null): Result =
        withContext(Dispatchers.IO) {
            try {
                val name = queryDisplayName(context, uri) ?: "upload"
                val mime = context.contentResolver.getType(uri) ?: "application/octet-stream"
                val bytes = context.contentResolver.openInputStream(uri)?.use { it.readBytes() }
                    ?: return@withContext Result.Failure("Could not read file")

                val body = MultipartBody.Builder()
                    .setType(MultipartBody.FORM)
                    .addFormDataPart("file", name, bytes.toRequestBody(mime.toMediaTypeOrNull()))
                    .apply {
                        if (!conversationId.isNullOrBlank()) {
                            addFormDataPart("conversationId", conversationId)
                        }
                    }
                    .build()

                val base = settings.httpBaseUrl()
                val request = Request.Builder()
                    .url("$base/api/files/upload")
                    .post(body)
                    .apply {
                        val key = settings.apiKey.first()
                        if (key.isNotBlank()) header("X-API-Key", key)
                    }
                    .build()

                client.newCall(request).execute().use { resp ->
                    val text = resp.body?.string().orEmpty()
                    if (resp.isSuccessful) {
                        Result.Success(JSONObject(text))
                    } else {
                        val detail = runCatching {
                            JSONObject(text).optString("detail")
                        }.getOrNull() ?: "HTTP ${resp.code}"
                        Result.Failure(detail)
                    }
                }
            } catch (e: Exception) {
                Log.w(TAG, "Upload failed: ${e.message}")
                Result.Failure(e.message ?: "Upload failed")
            }
        }

    private fun queryDisplayName(context: Context, uri: Uri): String? {
        return try {
            context.contentResolver.query(uri, null, null, null, null)?.use { cursor ->
                val idx = cursor.getColumnIndex(OpenableColumns.DISPLAY_NAME)
                if (idx >= 0 && cursor.moveToFirst()) cursor.getString(idx) else null
            }
        } catch (e: Exception) {
            null
        }
    }

    companion object {
        private const val TAG = "UploadClient"
    }
}
