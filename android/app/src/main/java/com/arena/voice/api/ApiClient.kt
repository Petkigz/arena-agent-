package com.arena.voice.api

import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.flow.first
import kotlinx.coroutines.withContext
import okhttp3.MediaType.Companion.toMediaTypeOrNull
import okhttp3.MultipartBody
import okhttp3.OkHttpClient
import okhttp3.Request
import okhttp3.RequestBody.Companion.toRequestBody
import org.json.JSONArray
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
                val requestBody = (body ?: "{}").toRequestBody("application/json".toMediaTypeOrNull())
                when (method) {
                    "POST" -> builder.post(requestBody)
                    "PUT" -> builder.put(requestBody)
                    "DELETE" -> builder.delete(if (body == null) null else requestBody)
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

    // ── owner control plane ─────────────────────────────────────────────────
    private fun segment(value: String): String =
        java.net.URLEncoder.encode(value, "UTF-8").replace("+", "%20")

    suspend fun getOwnerControl(): String? = call("/owner-control")
    suspend fun updateOwnerControl(
        mode: String,
        maxSafetyLevel: Int,
        allowSensitiveAutonomy: Boolean? = null,
    ): String? {
        val body = JSONObject().put("mode", mode).put("max_autonomous_level", maxSafetyLevel)
        if (allowSensitiveAutonomy != null) body.put("allow_sensitive_autonomy", allowSensitiveAutonomy)
        return call("/owner-control", "PUT", body.toString())
    }
    suspend fun setEmergencyPause(paused: Boolean): String? =
        call("/owner-control/pause", "POST", JSONObject().put("paused", paused).toString())
    suspend fun getAdaptiveAutonomy(): String? = call("/owner-control/adaptive-autonomy")
    suspend fun setExplorationBudget(maximum: Int): String? =
        call(
            "/owner-control/adaptive-autonomy/exploration-budget", "PUT",
            JSONObject().put("max_exploration_goals", maximum).toString(),
        )
    suspend fun getPendingApprovals(): String? = call("/owner-control/approvals")
    suspend fun decideApproval(actionId: String, approved: Boolean): String? =
        call(
            "/owner-control/approvals/${segment(actionId)}/decision", "POST",
            JSONObject().put("approved", approved).put("note", "Android owner decision")
                .put("ttl_seconds", 300).toString(),
        )
    suspend fun getAuthorizations(): String? = call("/owner-control/authorizations")
    suspend fun executeAuthorized(
        authorizationId: String,
        actionType: String,
        payload: JSONObject,
        planId: String?,
    ): String? = call(
        "/owner-control/execute-authorized", "POST",
        JSONObject().put("authorization_id", authorizationId)
            .put("action_type", actionType).put("payload", payload)
            .put("user_text", "Android owner-authorized action")
            .put("complexity", "fast").put("plan_id", planId).toString(),
    )
    suspend fun revokeAuthorization(authorizationId: String): String? =
        call("/owner-control/authorizations/${segment(authorizationId)}", "DELETE")
    suspend fun getReviewedPlans(): String? = call("/owner-control/plans")
    suspend fun editPlan(planId: String, revision: Int, steps: JSONArray): String? =
        call(
            "/owner-control/plans/${segment(planId)}", "PUT",
            JSONObject().put("expected_revision", revision).put("steps", steps).toString(),
        )
    suspend fun decidePlan(planId: String, revision: Int, approved: Boolean): String? =
        call(
            "/owner-control/plans/${segment(planId)}/decision", "POST",
            JSONObject().put("expected_revision", revision).put("approved", approved)
                .put("note", "Android owner decision").toString(),
        )
    suspend fun executeApprovedPlan(planId: String): String? =
        call("/owner-control/plans/${segment(planId)}/execute", "POST", "{}")
    suspend fun getControlledExecutions(): String? =
        call("/owner-control/executions?active_only=false&limit=100")
    suspend fun cancelExecution(executionId: String): String? =
        call("/owner-control/executions/${segment(executionId)}/cancel", "POST", "{}")
    suspend fun requestRollback(executionId: String): String? =
        call(
            "/owner-control/executions/${segment(executionId)}/request-rollback",
            "POST", "{}",
        )

    // ── autonomy operations (goal queue, schedule, runs) ────────────────────
    suspend fun getAutonomousGoals(): String? = call("/owner-control/autonomous-goals")
    suspend fun createAutonomousGoal(title: String, description: String, priority: String): String? =
        call(
            "/owner-control/autonomous-goals", "POST",
            JSONObject().put("title", title).put("description", description)
                .put("priority", priority).put("approve_for_planning", true).toString(),
        )
    suspend fun decideAutonomousGoal(goalId: String, approved: Boolean): String? =
        call(
            "/owner-control/autonomous-goals/${segment(goalId)}/decision", "POST",
            JSONObject().put("approved", approved).toString(),
        )
    suspend fun deferAutonomousGoal(goalId: String): String? =
        call("/owner-control/autonomous-goals/${segment(goalId)}/defer", "POST", "{}")
    suspend fun prioritizeAutonomousGoal(goalId: String, priority: String): String? =
        call(
            "/owner-control/autonomous-goals/${segment(goalId)}/priority", "PUT",
            JSONObject().put("priority", priority).toString(),
        )
    suspend fun executeNextAutonomousGoal(): String? =
        call("/owner-control/autonomous-goals/execute-next", "POST", "{}")
    suspend fun getAllocationPreview(): String? =
        call("/owner-control/autonomous-goals/allocation-preview")

    suspend fun getAutonomySchedule(): String? = call("/owner-control/autonomy-schedule")
    suspend fun createScheduledDirective(
        title: String,
        runAt: String,
        recurrence: String,
        timezoneName: String,
    ): String? = call(
        "/owner-control/autonomy-schedule", "POST",
        JSONObject().put("title", title).put("next_run_at", runAt)
            .put("recurrence", recurrence).put("timezone_name", timezoneName)
            .put("approve_for_planning", true).toString(),
    )
    suspend fun updateScheduleStatus(scheduleId: String, status: String): String? =
        call(
            "/owner-control/autonomy-schedule/${segment(scheduleId)}/status", "POST",
            JSONObject().put("status", status).toString(),
        )

    suspend fun getAutonomyRunEvents(limit: Int = 100): String? =
        call("/owner-control/autonomy-runs?limit=$limit")
    suspend fun getAutonomyCycleTimeline(cycleId: String): String? =
        call("/owner-control/autonomy-runs/${segment(cycleId)}/timeline")
    suspend fun getAutonomyEnvelope(): String? = call("/owner-control/autonomy-envelope")
    suspend fun updateAutonomyEnvelope(patch: JSONObject): String? =
        call("/owner-control/autonomy-envelope", "PUT", patch.toString())

    // ── preemptions + reconciliation ────────────────────────────────────────
    suspend fun getPreemptions(): String? = call("/owner-control/preemptions")
    suspend fun createPreemption(
        executionId: String,
        urgentGoalId: String,
        planId: String? = null,
    ): String? {
        val body = JSONObject().put("execution_id", executionId).put("urgent_goal_id", urgentGoalId)
        if (planId != null) body.put("plan_id", planId)
        return call("/owner-control/preemptions", "POST", body.toString())
    }
    suspend fun refreshPreemption(preemptionId: String): String? =
        call("/owner-control/preemptions/${segment(preemptionId)}/refresh", "POST", "{}")
    suspend fun reconcilePreemption(preemptionId: String): String? =
        call("/owner-control/preemptions/${segment(preemptionId)}/reconcile", "POST", "{}")
    suspend fun requestPreemptionResume(preemptionId: String): String? =
        call("/owner-control/preemptions/${segment(preemptionId)}/request-resume", "POST", "{}")
    suspend fun getPlanStepReconciliations(planId: String): String? =
        call("/owner-control/plans/${segment(planId)}/step-reconciliations")

    // ── measured concurrency budget + signed owner decisions ────────────────
    suspend fun getConcurrencyBudget(): String? = call("/owner-control/concurrency-budget")
    suspend fun setConcurrencyBudget(enabled: Boolean, maxWorkers: Int?): String? {
        val body = JSONObject().put("enabled", enabled)
        body.put("max_workers", maxWorkers ?: JSONObject.NULL)
        return call("/owner-control/concurrency-budget", "PUT", body.toString())
    }
    suspend fun getConcurrencyReceipts(): String? =
        call("/owner-control/concurrency-budget/receipts?limit=20")
    suspend fun getOwnerDecisions(): String? = call("/owner-control/owner-decisions")
    suspend fun issueOwnerDecision(expectedChangeTypes: List<String>, note: String): String? =
        call(
            "/owner-control/owner-decisions", "POST",
            JSONObject().put("decision_type", "expected_identity_change")
                .put("expected_change_types", JSONArray(expectedChangeTypes))
                .put("note", note).toString(),
        )
    suspend fun revokeOwnerDecision(decisionId: String): String? =
        call("/owner-control/owner-decisions/${segment(decisionId)}/revoke", "POST", "{}")

    // ── cognition surfaces (charter, questions, induced skills, progress) ───
    suspend fun getOwnerCharter(): String? = call("/owner-control/charter")
    suspend fun updateOwnerCharter(
        mission: String,
        priorities: List<String>,
        standingDirectives: List<String>,
    ): String? = call(
        "/owner-control/charter", "PUT",
        JSONObject().put("mission", mission)
            .put("priorities", JSONArray(priorities))
            .put("standing_directives", JSONArray(standingDirectives)).toString(),
    )
    suspend fun getOwnerQuestions(): String? = call("/owner-control/questions?status=pending")
    suspend fun answerOwnerQuestion(questionId: String, answer: String): String? =
        call(
            "/owner-control/questions/${segment(questionId)}/answer", "POST",
            JSONObject().put("answer", answer).put("note", "Android owner decision").toString(),
        )
    suspend fun getInducedSkills(): String? = call("/owner-control/induced-skills?status=pending")
    suspend fun acceptInducedSkill(candidateId: String): String? =
        call("/owner-control/induced-skills/${segment(candidateId)}/accept", "POST", "{}")
    suspend fun rejectInducedSkill(candidateId: String): String? =
        call("/owner-control/induced-skills/${segment(candidateId)}/reject", "POST", "{}")
    suspend fun getLearningProgress(): String? = call("/owner-control/learning-progress")
    suspend fun getOwnerModel(): String? = call("/owner-control/owner-model")

    // ── OS grounding + browser tabs (read-only observations) ────────────────
    suspend fun getOsGrounding(): String? = call("/os-grounding")
    suspend fun getAccessibilityStatus(): String? = call("/os-grounding/accessibility/status")
    suspend fun getBrowserTabs(): String? = call("/os-grounding/browser-tabs")
}
