package com.arena.voice.ui.screens

import androidx.compose.foundation.layout.*
import androidx.compose.foundation.lazy.LazyColumn
import androidx.compose.foundation.lazy.items
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
import org.json.JSONObject
import javax.inject.Inject

/**
 * Projects — long-horizon + multi-session tracking (P2 AGI).
 * Mirrors web ProjectsPage and desktop ProjectsPage, backed by backend's ProjectManager.
 * Shows projects auto-created via cognitive runtime decomposition (complex goals → sub-goals).
 */

data class BackendProject(
    val project_id: String,
    val name: String,
    val description: String,
    val status: String,
    val progress_percent: Double,
    val tags: List<String>
)

@HiltViewModel
class ProjectsViewModel @Inject constructor(
    private val api: ApiClient,
) : ViewModel() {
    var projects by mutableStateOf<List<BackendProject>>(emptyList())
        private set
    var loading by mutableStateOf(true)
        private set
    var error by mutableStateOf<String?>(null)
        private set
    var selectedDetail by mutableStateOf<String?>(null)
        private set

    init {
        load()
    }

    fun load() {
        loading = true
        error = null
        viewModelScope.launch {
            val raw = api.getBackendProjectsRaw()
            if (raw != null) {
                runCatching {
                    val json = JSONObject(raw)
                    val arr = json.optJSONArray("projects") ?: return@runCatching
                    val list = mutableListOf<BackendProject>()
                    for (i in 0 until arr.length()) {
                        val obj = arr.optJSONObject(i) ?: continue
                        list.add(
                            BackendProject(
                                project_id = obj.optString("project_id", ""),
                                name = obj.optString("name", "Unnamed"),
                                description = obj.optString("description", ""),
                                status = obj.optString("status", "active"),
                                progress_percent = obj.optDouble("progress_percent", 0.0),
                                tags = obj.optJSONArray("tags")?.let { tagsArr ->
                                    (0 until tagsArr.length()).mapNotNull { tagsArr.optString(it).ifBlank { null } }
                                } ?: emptyList()
                            )
                        )
                    }
                    projects = list
                }.onFailure { e ->
                    error = e.message
                }
            } else {
                error = "Backend offline — no projects"
            }
            loading = false
        }
    }

    fun selectProject(projectId: String) {
        viewModelScope.launch {
            val raw = api.getBackendProjectRaw(projectId)
            if (raw != null) {
                runCatching {
                    val json = JSONObject(raw)
                    val proj = json.optJSONObject("project")
                    val resume = json.optJSONObject("resume_context")
                    val decomp = json.optJSONObject("decomposition")
                    val detail = buildString {
                        appendLine("Project: ${proj?.optString("name", "")}")
                        appendLine("Status: ${proj?.optString("status", "")} — ${proj?.optDouble("progress_percent", 0.0)}%")
                        appendLine("Milestones: ${proj?.optJSONArray("milestones")?.length() ?: 0}")
                        appendLine()
                        appendLine("Resume: ${resume?.optDouble("progress_percent", 0.0)}% — pending: ${resume?.optJSONArray("pending_milestones")?.let { (0 until it.length()).joinToString { idx -> it.optString(idx) } }}")
                        appendLine()
                        appendLine("Decomposition: ${decomp?.optDouble("progress_percent", 0.0)}% — next: ${decomp?.optJSONArray("next_actions")?.let { (0 until it.length()).joinToString { idx -> it.optJSONObject(idx)?.optString("description") ?: "" } }}")
                    }
                    selectedDetail = detail
                }
            } else {
                selectedDetail = "Could not load project $projectId (backend offline?)"
            }
        }
    }
}

@Composable
fun ProjectsScreen(
    viewModel: ProjectsViewModel = hiltViewModel(),
) {
    Column(
        modifier = Modifier
            .fillMaxSize()
            .padding(16.dp),
        verticalArrangement = Arrangement.spacedBy(12.dp)
    ) {
        Row(
            modifier = Modifier.fillMaxWidth(),
            horizontalArrangement = Arrangement.SpaceBetween
        ) {
            Text("Projects", style = MaterialTheme.typography.titleLarge, fontWeight = FontWeight.SemiBold)
            Button(onClick = { viewModel.load() }) {
                Text("Refresh")
            }
        }

        Text(
            "Long-horizon + multi-session tracking (P2 AGI). Complex goals auto-create projects with sub-goals DAG.",
            style = MaterialTheme.typography.bodySmall,
            color = MaterialTheme.colorScheme.onSurfaceVariant
        )

        if (viewModel.loading) {
            CircularProgressIndicator()
        } else if (viewModel.error != null) {
            Text("⚠ ${viewModel.error}", color = MaterialTheme.colorScheme.error)
        } else if (viewModel.projects.isEmpty()) {
            Text("(no projects yet — complex goals auto-create them)", color = MaterialTheme.colorScheme.onSurfaceVariant)
        } else {
            LazyColumn(
                verticalArrangement = Arrangement.spacedBy(8.dp),
                modifier = Modifier.weight(1f)
            ) {
                items(viewModel.projects) { proj ->
                    Card(
                        modifier = Modifier.fillMaxWidth(),
                        onClick = { viewModel.selectProject(proj.project_id) }
                    ) {
                        Column(modifier = Modifier.padding(12.dp)) {
                            Text(proj.name, fontWeight = FontWeight.SemiBold)
                            Text("${proj.progress_percent.toInt()}% — ${proj.status}", style = MaterialTheme.typography.bodySmall)
                            if (proj.tags.isNotEmpty()) {
                                Text(proj.tags.joinToString(), style = MaterialTheme.typography.labelSmall, color = MaterialTheme.colorScheme.onSurfaceVariant)
                            }
                        }
                    }
                }
            }

            viewModel.selectedDetail?.let { detail ->
                Card(modifier = Modifier.fillMaxWidth()) {
                    Text(detail, modifier = Modifier.padding(12.dp), style = MaterialTheme.typography.bodySmall)
                }
            }
        }
    }
}
