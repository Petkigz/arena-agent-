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
    /** The exact cognitive trace this reply was persisted with. Blank = an
     * unlinked reply (older messages, or a failed cycle) — intentionally
     * unreviewable, never guessable. */
    val traceId: String = "",
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

    // ── Response review (Phase 1.4 evidence; same endpoints/stores as web/desktop) ──
    // Value domains enforced by the backend models (app/main.py) — validated
    // locally too so an invalid review fails fast without a round trip.
    val usefulnessLevels = listOf("helpful", "partially_helpful", "not_helpful")
    val taskOutcomes = listOf("success", "failure", "unknown")

    // Retry identity per trace: the SAME id is reused until the backend
    // returns its matching receipt, so a flaky network can never inflate
    // evidence counts (the web/desktop contract; ids start with "android-").
    private val usefulnessSubmissionIds = mutableMapOf<String, String>()
    private val evaluationSubmissionIds = mutableMapOf<String, String>()

    private fun submissionId(map: MutableMap<String, String>, traceId: String): String =
        map.getOrPut(traceId) { "android-${UUID.randomUUID()}" }

    /** Owner usefulness feedback for one exact trace. Feeds the existing
     * bounded strategy-learning path; changes no correctness state. */
    fun recordUsefulness(traceId: String, usefulness: String, note: String, onResult: (Boolean, String) -> Unit) {
        if (traceId.isBlank()) {
            onResult(false, "This reply carries no trace — it cannot be reviewed.")
            return
        }
        if (usefulness !in usefulnessLevels) {
            onResult(false, "Usefulness must be one of: ${usefulnessLevels.joinToString()}")
            return
        }
        viewModelScope.launch {
            val sid = submissionId(usefulnessSubmissionIds, traceId)
            val raw = apiClient.recordTraceUsefulness(traceId, usefulness, note.trim(), sid)
            val receipt = runCatching {
                JSONObject(raw ?: "{}").optJSONObject("feedback")?.optString("feedback_id").orEmpty()
            }.getOrDefault("")
            val ok = receipt.isNotBlank()
            if (ok) usefulnessSubmissionIds.remove(traceId) // durable: next review gets a fresh identity
            onResult(ok, if (ok) "Saved ✓" else "Not saved — retry the same rating.")
        }
    }

    /** Owner-recorded task evaluation. MEASUREMENT ONLY: recorded against the
     * exact trace; it never changes runtime truth, authorizes work, or
     * approves training. */
    fun recordTaskEvaluation(
        traceId: String,
        taskKey: String,
        observedOutcome: String,
        correctionReceived: Boolean,
        note: String,
        onResult: (Boolean, String) -> Unit,
    ) {
        if (traceId.isBlank()) {
            onResult(false, "This reply carries no trace — it cannot be reviewed.")
            return
        }
        val key = taskKey.trim()
        if (key.isEmpty()) {
            onResult(false, "A task key is required to record an evaluation.")
            return
        }
        if (observedOutcome !in taskOutcomes) {
            onResult(false, "Observed outcome must be one of: ${taskOutcomes.joinToString()}")
            return
        }
        viewModelScope.launch {
            val sid = submissionId(evaluationSubmissionIds, traceId)
            val payload = JSONObject()
                .put("task_key", key)
                .put("trace_id", traceId)
                .put("observed_outcome", observedOutcome)
                .put("usefulness", "unknown")
                .put("split", "held_out")
                .put("condition", "single")
                .put("correction_received", correctionReceived)
                .put("evidence_ids", JSONArray())
                .put("note", note.trim())
                .put("submission_id", sid)
            val raw = apiClient.recordTaskEvaluation(payload)
            val receipt = runCatching {
                JSONObject(raw ?: "{}").optJSONObject("evaluation")?.optString("evaluation_id").orEmpty()
            }.getOrDefault("")
            val ok = receipt.isNotBlank()
            if (ok) evaluationSubmissionIds.remove(traceId)
            onResult(ok, if (ok) "Evaluation saved ✓" else "Not saved — retry the same submission.")
        }
    }

    /** What is already recorded for this trace (absence stays explicit). */
    fun loadFeedbackSummary(traceId: String, onResult: (Pair<Int, Int>?) -> Unit) {
        if (traceId.isBlank()) {
            onResult(null)
            return
        }
        viewModelScope.launch {
            var feedback = -1
            var evaluations = 0
            runCatching {
                feedback = JSONObject(apiClient.traceUsefulness(traceId) ?: "{}")
                    .optJSONArray("feedback")?.length() ?: 0
                evaluations = JSONObject(apiClient.traceTaskEvaluations(traceId) ?: "{}")
                    .optJSONArray("evaluations")?.length() ?: 0
            }
            onResult(if (feedback < 0) null else Pair(feedback, evaluations))
        }
    }

    /** Grounded "why this response": the persisted trace facts via the
     * existing introspection endpoint — never a model self-narration. */
    fun fetchExplanation(traceId: String, onResult: (List<String>, Boolean) -> Unit) {
        if (traceId.isBlank()) {
            onResult(listOf("This reply carries no trace to explain."), false)
            return
        }
        viewModelScope.launch {
            val raw = apiClient.responseExplanation(traceId)
            val fallback = Pair(listOf("No trace explanation was returned."), false)
            val parsed = runCatching {
                val obj = JSONObject(raw ?: "{}")
                val lines = mutableListOf<String>()
                val arr = obj.optJSONArray("explanation")
                if (arr != null) {
                    for (i in 0 until arr.length()) {
                        lines.add(arr.optString(i))
                    }
                }
                val verified = obj.optJSONObject("facts")?.optBoolean("goal_verified", false) ?: false
                Pair(lines, verified)
            }.getOrDefault(fallback)
            onResult(parsed.first, parsed.second)
        }
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

    override fun onConversationHistory(conversationId: String, history: List<HistoryMessage>) {
        if (conversationId != this.conversationId) return
        messages.clear()
        history.forEach { m ->
            // Server message ids keep hydrated rows matched against live tokens;
            // trace ids enable the Review-response bar on linked replies only.
            messages.add(
                ChatMessage(
                    id = m.messageId.ifBlank { UUID.randomUUID().toString() },
                    role = m.role,
                    content = m.content,
                    traceId = m.traceId,
                )
            )
        }
    }

    override fun onCognitiveMetadata(conversationId: String, messageId: String, traceId: String) {
        // The just-persisted reply carries its exact trace — bind it to the
        // streamed message so the review bar can appear. A blank trace means
        // the cycle failed to persist one; the reply stays unreviewable.
        if (conversationId != this.conversationId || traceId.isBlank()) return
        val idx = messages.indexOfFirst { it.id == messageId }
        if (idx >= 0) {
            messages[idx] = messages[idx].copy(traceId = traceId)
        }
        // A miss (frame raced a re-hydration) is left alone: the next history
        // pull carries the durable trace — we never guess a binding.
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
