package com.arena.voice.ui.chat

import android.content.Context
import android.net.Uri
import android.util.Log
import androidx.compose.runtime.mutableStateListOf
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.setValue
import androidx.lifecycle.ViewModel
import com.arena.voice.api.UploadClient
import com.arena.voice.websocket.VoiceWebSocketClient
import dagger.hilt.android.lifecycle.HiltViewModel
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.StateFlow
import kotlinx.coroutines.flow.asStateFlow
import java.util.UUID
import javax.inject.Inject

data class ChatMessage(
    val id: String,
    val role: String,        // "user" | "assistant"
    val content: String,
    val isStreaming: Boolean = false,
    val actionSteps: List<String> = emptyList(),
)

@HiltViewModel
class ChatViewModel @Inject constructor(
    private val webSocketClient: VoiceWebSocketClient,
    private val uploadClient: UploadClient,
) : ViewModel(), VoiceWebSocketClient.VoiceWebSocketListener {

    val messages = mutableStateListOf<ChatMessage>()

    private val _isConnected = MutableStateFlow(false)
    val isConnected: StateFlow<Boolean> = _isConnected.asStateFlow()

    private val _isStreaming = MutableStateFlow(false)
    val isStreaming: StateFlow<Boolean> = _isStreaming.asStateFlow()

    var conversationId by mutableStateOf(webSocketClient.conversationId)
        private set

    private var streamingMessageId: String? = null

    init {
        webSocketClient.addListener(this)
        _isConnected.value = webSocketClient.isConnected()
    }

    fun connect() {
        webSocketClient.connectToSavedServer()
    }

    fun disconnect() {
        webSocketClient.disconnect()
    }

    fun sendMessage(content: String) {
        val text = content.trim()
        if (text.isEmpty()) return

        // Optimistic user message.
        messages.add(ChatMessage(id = UUID.randomUUID().toString(), role = "user", content = text))
        webSocketClient.sendUserMessage(conversationId, text)
    }

    fun newConversation() {
        webSocketClient.createConversation()
    }

    fun requestHistory() {
        messages.clear()
        webSocketClient.requestHistory(conversationId)
    }

    /** Upload a file to the backend and surface the result as a message. */
    suspend fun uploadFile(context: Context, uri: Uri) {
        val result = uploadClient.uploadFile(context, uri, conversationId)
        when (result) {
            is UploadClient.Result.Success -> {
                val name = result.json.optString("name", "attachment")
                sendMessage("I've uploaded a file: $name")
            }
            is UploadClient.Result.Failure -> {
                messages.add(
                    ChatMessage(
                        id = "err_${System.currentTimeMillis()}",
                        role = "assistant",
                        content = "Upload failed: ${result.error}",
                    )
                )
            }
        }
    }

    override fun onCleared() {
        webSocketClient.removeListener(this)
    }

    // ── WebSocket listener (chat) ───────────────────────────────────────────
    override fun onConnected() {
        _isConnected.value = true
        // Bind to the default conversation, then pull its history.
        webSocketClient.requestHistory(conversationId)
    }

    override fun onDisconnected(reason: String) {
        _isConnected.value = false
        _isStreaming.value = false
    }

    override fun onError(throwable: Throwable) {
        _isConnected.value = false
        _isStreaming.value = false
    }

    override fun onConversationJoined(conversationId: String) {
        this.conversationId = conversationId
    }

    override fun onConversationCreated(conversationId: String) {
        this.conversationId = conversationId
        messages.clear()
    }

    override fun onConversationList(ids: List<String>) {
        // Basic support: pick the first conversation if none selected yet.
        if (conversationId.isBlank() && ids.isNotEmpty()) {
            conversationId = ids.first()
            webSocketClient.requestHistory(conversationId)
        }
    }

    override fun onConversationHistory(conversationId: String, history: List<Pair<String, String>>) {
        if (conversationId != this.conversationId) return
        messages.clear()
        history.forEach { (role, content) ->
            messages.add(ChatMessage(id = UUID.randomUUID().toString(), role = role, content = content))
        }
    }

    override fun onMessageToken(conversationId: String, messageId: String, token: String, done: Boolean) {
        if (conversationId != this.conversationId) return
        _isStreaming.value = !done

        if (streamingMessageId == null) {
            streamingMessageId = messageId
            messages.add(ChatMessage(id = messageId, role = "assistant", content = "", isStreaming = true))
        }

        val idx = messages.indexOfFirst { it.id == messageId }
        if (idx >= 0) {
            val m = messages[idx]
            messages[idx] = m.copy(content = m.content + token, isStreaming = !done)
        }

        if (done) {
            streamingMessageId = null
        }
    }

    override fun onActionStep(conversationId: String, messageId: String, label: String, status: String) {
        // Lightweight: append the step label to the streaming message's action steps.
        if (conversationId != this.conversationId || label.isBlank()) return
        val idx = messages.indexOfFirst { it.id == messageId }
        if (idx >= 0) {
            val m = messages[idx]
            val steps = if (m.actionSteps.any { it.startsWith(label) }) m.actionSteps
            else m.actionSteps + "$label ($status)"
            messages[idx] = m.copy(actionSteps = steps)
        }
    }

    override fun onChatError(message: String) {
        _isStreaming.value = false
        Log.w(TAG, "Chat error: $message")
    }

    companion object {
        private const val TAG = "ChatViewModel"
    }
}
