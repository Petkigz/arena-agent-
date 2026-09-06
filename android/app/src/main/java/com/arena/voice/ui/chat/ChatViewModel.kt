package com.arena.voice.ui.chat

import android.content.Context
import android.net.Uri
import android.util.Log
import androidx.compose.runtime.mutableStateListOf
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.setValue
import androidx.lifecycle.ViewModel
import androidx.lifecycle.viewModelScope
import com.arena.voice.api.ApiClient
import com.arena.voice.api.UploadClient
import com.arena.voice.websocket.VoiceWebSocketClient
import dagger.hilt.android.lifecycle.HiltViewModel
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.StateFlow
import kotlinx.coroutines.flow.asStateFlow
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.launch
import kotlinx.coroutines.withContext
import org.json.JSONArray
import org.json.JSONObject
import java.util.UUID
import javax.inject.Inject

data class ChatMessage(
    val id: String,
    val role: String,        // "user" | "assistant"
    val content: String,
    val isStreaming: Boolean = false,
    val actionSteps: List<ToolActivity> = emptyList(),
)

/** One tool/activity step rendered semantically (review: Android must render
 * the same event desktop/web render — never raw diagnostic output).
 * Status vocabulary matches the wire: "in_progress" → "complete" (+"error"). */
data class ToolActivity(
    val label: String,
    val status: String,
)

/** Inline "Working context" card data (design review section 4). Each field is
 * optional — partial context still renders; offline renders nothing. */
data class WorkingContext(
    val project: String? = null,
    val objective: String? = null,
    val memories: Int = 0,
)

@HiltViewModel
class ChatViewModel @Inject constructor(
    private val webSocketClient: VoiceWebSocketClient,
    private val uploadClient: UploadClient,
    private val apiClient: ApiClient,
) : ViewModel(), VoiceWebSocketClient.VoiceWebSocketListener {

    val messages = mutableStateListOf<ChatMessage>()

    /** Conversation list for the sidebar: (id, title). */
    val conversations = mutableStateListOf<Pair<String, String>>()

    private val _isConnected = MutableStateFlow(false)
    val isConnected: StateFlow<Boolean> = _isConnected.asStateFlow()

    private val _isStreaming = MutableStateFlow(false)
    val isStreaming: StateFlow<Boolean> = _isStreaming.asStateFlow()

    /** While Beanie works, the conversation carries a compact context card —
     * composed from the same contract endpoints the web/desktop panels use. */
    private val _workingContext = MutableStateFlow<WorkingContext?>(null)
    val workingContext: StateFlow<WorkingContext?> = _workingContext.asStateFlow()

    var conversationId by mutableStateOf(webSocketClient.conversationId)
        private set

    private var streamingMessageId: String? = null

    /** Set when the user manually picks a conversation; while false the app
     * follows the owner's most recent conversation from ANY device. */
    private var userPickedConversation = false
    private var lastListRequestMs: Long = 0L

    init {
        webSocketClient.addListener(this)
        _isConnected.value = webSocketClient.isConnected()
    }

    fun connect() {
        viewModelScope.launch {
            webSocketClient.connectToSavedServer()
            _isConnected.value = webSocketClient.isConnected()
        }
    }

    fun disconnect() {
        webSocketClient.disconnect()
    }

    fun sendMessage(content: String) {
        val text = content.trim()
        if (text.isEmpty()) return

        // Optimistic user message.
        messages.add(ChatMessage(id = UUID.randomUUID().toString(), role = "user", content = text))
        fetchWorkingContext()
        webSocketClient.sendUserMessage(conversationId, text)
    }

    /** Compose the working-context card (review section 4). Every source is
     * optional; a slow/offline fetch simply leaves the card hidden. */
    private fun fetchWorkingContext() {
        viewModelScope.launch {
            val context = withContext(Dispatchers.Default) {
                var project: String? = null
                var objective: String? = null
                var memories = 0
                try {
                    apiClient.getBackendProjectsRaw()?.let { raw ->
                        val projects = JSONObject(raw).optJSONArray("projects")
                        if (projects != null && projects.length() > 0) {
                            val name = projects.optJSONObject(0)?.optString("name", "")?.trim().orEmpty()
                            if (name.isNotEmpty()) project = name
                        }
                    }
                } catch (_: Exception) {
                }
                try {
                    apiClient.getAutonomousGoals()?.let { raw ->
                        val goals = JSONObject(raw).optJSONArray("goals")
                        if (goals != null && goals.length() > 0) {
                            val title = goals.optJSONObject(0)?.optString("title", "")?.trim().orEmpty()
                            if (title.isNotEmpty()) objective = title
                        }
                    }
                } catch (_: Exception) {
                }
                try {
                    apiClient.memories()?.let { raw ->
                        val arr = JSONArray(raw)
                        memories = arr.length()
                    }
                } catch (_: Exception) {
                }
                WorkingContext(project = project, objective = objective, memories = memories)
            }
            if (context.project != null || context.objective != null || context.memories > 0) {
                _workingContext.value = context
            }
        }
    }

    fun newConversation() {
        webSocketClient.createConversation()
    }

    fun loadConversations() {
        webSocketClient.listConversations()
    }

    fun selectConversation(id: String, fromUser: Boolean = true) {
        if (fromUser) userPickedConversation = true
        if (id == conversationId) return
        conversationId = id
        // Join the room so messages from other devices stream to this one.
        webSocketClient.joinConversation(id)
        requestHistory()
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
        // Bind to the default conversation, then pull its history + the list.
        webSocketClient.requestHistory(conversationId)
        webSocketClient.listConversations()
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

    override fun onConversationList(conversations: List<Pair<String, String>>) {
        this.conversations.clear()
        this.conversations.addAll(conversations)
        if (conversations.isEmpty()) return
        // Follow the owner: until the user picks a conversation manually,
        // stay in the most recently active conversation from ANY device so
        // chats sync across web/desktop/Android.
        val newest = conversations.first().first
        if (!userPickedConversation && newest != conversationId) {
            selectConversation(newest, fromUser = false)
        } else if (conversationId.isBlank()) {
            conversationId = newest
            webSocketClient.requestHistory(conversationId)
        }
    }

    override fun onConversationActivity(conversationId: String) {
        // The owner chatted somewhere else — refresh the list (throttled) so
        // follow-the-newest kicks in without pulling every message burst.
        val now = System.currentTimeMillis()
        if (now - lastListRequestMs < 2000L) return
        lastListRequestMs = now
        webSocketClient.listConversations()
    }

    override fun onConversationHistory(conversationId: String, history: List<Triple<String, String, String>>) {
        if (conversationId != this.conversationId) return
        messages.clear()
        history.forEach { (messageId, role, content) ->
            // Server message ids keep hydrated rows matched against live tokens.
            messages.add(
                ChatMessage(
                    id = messageId.ifBlank { UUID.randomUUID().toString() },
                    role = role,
                    content = content
                )
            )
        }
    }

    override fun onRemoteMessage(conversationId: String, messageId: String, content: String) {
        // A user message sent from another device (web/desktop) — render it live.
        if (conversationId != this.conversationId || content.isBlank()) return
        if (messages.any { it.id == messageId || (it.role == "user" && it.content == content) }) return
        messages.add(ChatMessage(id = messageId.ifBlank { UUID.randomUUID().toString() }, role = "user", content = content))
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
            // Already fully hydrated from history (server persists the reply
            // before the stream finishes) — appending would duplicate text.
            if (!m.isStreaming && m.content.isNotBlank()) {
                if (done) streamingMessageId = null
                return
            }
            messages[idx] = m.copy(content = m.content + token, isStreaming = !done)
        }

        if (done) {
            streamingMessageId = null
            _workingContext.value = null
        }
    }

    override fun onActionStep(conversationId: String, messageId: String, label: String, status: String) {
        // Lightweight: append the step label to the streaming message's action steps.
        if (conversationId != this.conversationId || label.isBlank()) return
        val idx = messages.indexOfFirst { it.id == messageId }
        if (idx >= 0) {
            val m = messages[idx]
            val steps = if (m.actionSteps.any { it.label == label }) {
                m.actionSteps.map { if (it.label == label) it.copy(status = status) else it }
            } else {
                m.actionSteps + ToolActivity(label, status)
            }
            messages[idx] = m.copy(actionSteps = steps)
        } else {
            // Steps can arrive before the first token — create the bubble.
            messages.add(
                ChatMessage(
                    id = messageId,
                    role = "assistant",
                    content = "",
                    isStreaming = true,
                    actionSteps = listOf(ToolActivity(label, status))
                )
            )
            streamingMessageId = messageId
        }
    }

    override fun onChatError(message: String) {
        _isStreaming.value = false
        _workingContext.value = null
        Log.w(TAG, "Chat error: $message")
    }

    companion object {
        private const val TAG = "ChatViewModel"
    }
}
