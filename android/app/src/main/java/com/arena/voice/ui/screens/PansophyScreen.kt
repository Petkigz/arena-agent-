package com.arena.voice.ui.screens

import androidx.compose.foundation.layout.*
import androidx.compose.foundation.lazy.LazyColumn
import androidx.compose.foundation.lazy.items
import androidx.compose.material3.*
import androidx.compose.runtime.*
import androidx.compose.ui.Modifier
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp
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
 * Pansophy — knowledge graph + memories, mirroring the web/desktop page.
 * Reads the same backend endpoint (/knowledge/graph + /memories).
 */
@HiltViewModel
class PansophyViewModel @Inject constructor(
    private val api: ApiClient,
) : ViewModel() {
    var items by mutableStateOf<List<String>>(emptyList())
        private set
    var loading by mutableStateOf(true)
        private set

    init {
        refresh()
    }

    fun refresh() {
        loading = true
        viewModelScope.launch {
            val lines = mutableListOf<String>()

            api.knowledgeGraph()?.let { raw ->
                runCatching {
                    val obj = JSONObject(raw)
                    val entities = obj.optJSONArray("entities") ?: JSONArray()
                    val rels = obj.optJSONArray("relationships") ?: JSONArray()
                    lines.add("── Knowledge Graph — ${entities.length()} entities, ${rels.length()} links ──")
                    for (i in 0 until minOf(entities.length(), 150)) {
                        val e = entities.optJSONObject(i) ?: continue
                        lines.add("• ${e.optString("name")}  [${e.optString("type")}]")
                    }
                    for (i in 0 until minOf(rels.length(), 150)) {
                        val r = rels.optJSONObject(i) ?: continue
                        lines.add("↳ ${r.optString("predicate")}")
                    }
                }
            }

            api.memories()?.let { raw ->
                runCatching {
                    val arr = JSONArray(raw)
                    lines.add("── Memories (${arr.length()}) ──")
                    for (i in 0 until minOf(arr.length(), 150)) {
                        val m = arr.optJSONObject(i) ?: continue
                        val text = m.optString("title")
                            .ifBlank { m.optString("content").ifBlank { m.toString() } }
                        lines.add("• $text")
                    }
                }
            }

            if (lines.isEmpty()) {
                lines.add("(nothing yet — ask Beanie to remember things)")
            }
            items = lines
            loading = false
        }
    }
}

@Composable
fun PansophyScreen(viewModel: PansophyViewModel = hiltViewModel()) {
    Column(
        modifier = Modifier
            .fillMaxSize()
            .padding(16.dp),
    ) {
        Text("Pansophy", style = MaterialTheme.typography.titleLarge, fontWeight = FontWeight.SemiBold)
        Spacer(Modifier.height(4.dp))
        TextButton(onClick = { viewModel.refresh() }) { Text("Refresh") }
        Spacer(Modifier.height(4.dp))

        if (viewModel.loading) {
            Box(Modifier.fillMaxSize(), contentAlignment = androidx.compose.ui.Alignment.Center) {
                CircularProgressIndicator()
            }
        } else {
            LazyColumn(verticalArrangement = Arrangement.spacedBy(2.dp)) {
                items(viewModel.items) { line ->
                    Text(
                        text = line,
                        color = if (line.startsWith("──")) Color(0xFF94A3B8) else Color(0xFFF1F5F9),
                        fontSize = if (line.startsWith("──")) 12.sp else 14.sp,
                        modifier = Modifier.padding(vertical = 3.dp),
                    )
                }
            }
        }
    }
}
