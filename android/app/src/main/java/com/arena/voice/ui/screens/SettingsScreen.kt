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
            loading = false
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
