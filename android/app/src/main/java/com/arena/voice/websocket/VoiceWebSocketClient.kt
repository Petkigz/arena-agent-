package com.arena.voice.websocket

import android.util.Log
import kotlinx.coroutines.flow.first
import okhttp3.*
import okio.ByteString
import okio.ByteString.Companion.toByteString
import org.json.JSONObject
import java.util.concurrent.TimeUnit
import javax.inject.Inject
import javax.inject.Singleton
import com.arena.voice.util.SettingsRepository

@Singleton
class VoiceWebSocketClient @Inject constructor(
    private val settings: SettingsRepository,
) {

    private var webSocket: WebSocket? = null
    private var isConnected = false
    private var shouldReconnect = true
    private var reconnectAttempts = 0
    private var currentServerUrl = SettingsRepository.DEFAULT_SERVER_URL

    private val listeners = mutableListOf<VoiceWebSocketListener>()

    /** Connect using the persisted server URL (DataStore), falling back to the default. */
    suspend fun connectToSavedServer() {
        val saved = settings.serverUrl.first()
        connect(saved)
    }

    /** Connect to an explicit URL (used for emulator default and manual overrides). */
    fun connect(serverUrl: String = SettingsRepository.DEFAULT_SERVER_URL) {
        if (isConnected) {
            Log.w(TAG, "Already connected")
            return
        }

        currentServerUrl = serverUrl
        shouldReconnect = true
        reconnectAttempts = 0

        doConnect()
    }

    private fun doConnect() {
        val client = OkHttpClient.Builder()
            .connectTimeout(10, TimeUnit.SECONDS)
            .readTimeout(0, TimeUnit.MINUTES)  // No timeout for WebSocket
            .writeTimeout(10, TimeUnit.SECONDS)
            .build()

        val request = Request.Builder()
            .url(currentServerUrl)
            .build()

        webSocket = client.newWebSocket(request, webSocketListener)
        Log.i(TAG, "Connecting to $currentServerUrl")
    }

    fun disconnect() {
        shouldReconnect = false
        webSocket?.close(1000, "Client disconnecting")
        webSocket = null
        isConnected = false
        reconnectAttempts = 0
        Log.i(TAG, "Disconnected")
    }

    fun sendAudio(audioBytes: ByteArray) {
        if (!isConnected) {
            Log.w(TAG, "Cannot send audio: not connected")
            return
        }

        webSocket?.send(audioBytes.toByteString(0, audioBytes.size))
    }

    fun sendVoiceStart(conversationId: String) {
        sendJson(mapOf(
            "type" to "voice_start",
            "conversation_id" to conversationId
        ))
    }

    fun sendVoiceStop(conversationId: String) {
        sendJson(mapOf(
            "type" to "voice_stop",
            "conversation_id" to conversationId
        ))
    }

    fun onWakeWordDetected() {
        Log.i(TAG, "Wake word detected, notifying backend")
        sendJson(mapOf("type" to "wake_word_detected"))
    }

    private fun sendJson(data: Map<String, Any>) {
        if (!isConnected) {
            Log.w(TAG, "Cannot send message: not connected")
            return
        }

        val json = JSONObject(data as Map<*, *>)
        webSocket?.send(json.toString())
        Log.d(TAG, "Sent: ${json.toString()}")
    }

    fun addListener(listener: VoiceWebSocketListener) {
        listeners.add(listener)
    }

    fun removeListener(listener: VoiceWebSocketListener) {
        listeners.remove(listener)
    }

    private fun scheduleReconnect() {
        if (!shouldReconnect) return
        if (reconnectAttempts >= MAX_RECONNECT_ATTEMPTS) {
            Log.e(TAG, "Max reconnection attempts reached")
            listeners.forEach { it.onError(Exception("Max reconnection attempts reached")) }
            return
        }

        reconnectAttempts++
        val delay = reconnectAttempts * RECONNECT_DELAY_MS
        Log.i(TAG, "Scheduling reconnect attempt $reconnectAttempts in ${delay}ms")

        Thread {
            Thread.sleep(delay)
            if (shouldReconnect && !isConnected) {
                doConnect()
            }
        }.start()
    }

    private val webSocketListener = object : WebSocketListener() {
        override fun onOpen(webSocket: WebSocket, response: Response) {
            Log.i(TAG, "WebSocket connected")
            isConnected = true
            reconnectAttempts = 0
            listeners.forEach { it.onConnected() }
        }

        override fun onMessage(webSocket: WebSocket, text: String) {
            Log.d(TAG, "Received: $text")

            try {
                val json = JSONObject(text)
                val type = json.optString("type")

                when (type) {
                    "voice_state" -> {
                        val state = json.getString("state")
                        listeners.forEach { it.onVoiceState(state) }
                    }
                    "voice_transcript" -> {
                        val transcript = json.getString("text")
                        val isFinal = json.optBoolean("is_final", false)
                        listeners.forEach { it.onTranscript(transcript, isFinal) }
                    }
                    "voice_audio" -> {
                        val audioBase64 = json.getString("audio")
                        listeners.forEach { it.onAudioResponse(audioBase64) }
                    }
                    else -> {
                        Log.w(TAG, "Unknown message type: $type")
                    }
                }

            } catch (e: Exception) {
                Log.e(TAG, "Error parsing message: ${e.message}")
            }
        }

        override fun onMessage(webSocket: WebSocket, bytes: ByteString) {
            Log.d(TAG, "Received audio bytes: ${bytes.size}")
            listeners.forEach { it.onAudioResponse(bytes.toByteArray()) }
        }

        override fun onClosing(webSocket: WebSocket, code: Int, reason: String) {
            Log.i(TAG, "WebSocket closing: $reason")
            webSocket.close(1000, null)
        }

        override fun onClosed(webSocket: WebSocket, code: Int, reason: String) {
            Log.i(TAG, "WebSocket closed: $reason")
            isConnected = false
            listeners.forEach { it.onDisconnected(reason) }
            scheduleReconnect()
        }

        override fun onFailure(webSocket: WebSocket, t: Throwable, response: Response?) {
            Log.e(TAG, "WebSocket failure: ${t.message}")
            isConnected = false
            listeners.forEach { it.onError(t) }
            scheduleReconnect()
        }
    }

    interface VoiceWebSocketListener {
        fun onConnected() {}
        fun onDisconnected(reason: String) {}
        fun onError(throwable: Throwable) {}
        fun onVoiceState(state: String) {}
        fun onTranscript(text: String, isFinal: Boolean) {}
        fun onAudioResponse(audio: String) {}
        fun onAudioResponse(audio: ByteArray) {}
    }

    companion object {
        private const val TAG = "VoiceWebSocketClient"
        // The default server URL now lives in SettingsRepository.DEFAULT_SERVER_URL
        // (editable at runtime via DataStore; see SettingsRepository).
        private const val MAX_RECONNECT_ATTEMPTS = 5
        private const val RECONNECT_DELAY_MS = 2000L
    }
}
