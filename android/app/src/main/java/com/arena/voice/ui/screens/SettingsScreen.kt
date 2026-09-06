@file:OptIn(androidx.compose.material3.ExperimentalMaterial3Api::class)

package com.arena.voice.ui.screens

import androidx.compose.foundation.layout.*
import androidx.compose.foundation.rememberScrollState
import androidx.compose.foundation.verticalScroll
import androidx.compose.material3.*
import androidx.compose.runtime.*
import androidx.compose.ui.Modifier
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.unit.dp
import androidx.hilt.navigation.compose.hiltViewModel
import androidx.lifecycle.ViewModel
import androidx.lifecycle.viewModelScope
import com.arena.voice.api.ApiClient
import dagger.hilt.android.lifecycle.HiltViewModel
import kotlinx.coroutines.launch
import org.json.JSONArray
import org.json.JSONObject
import javax.inject.Inject

/**
 * Settings ViewModel — edits the BACKEND's shared settings (wake word, Piper
 * voice, voice speed, theme, language, VAD sensitivity, response delay), so the
 * Android app changes the SAME values the web + desktop apps edit.
 */
data class OwnerApproval(
    val actionId: String,
    val actionType: String,
    val reason: String,
    val payload: String,
)

data class OwnerAuthorization(
    val authorizationId: String,
    val actionType: String,
    val payload: String,
    val planId: String?,
    val expiresAt: String,
    val scopeRecoverable: Boolean,
)

data class OwnerPlanReview(
    val planId: String,
    val title: String,
    val revision: Int,
    val status: String,
    val steps: String,
)

data class OwnerExecution(
    val executionId: String,
    val actionType: String,
    val status: String,
    val rollbackSupported: Boolean,
)

data class OwnerGoal(
    val goalId: String,
    val title: String,
    val status: String,
    val priority: String,
)

data class OwnerSchedule(
    val scheduleId: String,
    val title: String,
    val status: String,
)

data class OwnerRunEvent(
    val cycleId: String,
    val stage: String,
    val createdAt: String,
)

data class OwnerPreemption(
    val preemptionId: String,
    val status: String,
)

data class OwnerQuestion(
    val questionId: String,
    val actionType: String,
    val questionText: String,
    val calibratedConfidence: Double,
)

data class InducedSkill(
    val candidateId: String,
    val skillName: String,
    val actionSequence: String,
    val occurrences: Int,
)

data class OwnerDecision(
    val decisionId: String,
    val status: String,
    val changeTypes: String,
)

@HiltViewModel
class SettingsViewModel @Inject constructor(
    private val api: ApiClient,
) : ViewModel() {
    var wakeWord by mutableStateOf("hey_arena")
    var voice by mutableStateOf("en_US-lessac-medium")
    var voiceSpeed by mutableStateOf("1.0")
    var theme by mutableStateOf("dark")
    var language by mutableStateOf("en_US")
    var voiceEnabled by mutableStateOf(true)
    var vadSensitivity by mutableStateOf("50")
    var responseDelay by mutableStateOf("500")

    var ownerMode by mutableStateOf("approve_every_action")
    var ownerPaused by mutableStateOf(false)
    var maxAutonomousSafety by mutableStateOf("0")
    var explorationBudget by mutableStateOf("0")
    var ownerApprovals by mutableStateOf<List<OwnerApproval>>(emptyList())
        private set
    var ownerAuthorizations by mutableStateOf<List<OwnerAuthorization>>(emptyList())
        private set
    var ownerPlans by mutableStateOf<List<OwnerPlanReview>>(emptyList())
        private set
    var selectedPlanId by mutableStateOf<String?>(null)
    var selectedPlanRevision by mutableStateOf(0)
    var planStepsJson by mutableStateOf("")
    var ownerExecutions by mutableStateOf<List<OwnerExecution>>(emptyList())
        private set
    var allowSensitiveAutonomy by mutableStateOf(false)
    var autonomyGoals by mutableStateOf<List<OwnerGoal>>(emptyList())
        private set
    var autonomySchedule by mutableStateOf<List<OwnerSchedule>>(emptyList())
        private set
    var autonomyRuns by mutableStateOf<List<OwnerRunEvent>>(emptyList())
        private set
    var autonomyPreemptions by mutableStateOf<List<OwnerPreemption>>(emptyList())
        private set
    var ownerDecisions by mutableStateOf<List<OwnerDecision>>(emptyList())
        private set
    var workerBudgetLabel by mutableStateOf("Measured worker budget: unknown")
        private set
    var directiveTitle by mutableStateOf("")
    var directivePriority by mutableStateOf("normal")
    var decisionTypesInput by mutableStateOf("")
    var charterMission by mutableStateOf("")
    var charterRevision by mutableStateOf(0)
    var ownerQuestionsList by mutableStateOf<List<OwnerQuestion>>(emptyList())
        private set
    var inducedSkillList by mutableStateOf<List<InducedSkill>>(emptyList())
        private set

    var piperVoices by mutableStateOf<List<String>>(emptyList())
        private set
    var loading by mutableStateOf(true)
        private set
    var status by mutableStateOf<String?>(null)
        private set

    init {
        load()
    }

    fun load() {
        loading = true
        viewModelScope.launch {
            // Shared settings
            api.getSharedSettings()?.let { raw ->
                runCatching {
                    val s = JSONObject(raw)
                    wakeWord = s.optString("wake_word", wakeWord)
                    voice = s.optString("voice", voice)
                    voiceSpeed = s.optDouble("voice_speed", voiceSpeed.toDouble()).toString()
                    theme = s.optString("theme", theme)
                    language = s.optString("language", language)
                    voiceEnabled = s.optBoolean("voice_enabled", true)
                    vadSensitivity = s.optInt("vad_sensitivity", vadSensitivity.toInt()).toString()
                    responseDelay = s.optInt("response_delay", responseDelay.toInt()).toString()
                }
            }
            // Piper voices
            api.listPiperVoices()?.let { raw ->
                runCatching {
                    val arr = JSONObject(raw).optJSONArray("voices") ?: JSONArray()
                    piperVoices = (0 until arr.length()).mapNotNull { i ->
                        arr.optJSONObject(i)?.optString("id")?.ifBlank { null }
                    }
                }
            }
            loadOwnerControlState()
            loadAutonomyState()
            loadCognitionState()
            loading = false
        }
    }

    private suspend fun loadOwnerControlState() {
        api.getOwnerControl()?.let { raw ->
            runCatching {
                val policy = JSONObject(raw).optJSONObject("policy") ?: JSONObject()
                ownerMode = policy.optString("mode", ownerMode)
                ownerPaused = policy.optBoolean("paused", false)
                maxAutonomousSafety = policy.optInt("max_autonomous_level", 0).toString()
                allowSensitiveAutonomy = policy.optBoolean("allow_sensitive_autonomy", false)
            }
        }
        api.getAdaptiveAutonomy()?.let { raw ->
            runCatching {
                val profile = JSONObject(raw).optJSONObject("profile") ?: JSONObject()
                explorationBudget = profile.optInt("owner_max_exploration_goals", 0).toString()
            }
        }
        api.getPendingApprovals()?.let { raw ->
            runCatching {
                val array = JSONObject(raw).optJSONArray("approvals") ?: JSONArray()
                ownerApprovals = (0 until array.length()).mapNotNull { index ->
                    array.optJSONObject(index)?.let { item ->
                        OwnerApproval(
                            item.optString("action_id"), item.optString("action_type"),
                            item.optString("reason"), item.optJSONObject("payload")?.toString(2) ?: "{}",
                        )
                    }
                }
            }
        }
        api.getAuthorizations()?.let { raw ->
            runCatching {
                val array = JSONObject(raw).optJSONArray("authorizations") ?: JSONArray()
                ownerAuthorizations = (0 until array.length()).mapNotNull { index ->
                    array.optJSONObject(index)?.let { item ->
                        OwnerAuthorization(
                            item.optString("authorization_id"), item.optString("action_type"),
                            item.optJSONObject("payload")?.toString(2) ?: "{}",
                            item.optString("plan_id").ifBlank { null }, item.optString("expires_at"),
                            item.optBoolean("scope_recoverable", false),
                        )
                    }
                }
            }
        }
        api.getReviewedPlans()?.let { raw ->
            runCatching {
                val array = JSONObject(raw).optJSONArray("plans") ?: JSONArray()
                ownerPlans = (0 until array.length()).mapNotNull { index ->
                    array.optJSONObject(index)?.let { item ->
                        OwnerPlanReview(
                            item.optString("plan_id"), item.optString("goal_title", item.optString("plan_id")),
                            item.optInt("revision"), item.optString("status"),
                            item.optJSONObject("snapshot")?.optJSONArray("steps")?.toString(2) ?: "[]",
                        )
                    }
                }
            }
        }
        api.getControlledExecutions()?.let { raw ->
            runCatching {
                val array = JSONObject(raw).optJSONArray("executions") ?: JSONArray()
                ownerExecutions = (0 until array.length()).mapNotNull { index ->
                    array.optJSONObject(index)?.let { item ->
                        OwnerExecution(
                            item.optString("execution_id"), item.optString("action_type"),
                            item.optString("status"),
                            item.optJSONObject("rollback_receipt")?.optBoolean("supported", false) ?: false,
                        )
                    }
                }
            }
        }
    }

    fun refreshOwnerControl() {
        viewModelScope.launch {
            loadOwnerControlState()
            loadAutonomyState()
            loadCognitionState()
            status = "Owner-control state refreshed"
        }
    }

    private suspend fun loadCognitionState() {
        api.getOwnerCharter()?.let { raw ->
            runCatching {
                val charter = JSONObject(raw).optJSONObject("charter") ?: JSONObject()
                charterMission = charter.optString("mission", charterMission)
                charterRevision = charter.optInt("revision", 0)
            }
        }
        api.getOwnerQuestions()?.let { raw ->
            runCatching {
                val arr = JSONObject(raw).optJSONArray("questions") ?: JSONArray()
                ownerQuestionsList = (0 until arr.length()).mapNotNull { i ->
                    arr.optJSONObject(i)?.let {
                        OwnerQuestion(it.optString("question_id"), it.optString("action_type"),
                            it.optString("question_text"), it.optDouble("calibrated_confidence", 0.0))
                    }
                }
            }
        }
        api.getInducedSkills()?.let { raw ->
            runCatching {
                val arr = JSONObject(raw).optJSONArray("candidates") ?: JSONArray()
                inducedSkillList = (0 until arr.length()).mapNotNull { i ->
                    arr.optJSONObject(i)?.let {
                        val seq = it.optJSONArray("action_sequence")
                        val joined = if (seq == null) "" else (0 until seq.length()).joinToString(" → ") { j -> seq.optString(j) }
                        InducedSkill(it.optString("candidate_id"), it.optString("skill_name"), joined,
                            it.optInt("occurrences", 0))
                    }
                }
            }
        }
    }

    fun saveCharter(mission: String) {
        viewModelScope.launch {
            status = if (api.updateOwnerCharter(mission, emptyList(), emptyList()) != null) {
                charterMission = mission
                "Charter saved; it informs every cycle and grants no authority"
            } else "Charter save failed"
            loadCognitionState()
        }
    }

    fun answerQuestion(question: OwnerQuestion, answer: String) {
        viewModelScope.launch {
            status = if (api.answerOwnerQuestion(question.questionId, answer) != null) {
                if (answer == "approve") "Exact approval created; nothing executed"
                else "Answer recorded: $answer"
            } else "Answer failed"
            loadCognitionState()
        }
    }

    fun decideInducedSkill(skill: InducedSkill, accept: Boolean) {
        viewModelScope.launch {
            status = if (accept && api.acceptInducedSkill(skill.candidateId) != null)
                "Skill accepted; execution still passes all gates"
            else if (!accept && api.rejectInducedSkill(skill.candidateId) != null)
                "Candidate rejected"
            else "Decision failed"
            loadCognitionState()
        }
    }

    private suspend fun loadAutonomyState() {
        api.getAutonomousGoals()?.let { raw ->
            runCatching {
                val arr = JSONObject(raw).optJSONArray("goals") ?: JSONArray()
                autonomyGoals = (0 until arr.length()).mapNotNull { i ->
                    arr.optJSONObject(i)?.let {
                        OwnerGoal(
                            it.optString("goal_id"), it.optString("title"),
                            it.optString("status"), it.optString("priority"),
                        )
                    }
                }
            }
        }
        api.getAutonomySchedule()?.let { raw ->
            runCatching {
                val arr = JSONObject(raw).optJSONArray("schedule") ?: JSONArray()
                autonomySchedule = (0 until arr.length()).mapNotNull { i ->
                    arr.optJSONObject(i)?.let {
                        OwnerSchedule(it.optString("schedule_id"), it.optString("title"), it.optString("status"))
                    }
                }
            }
        }
        api.getAutonomyRunEvents(50)?.let { raw ->
            runCatching {
                val arr = JSONObject(raw).optJSONArray("events") ?: JSONArray()
                autonomyRuns = (0 until arr.length()).mapNotNull { i ->
                    arr.optJSONObject(i)?.let {
                        OwnerRunEvent(it.optString("cycle_id"), it.optString("stage"), it.optString("created_at"))
                    }
                }
            }
        }
        api.getPreemptions()?.let { raw ->
            runCatching {
                val arr = JSONObject(raw).optJSONArray("preemptions") ?: JSONArray()
                autonomyPreemptions = (0 until arr.length()).mapNotNull { i ->
                    arr.optJSONObject(i)?.let {
                        OwnerPreemption(it.optString("preemption_id"), it.optString("status"))
                    }
                }
            }
        }
        api.getConcurrencyBudget()?.let { raw ->
            runCatching {
                val budget = JSONObject(raw).optJSONObject("budget") ?: JSONObject()
                workerBudgetLabel = "Measured worker budget: " + budget.optInt("workers_granted") +
                    " granted of " + budget.optInt("configured_budget") +
                    " (physical cap " + budget.optInt("physical_thread_cap") + ")"
            }
        }
        api.getOwnerDecisions()?.let { raw ->
            runCatching {
                val arr = JSONObject(raw).optJSONArray("decisions") ?: JSONArray()
                ownerDecisions = (0 until arr.length()).mapNotNull { i ->
                    arr.optJSONObject(i)?.let {
                        val types = it.optJSONObject("payload")?.optJSONArray("expected_change_types")
                        val joined = if (types == null) "" else (0 until types.length()).joinToString(",") { j -> types.optString(j) }
                        OwnerDecision(it.optString("decision_id"), it.optString("status"), joined)
                    }
                }
            }
        }
    }

    fun decideAutonomousGoal(goal: OwnerGoal, approved: Boolean) {
        viewModelScope.launch {
            status = if (api.decideAutonomousGoal(goal.goalId, approved) != null)
                "Goal decision recorded; planning only — execution stays separate" else "Goal decision failed"
            loadAutonomyState()
        }
    }

    fun deferAutonomousGoal(goal: OwnerGoal) {
        viewModelScope.launch {
            status = if (api.deferAutonomousGoal(goal.goalId) != null)
                "Goal deferred by owner priority" else "Defer failed"
            loadAutonomyState()
        }
    }

    fun executeNextAutonomousGoal() {
        viewModelScope.launch {
            status = if (api.executeNextAutonomousGoal() != null)
                "Execute-next issued; results require verification" else "Execute-next failed"
            loadAutonomyState()
        }
    }

    fun createDirective() {
        if (directiveTitle.isBlank()) {
            status = "Directive title is required"
            return
        }
        viewModelScope.launch {
            status = if (api.createAutonomousGoal(directiveTitle, "", directivePriority) != null) {
                directiveTitle = ""
                "Directive created; it authorizes planning only"
            } else "Create directive failed"
            loadAutonomyState()
        }
    }

    fun setScheduleStatus(schedule: OwnerSchedule, scheduleStatus: String) {
        viewModelScope.launch {
            status = if (api.updateScheduleStatus(schedule.scheduleId, scheduleStatus) != null)
                "Schedule $scheduleStatus" else "Schedule update failed"
            loadAutonomyState()
        }
    }

    fun reconcilePreemption(preemption: OwnerPreemption) {
        viewModelScope.launch {
            val raw = api.reconcilePreemption(preemption.preemptionId)
            status = if (raw != null) {
                val step = JSONObject(raw).optJSONObject("step_status_update")?.optString("status") ?: "?"
                "Reconciled; step now $step (nothing executed)"
            } else "Reconciliation failed"
            loadAutonomyState()
        }
    }

    fun requestPreemptionResume(preemption: OwnerPreemption) {
        viewModelScope.launch {
            status = if (api.requestPreemptionResume(preemption.preemptionId) != null)
                "Resume requested; separately execute the approved plan" else "Resume request failed"
            loadAutonomyState()
        }
    }

    fun applyWorkerBudget(enabled: Boolean, maxWorkers: Int?) {
        viewModelScope.launch {
            status = if (api.setConcurrencyBudget(enabled, maxWorkers) != null)
                "Owner worker budget updated (clamped to physical threads)" else "Budget update failed"
            loadAutonomyState()
        }
    }

    fun issueOwnerDecision() {
        val types = decisionTypesInput.split(",").map { it.trim() }.filter { it.isNotBlank() }
        if (types.isEmpty()) {
            status = "List at least one expected change type"
            return
        }
        viewModelScope.launch {
            status = if (api.issueOwnerDecision(types, "Android owner decision") != null) {
                decisionTypesInput = ""
                "Decision issued (single-use); pass its ID to the identity checkpoint"
            } else "Decision issue failed"
            loadAutonomyState()
        }
    }

    fun revokeOwnerDecision(decision: OwnerDecision) {
        viewModelScope.launch {
            status = if (api.revokeOwnerDecision(decision.decisionId) != null)
                "Decision revoked" else "Decision revoke failed"
            loadAutonomyState()
        }
    }

    fun saveOwnerPolicy() {
        viewModelScope.launch {
            val policy = api.updateOwnerControl(
                ownerMode, (maxAutonomousSafety.toIntOrNull() ?: 0).coerceIn(0, 3), allowSensitiveAutonomy
            )
            val budget = api.setExplorationBudget(
                (explorationBudget.toIntOrNull() ?: 0).coerceIn(0, 10)
            )
            status = if (policy != null && budget != null)
                "Policy saved; no action was authorized or executed" else "Could not save owner policy"
            loadOwnerControlState()
        }
    }

    fun toggleEmergencyPause() {
        viewModelScope.launch {
            status = if (api.setEmergencyPause(!ownerPaused) != null)
                "Emergency state updated" else "Could not update emergency state"
            loadOwnerControlState()
        }
    }

    fun decideApproval(approval: OwnerApproval, approved: Boolean) {
        viewModelScope.launch {
            status = if (api.decideApproval(approval.actionId, approved) != null) {
                if (approved) "Exact action authorized; nothing executed" else "Recommendation rejected"
            } else "Approval decision failed"
            loadOwnerControlState()
        }
    }

    fun executeAuthorization(authorization: OwnerAuthorization) {
        if (!authorization.scopeRecoverable) {
            status = "This grant has no recoverable reviewed payload; use the issuing client"
            return
        }
        viewModelScope.launch {
            val result = runCatching {
                api.executeAuthorized(
                    authorization.authorizationId, authorization.actionType,
                    JSONObject(authorization.payload), authorization.planId,
                )
            }.getOrNull()
            status = if (result != null) {
                val data = runCatching { JSONObject(result) }.getOrDefault(JSONObject())
                "Execution success=${data.optBoolean("execution_success", false)}, " +
                    "goal verified=${data.optBoolean("goal_verified", false)}, " +
                    "verification unknown=${data.optBoolean("verification_unknown", false)}"
            } else "Authorized execution failed"
            loadOwnerControlState()
        }
    }

    fun revokeAuthorization(authorization: OwnerAuthorization) {
        viewModelScope.launch {
            status = if (api.revokeAuthorization(authorization.authorizationId) != null)
                "Authorization revoked without execution" else "Authorization revocation failed"
            loadOwnerControlState()
        }
    }

    fun selectPlanForEditing(plan: OwnerPlanReview) {
        selectedPlanId = plan.planId
        selectedPlanRevision = plan.revision
        planStepsJson = plan.steps
        status = "Editing revision ${plan.revision}; saving creates a new unapproved revision"
    }

    fun savePlanEdits() {
        val planId = selectedPlanId ?: return
        val steps = runCatching { JSONArray(planStepsJson) }.getOrElse {
            status = "Plan steps must be a valid JSON array"
            return
        }
        if (steps.length() == 0) {
            status = "Plan steps cannot be empty"
            return
        }
        viewModelScope.launch {
            status = if (api.editPlan(planId, selectedPlanRevision, steps) != null)
                "Plan edits saved as a new revision; not approved or executed"
            else "Plan edit failed (revision may be stale or a started step immutable)"
            loadOwnerControlState()
        }
    }

    fun decidePlan(plan: OwnerPlanReview, approved: Boolean) {
        viewModelScope.launch {
            status = if (api.decidePlan(plan.planId, plan.revision, approved) != null)
                "Plan decision recorded; nothing executed" else "Plan decision failed"
            loadOwnerControlState()
        }
    }

    fun executePlan(plan: OwnerPlanReview) {
        viewModelScope.launch {
            status = if (api.executeApprovedPlan(plan.planId) != null)
                "Separate plan execution request completed" else "Plan execution failed"
            loadOwnerControlState()
        }
    }

    fun cancelExecution(execution: OwnerExecution) {
        viewModelScope.launch {
            status = if (api.cancelExecution(execution.executionId) != null)
                "Cooperative cancellation requested; prior side effects may exist" else "Cancellation failed"
            loadOwnerControlState()
        }
    }

    fun requestRollback(execution: OwnerExecution) {
        viewModelScope.launch {
            status = if (api.requestRollback(execution.executionId) != null)
                "Rollback compensation added to approvals; not executed" else "Rollback request failed"
            loadOwnerControlState()
        }
    }

    fun save() {
        status = "Saving…"
        viewModelScope.launch {
            val patch = JSONObject()
                .put("wake_word", wakeWord)
                .put("voice", voice)
                .put("voice_speed", voiceSpeed.toDoubleOrNull() ?: 1.0)
                .put("voice_enabled", voiceEnabled)
                .put("language", language)
                .put("vad_sensitivity", vadSensitivity.toIntOrNull() ?: 50)
                .put("response_delay", responseDelay.toIntOrNull() ?: 500)
                .put("theme", theme)
            val result = api.updateSharedSettings(patch)
            // Also make the backend's active Piper voice match.
            api.selectPiperVoice(voice)
            status = if (result != null) "✓ Saved" else "⚠ Could not save (backend offline?)"
        }
    }
}

@Composable
fun SettingsScreen(
    serverUrl: String,
    apiKey: String,
    onSaveServerUrl: (String) -> Unit,
    onSaveApiKey: (String) -> Unit,
    onSaveTheme: (String) -> Unit,
    viewModel: SettingsViewModel = hiltViewModel(),
) {
    var serverUrlInput by remember { mutableStateOf(serverUrl) }
    var apiKeyInput by remember { mutableStateOf(apiKey) }

    Column(
        modifier = Modifier
            .fillMaxSize()
            .verticalScroll(rememberScrollState())
            .padding(16.dp),
        verticalArrangement = Arrangement.spacedBy(14.dp),
    ) {
        Text("Settings", style = MaterialTheme.typography.titleLarge, fontWeight = FontWeight.SemiBold)

        // ── Connection (local DataStore) ──
        Text("Connection", style = MaterialTheme.typography.titleMedium, fontWeight = FontWeight.SemiBold)
        OutlinedTextField(
            value = serverUrlInput,
            onValueChange = { serverUrlInput = it },
            label = { Text("Server URL (ws://…)") },
            singleLine = true,
            modifier = Modifier.fillMaxWidth(),
        )
        OutlinedTextField(
            value = apiKeyInput,
            onValueChange = { apiKeyInput = it },
            label = { Text("API Key (optional)") },
            singleLine = true,
            modifier = Modifier.fillMaxWidth(),
        )
        Button(
            onClick = {
                onSaveServerUrl(serverUrlInput)
                onSaveApiKey(apiKeyInput)
            },
            modifier = Modifier.fillMaxWidth(),
        ) { Text("Save connection") }

        // ── Owner Control (backend authority, not local preferences) ──
        Divider()
        Text("Owner Control", style = MaterialTheme.typography.titleMedium, fontWeight = FontWeight.SemiBold)
        Text(
            "Approval authorizes only the exact recommendation. It does not execute it. " +
                "Plan execution, cancellation, and rollback are separate owner actions.",
            style = MaterialTheme.typography.bodySmall,
            color = MaterialTheme.colorScheme.onSurfaceVariant,
        )
        var ownerModeExpanded by remember { mutableStateOf(false) }
        ExposedDropdownMenuBox(
            expanded = ownerModeExpanded,
            onExpandedChange = { ownerModeExpanded = it },
        ) {
            OutlinedTextField(
                value = viewModel.ownerMode,
                onValueChange = {},
                readOnly = true,
                label = { Text("Authority mode") },
                trailingIcon = { ExposedDropdownMenuDefaults.TrailingIcon(ownerModeExpanded) },
                modifier = Modifier.fillMaxWidth().menuAnchor(),
            )
            ExposedDropdownMenu(
                expanded = ownerModeExpanded,
                onDismissRequest = { ownerModeExpanded = false },
            ) {
                listOf(
                    "observe_only", "suggest_only", "approve_every_action",
                    "approve_each_plan", "bounded_autonomy", "custom",
                ).forEach { mode ->
                    DropdownMenuItem(
                        text = { Text(mode) },
                        onClick = { viewModel.ownerMode = mode; ownerModeExpanded = false },
                    )
                }
            }
        }
        Row(horizontalArrangement = Arrangement.spacedBy(8.dp)) {
            OutlinedTextField(
                value = viewModel.maxAutonomousSafety,
                onValueChange = { viewModel.maxAutonomousSafety = it },
                label = { Text("Safety ceiling 0–3") },
                singleLine = true,
                modifier = Modifier.weight(1f),
            )
            OutlinedTextField(
                value = viewModel.explorationBudget,
                onValueChange = { viewModel.explorationBudget = it },
                label = { Text("Exploration 0–10") },
                singleLine = true,
                modifier = Modifier.weight(1f),
            )
        }
        Row(
            horizontalArrangement = Arrangement.spacedBy(8.dp),
            verticalAlignment = androidx.compose.ui.Alignment.CenterVertically,
        ) {
            Switch(
                checked = viewModel.allowSensitiveAutonomy,
                onCheckedChange = { viewModel.allowSensitiveAutonomy = it },
            )
            Column {
                Text("Delegate sensitive (Level 3) autonomy", fontWeight = FontWeight.SemiBold)
                Text(
                    "Off clamps autonomous execution to Level 2; on allows Level 3 under your policy.",
                    style = MaterialTheme.typography.bodySmall
                )
            }
        }
        Row(horizontalArrangement = Arrangement.spacedBy(8.dp)) {
            Button(onClick = { viewModel.saveOwnerPolicy() }, modifier = Modifier.weight(1f)) {
                Text("Save policy")
            }
            Button(
                onClick = { viewModel.toggleEmergencyPause() },
                colors = ButtonDefaults.buttonColors(
                    containerColor = if (viewModel.ownerPaused) MaterialTheme.colorScheme.primary
                    else MaterialTheme.colorScheme.error
                ),
                modifier = Modifier.weight(1f),
            ) { Text(if (viewModel.ownerPaused) "Resume" else "Emergency pause") }
        }
        OutlinedButton(
            onClick = { viewModel.refreshOwnerControl() }, modifier = Modifier.fillMaxWidth()
        ) { Text("Refresh Owner Control") }

        Text("Pending exact-action approvals", fontWeight = FontWeight.SemiBold)
        if (viewModel.ownerApprovals.isEmpty()) {
            Text("None", style = MaterialTheme.typography.bodySmall)
        }
        viewModel.ownerApprovals.forEach { approval ->
            Card(modifier = Modifier.fillMaxWidth()) {
                Column(Modifier.padding(12.dp), verticalArrangement = Arrangement.spacedBy(6.dp)) {
                    Text(approval.actionType, fontWeight = FontWeight.SemiBold)
                    Text(approval.reason, style = MaterialTheme.typography.bodySmall)
                    Text(approval.payload, style = MaterialTheme.typography.bodySmall)
                    Row(horizontalArrangement = Arrangement.spacedBy(8.dp)) {
                        Button(
                            onClick = { viewModel.decideApproval(approval, true) },
                            modifier = Modifier.weight(1f),
                        ) { Text("Authorize only") }
                        OutlinedButton(
                            onClick = { viewModel.decideApproval(approval, false) },
                            modifier = Modifier.weight(1f),
                        ) { Text("Reject") }
                    }
                }
            }
        }

        Text("Active exact-scope authorizations", fontWeight = FontWeight.SemiBold)
        viewModel.ownerAuthorizations.forEach { authorization ->
            Card(modifier = Modifier.fillMaxWidth()) {
                Column(Modifier.padding(12.dp), verticalArrangement = Arrangement.spacedBy(6.dp)) {
                    Text("${authorization.actionType} · expires ${authorization.expiresAt}")
                    if (authorization.scopeRecoverable) {
                        Text(authorization.payload, style = MaterialTheme.typography.bodySmall)
                    } else {
                        Text(
                            "Exact payload is retained only by the issuing client.",
                            style = MaterialTheme.typography.bodySmall,
                        )
                    }
                    Row(horizontalArrangement = Arrangement.spacedBy(6.dp)) {
                        Button(
                            onClick = { viewModel.executeAuthorization(authorization) },
                            enabled = authorization.scopeRecoverable,
                            modifier = Modifier.weight(1f),
                        ) { Text("Execute exact scope") }
                        OutlinedButton(
                            onClick = { viewModel.revokeAuthorization(authorization) },
                            modifier = Modifier.weight(1f),
                        ) { Text("Revoke") }
                    }
                }
            }
        }

        Text("Plan reviews", fontWeight = FontWeight.SemiBold)
        viewModel.ownerPlans.forEach { plan ->
            Card(modifier = Modifier.fillMaxWidth()) {
                Column(Modifier.padding(12.dp), verticalArrangement = Arrangement.spacedBy(6.dp)) {
                    Text("${plan.title} [${plan.status}] r${plan.revision}")
                    OutlinedButton(
                        onClick = { viewModel.selectPlanForEditing(plan) },
                        enabled = plan.status == "pending",
                        modifier = Modifier.fillMaxWidth(),
                    ) { Text("Edit exact plan steps JSON") }
                    Row(horizontalArrangement = Arrangement.spacedBy(6.dp)) {
                        OutlinedButton(
                            onClick = { viewModel.decidePlan(plan, true) },
                            enabled = plan.status == "pending",
                            modifier = Modifier.weight(1f),
                        ) { Text("Approve") }
                        OutlinedButton(
                            onClick = { viewModel.decidePlan(plan, false) },
                            enabled = plan.status == "pending",
                            modifier = Modifier.weight(1f),
                        ) { Text("Reject") }
                    }
                    if (plan.status == "approved") {
                        Button(
                            onClick = { viewModel.executePlan(plan) }, modifier = Modifier.fillMaxWidth()
                        ) { Text("Execute approved plan separately") }
                    }
                }
            }
        }

        viewModel.selectedPlanId?.let { planId ->
            OutlinedTextField(
                value = viewModel.planStepsJson,
                onValueChange = { viewModel.planStepsJson = it },
                label = { Text("Plan $planId steps JSON") },
                minLines = 5,
                modifier = Modifier.fillMaxWidth(),
            )
            Button(
                onClick = { viewModel.savePlanEdits() }, modifier = Modifier.fillMaxWidth()
            ) { Text("Save as new unapproved revision") }
        }

        Text("Execution control", fontWeight = FontWeight.SemiBold)
        viewModel.ownerExecutions.take(20).forEach { execution ->
            Card(modifier = Modifier.fillMaxWidth()) {
                Column(Modifier.padding(12.dp), verticalArrangement = Arrangement.spacedBy(6.dp)) {
                    Text("${execution.actionType} [${execution.status}]")
                    Row(horizontalArrangement = Arrangement.spacedBy(6.dp)) {
                        OutlinedButton(
                            onClick = { viewModel.cancelExecution(execution) },
                            enabled = execution.status == "running",
                            modifier = Modifier.weight(1f),
                        ) { Text("Cancel") }
                        OutlinedButton(
                            onClick = { viewModel.requestRollback(execution) },
                            enabled = execution.rollbackSupported,
                            modifier = Modifier.weight(1f),
                        ) { Text("Request rollback") }
                    }
                }
            }
        }

        Divider()
        // ── Autonomy operations (goal queue, schedule, runs, preemptions, budgets, decisions) ──
        Text("Autonomy operations", style = MaterialTheme.typography.titleMedium, fontWeight = FontWeight.SemiBold)
        Text(
            "Goal decisions authorize planning only. Execution, resume, and rollback stay separate actions.",
            style = MaterialTheme.typography.bodySmall
        )
        Text("Measured budget: ${viewModel.workerBudgetLabel}", style = MaterialTheme.typography.bodySmall)
        Row(horizontalArrangement = Arrangement.spacedBy(6.dp)) {
            OutlinedButton(onClick = { viewModel.applyWorkerBudget(true, null) }, modifier = Modifier.weight(1f)) {
                Text("Reset to measured")
            }
            OutlinedButton(onClick = { viewModel.executeNextAutonomousGoal() }, modifier = Modifier.weight(1f)) {
                Text("Execute next approved goal")
            }
        }
        OutlinedTextField(
            value = viewModel.directiveTitle,
            onValueChange = { viewModel.directiveTitle = it },
            label = { Text("Directive title (planning only)") },
            singleLine = true,
            modifier = Modifier.fillMaxWidth(),
        )
        Row(horizontalArrangement = Arrangement.spacedBy(6.dp)) {
            val priorities = listOf("critical", "high", "normal", "low")
            var priorityExpanded by remember { mutableStateOf(false) }
            ExposedDropdownMenuBox(
                expanded = priorityExpanded,
                onExpandedChange = { priorityExpanded = it },
            ) {
                OutlinedTextField(
                    value = viewModel.directivePriority,
                    onValueChange = { },
                    readOnly = true,
                    label = { Text("Priority") },
                    singleLine = true,
                    modifier = Modifier.fillMaxWidth().menuAnchor(),
                )
                DropdownMenu(expanded = priorityExpanded, onDismissRequest = { priorityExpanded = false }) {
                    priorities.forEach { priority ->
                        DropdownMenuItem(
                            text = { Text(priority) },
                            onClick = {
                                viewModel.directivePriority = priority
                                priorityExpanded = false
                            }
                        )
                    }
                }
            }
            Button(onClick = { viewModel.createDirective() }, modifier = Modifier.weight(1f)) {
                Text("Create directive")
            }
        }
        viewModel.autonomyGoals.take(10).forEach { goal ->
            Card(modifier = Modifier.fillMaxWidth()) {
                Column(Modifier.padding(12.dp), verticalArrangement = Arrangement.spacedBy(6.dp)) {
                    Text("${goal.title} [${goal.status}/${goal.priority}]")
                    Row(horizontalArrangement = Arrangement.spacedBy(6.dp)) {
                        OutlinedButton(
                            onClick = { viewModel.decideAutonomousGoal(goal, true) },
                            modifier = Modifier.weight(1f),
                        ) { Text("Approve for planning") }
                        OutlinedButton(
                            onClick = { viewModel.decideAutonomousGoal(goal, false) },
                            modifier = Modifier.weight(1f),
                        ) { Text("Reject") }
                        OutlinedButton(
                            onClick = { viewModel.deferAutonomousGoal(goal) },
                            modifier = Modifier.weight(1f),
                        ) { Text("Defer") }
                    }
                }
            }
        }
        viewModel.autonomySchedule.take(10).forEach { schedule ->
            Card(modifier = Modifier.fillMaxWidth()) {
                Column(Modifier.padding(12.dp), verticalArrangement = Arrangement.spacedBy(6.dp)) {
                    Text("Schedule: ${schedule.title} [${schedule.status}]")
                    Row(horizontalArrangement = Arrangement.spacedBy(6.dp)) {
                        OutlinedButton(
                            onClick = { viewModel.setScheduleStatus(schedule, "paused") },
                            enabled = schedule.status != "paused",
                            modifier = Modifier.weight(1f),
                        ) { Text("Pause") }
                        OutlinedButton(
                            onClick = { viewModel.setScheduleStatus(schedule, "active") },
                            enabled = schedule.status == "paused",
                            modifier = Modifier.weight(1f),
                        ) { Text("Resume") }
                    }
                }
            }
        }
        viewModel.autonomyRuns.take(10).forEach { run ->
            Card(modifier = Modifier.fillMaxWidth()) {
                Text(
                    "Run ${run.cycleId.take(16)} ${run.stage} ${run.createdAt.take(19)}",
                    modifier = Modifier.padding(12.dp)
                )
            }
        }
        Text("Preemptions — reconcile before resume; verified steps are skipped, unknown halts for evidence", style = MaterialTheme.typography.bodySmall)
        viewModel.autonomyPreemptions.take(10).forEach { preemption ->
            Card(modifier = Modifier.fillMaxWidth()) {
                Column(Modifier.padding(12.dp), verticalArrangement = Arrangement.spacedBy(6.dp)) {
                    Text("${preemption.preemptionId.take(20)} [${preemption.status}]")
                    Row(horizontalArrangement = Arrangement.spacedBy(6.dp)) {
                        OutlinedButton(
                            onClick = { viewModel.reconcilePreemption(preemption) },
                            modifier = Modifier.weight(1f),
                        ) { Text("Reconcile") }
                        OutlinedButton(
                            onClick = { viewModel.requestPreemptionResume(preemption) },
                            modifier = Modifier.weight(1f),
                        ) { Text("Request resume") }
                    }
                }
            }
        }
        Text("Signed owner decisions (expected identity changes; single-use, revocable)", style = MaterialTheme.typography.bodySmall)
        OutlinedTextField(
            value = viewModel.decisionTypesInput,
            onValueChange = { viewModel.decisionTypesInput = it },
            label = { Text("Expected change types, comma separated") },
            singleLine = true,
            modifier = Modifier.fillMaxWidth(),
        )
        Button(onClick = { viewModel.issueOwnerDecision() }, modifier = Modifier.fillMaxWidth()) {
            Text("Issue decision")
        }
        viewModel.ownerDecisions.take(10).forEach { decision ->
            Card(modifier = Modifier.fillMaxWidth()) {
                Column(Modifier.padding(12.dp), verticalArrangement = Arrangement.spacedBy(6.dp)) {
                    Text("${decision.decisionId.take(18)} [${decision.status}] ${decision.changeTypes}")
                    OutlinedButton(
                        onClick = { viewModel.revokeOwnerDecision(decision) },
                        enabled = decision.status == "active",
                    ) { Text("Revoke") }
                }
            }
        }

        Divider()
        // ── Cognition (charter, questions, induced skills) ──
        Text("Cognition", style = MaterialTheme.typography.titleMedium, fontWeight = FontWeight.SemiBold)
        Text(
            "Charter revision ${viewModel.charterRevision}. Your values inform every cycle; policy gates remain the authority.",
            style = MaterialTheme.typography.bodySmall
        )
        OutlinedTextField(
            value = viewModel.charterMission,
            onValueChange = { viewModel.charterMission = it },
            label = { Text("Charter mission") },
            minLines = 2,
            modifier = Modifier.fillMaxWidth(),
        )
        Button(onClick = { viewModel.saveCharter(viewModel.charterMission) }, modifier = Modifier.fillMaxWidth()) {
            Text("Save charter")
        }
        viewModel.ownerQuestionsList.take(5).forEach { question ->
            Card(modifier = Modifier.fillMaxWidth()) {
                Column(Modifier.padding(12.dp), verticalArrangement = Arrangement.spacedBy(6.dp)) {
                    Text(question.questionText.take(160))
                    Row(horizontalArrangement = Arrangement.spacedBy(6.dp)) {
                        OutlinedButton(
                            onClick = { viewModel.answerQuestion(question, "approve") },
                            modifier = Modifier.weight(1f),
                        ) { Text("Approve exactly") }
                        OutlinedButton(
                            onClick = { viewModel.answerQuestion(question, "deny") },
                            modifier = Modifier.weight(1f),
                        ) { Text("Deny") }
                    }
                }
            }
        }
        viewModel.inducedSkillList.take(5).forEach { skill ->
            Card(modifier = Modifier.fillMaxWidth()) {
                Column(Modifier.padding(12.dp), verticalArrangement = Arrangement.spacedBy(6.dp)) {
                    Text("${skill.skillName} (${skill.occurrences}x)")
                    Text(skill.actionSequence, style = MaterialTheme.typography.bodySmall)
                    Row(horizontalArrangement = Arrangement.spacedBy(6.dp)) {
                        OutlinedButton(
                            onClick = { viewModel.decideInducedSkill(skill, true) },
                            modifier = Modifier.weight(1f),
                        ) { Text("Accept skill") }
                        OutlinedButton(
                            onClick = { viewModel.decideInducedSkill(skill, false) },
                            modifier = Modifier.weight(1f),
                        ) { Text("Reject") }
                    }
                }
            }
        }

        Divider()
        // ── Voice (backend shared settings) ──
        Text("Voice", style = MaterialTheme.typography.titleMedium, fontWeight = FontWeight.SemiBold)
        if (viewModel.loading) {
            CircularProgressIndicator()
        } else {
            OutlinedTextField(
                value = viewModel.wakeWord,
                onValueChange = { viewModel.wakeWord = it },
                label = { Text("Wake word") },
                singleLine = true,
                modifier = Modifier.fillMaxWidth(),
            )

            // Piper voice dropdown.
            var voiceExpanded by remember { mutableStateOf(false) }
            ExposedDropdownMenuBox(
                expanded = voiceExpanded,
                onExpandedChange = { voiceExpanded = it },
            ) {
                OutlinedTextField(
                    value = viewModel.voice,
                    onValueChange = { viewModel.voice = it },
                    label = { Text("Voice (Piper)") },
                    singleLine = true,
                    modifier = Modifier
                        .fillMaxWidth()
                        .menuAnchor(),
                    trailingIcon = { ExposedDropdownMenuDefaults.TrailingIcon(expanded = voiceExpanded) },
                )
                ExposedDropdownMenu(
                    expanded = voiceExpanded,
                    onDismissRequest = { voiceExpanded = false },
                ) {
                    viewModel.piperVoices.forEach { id ->
                        DropdownMenuItem(text = { Text(id) }, onClick = {
                            viewModel.voice = id
                            voiceExpanded = false
                        })
                    }
                }
            }

            OutlinedTextField(
                value = viewModel.voiceSpeed,
                onValueChange = { viewModel.voiceSpeed = it },
                label = { Text("Voice speed (0.5–2.0)") },
                singleLine = true,
                modifier = Modifier.fillMaxWidth(),
            )

            var languageExpanded by remember { mutableStateOf(false) }
            ExposedDropdownMenuBox(
                expanded = languageExpanded,
                onExpandedChange = { languageExpanded = it },
            ) {
                OutlinedTextField(
                    value = viewModel.language,
                    onValueChange = { viewModel.language = it },
                    label = { Text("Language") },
                    singleLine = true,
                    modifier = Modifier
                        .fillMaxWidth()
                        .menuAnchor(),
                    trailingIcon = { ExposedDropdownMenuDefaults.TrailingIcon(expanded = languageExpanded) },
                )
                ExposedDropdownMenu(
                    expanded = languageExpanded,
                    onDismissRequest = { languageExpanded = false },
                ) {
                    listOf("en_US", "en_GB", "es_ES", "fr_FR", "de_DE", "it_IT", "pt_PT", "nl_NL").forEach { lang ->
                        DropdownMenuItem(text = { Text(lang) }, onClick = {
                            viewModel.language = lang
                            languageExpanded = false
                        })
                    }
                }
            }

            Row(verticalAlignment = androidx.compose.ui.Alignment.CenterVertically) {
                Text("Voice enabled", modifier = Modifier.weight(1f))
                Switch(checked = viewModel.voiceEnabled, onCheckedChange = { viewModel.voiceEnabled = it })
            }

            OutlinedTextField(
                value = viewModel.vadSensitivity,
                onValueChange = { viewModel.vadSensitivity = it },
                label = { Text("VAD sensitivity (0–100)") },
                singleLine = true,
                modifier = Modifier.fillMaxWidth(),
            )
            OutlinedTextField(
                value = viewModel.responseDelay,
                onValueChange = { viewModel.responseDelay = it },
                label = { Text("Response delay (ms)") },
                singleLine = true,
                modifier = Modifier.fillMaxWidth(),
            )
        }

        // ── Appearance ──
        Text("Appearance", style = MaterialTheme.typography.titleMedium, fontWeight = FontWeight.SemiBold)
        var themeExpanded by remember { mutableStateOf(false) }
        ExposedDropdownMenuBox(
            expanded = themeExpanded,
            onExpandedChange = { themeExpanded = it },
        ) {
            OutlinedTextField(
                value = viewModel.theme,
                onValueChange = { viewModel.theme = it },
                label = { Text("Theme") },
                singleLine = true,
                modifier = Modifier
                    .fillMaxWidth()
                    .menuAnchor(),
                trailingIcon = { ExposedDropdownMenuDefaults.TrailingIcon(expanded = themeExpanded) },
            )
            ExposedDropdownMenu(
                    expanded = themeExpanded,
                    onDismissRequest = { themeExpanded = false },
                ) {
                    listOf("dark", "light", "system").forEach { t ->
                        DropdownMenuItem(text = { Text(t) }, onClick = {
                            viewModel.theme = t
                            themeExpanded = false
                        })
                    }
                }
        }

        Button(
            onClick = {
                viewModel.save()
                onSaveTheme(viewModel.theme)
            },
            modifier = Modifier.fillMaxWidth(),
        ) { Text("Save settings") }

        viewModel.status?.let { Text(it, color = MaterialTheme.colorScheme.onSurfaceVariant) }
    }
}
