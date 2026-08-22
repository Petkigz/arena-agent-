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
 * Files — file search, mirroring the web/desktop Files page (/filesystem/search).
 */
@HiltViewModel
class FilesViewModel @Inject constructor(
    private val api: ApiClient,
) : ViewModel() {
    var results by mutableStateOf<List<String>>(emptyList())
        private set
    var searching by mutableStateOf(false)
        private set

    fun search(query: String) {
        if (query.isBlank()) return
        searching = true
        viewModelScope.launch {
            val lines = mutableListOf<String>()
            api.searchFiles(query)?.let { raw ->
                runCatching {
                    val root = JSONObject(raw)
                    val arr = root.optJSONArray("results") ?: JSONArray()
                    for (i in 0 until minOf(arr.length(), 100)) {
                        val item = arr.optJSONObject(i) ?: continue
                        lines.add(item.optString("name").ifBlank { item.optString("path").ifBlank { item.toString() } })
                    }
                }
            }
            results = lines.ifEmpty { listOf("(no results)") }
            searching = false
        }
    }
}

@Composable
fun FilesScreen(viewModel: FilesViewModel = hiltViewModel()) {
    var query by remember { mutableStateOf("") }

    Column(
        modifier = Modifier
            .fillMaxSize()
            .padding(16.dp),
    ) {
        Text("Files", style = MaterialTheme.typography.titleLarge, fontWeight = FontWeight.SemiBold)
        Spacer(Modifier.height(8.dp))

        Row(verticalAlignment = androidx.compose.ui.Alignment.CenterVertically) {
            OutlinedTextField(
                value = query,
                onValueChange = { query = it },
                placeholder = { Text("Search files…") },
                singleLine = true,
                modifier = Modifier.weight(1f),
            )
            Spacer(Modifier.width(8.dp))
            Button(onClick = { viewModel.search(query) }) { Text("Search") }
        }

        Spacer(Modifier.height(8.dp))
        if (viewModel.searching) {
            CircularProgressIndicator()
        } else {
            LazyColumn {
                items(viewModel.results) { line ->
                    Text(
                        text = line,
                        color = Color(0xFFF1F5F9),
                        fontSize = 14.sp,
                        modifier = Modifier.padding(vertical = 4.dp),
                    )
                }
            }
        }
    }
}
