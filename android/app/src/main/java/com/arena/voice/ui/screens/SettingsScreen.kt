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
            loading = false
        }
    }

    private suspend fun loadOwnerControlState() {
        api.getOwnerControl()?.let { raw ->
            runCatching {
                val policy = JSONObject(raw).optJSONObject("policy") ?: JSONObject()
                ownerMode = policy.optString("mode", ownerMode)
                ownerPaused = policy.optBoolean("paused", false)
                maxAutonomousSafety = policy.optInt("max_autonomous_safety_level", 0).toString()
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
            status = "Owner-control state refreshed"
        }
    }

    fun saveOwnerPolicy() {
        viewModelScope.launch {
            val policy = api.updateOwnerControl(
                ownerMode, (maxAutonomousSafety.toIntOrNull() ?: 0).coerceIn(0, 2)
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
                label = { Text("Safety ceiling 0–2") },
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
