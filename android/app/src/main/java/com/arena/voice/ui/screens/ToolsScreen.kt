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
import androidx.lifecycle.compose.collectAsStateWithLifecycle
import com.arena.voice.ui.chat.ChatViewModel

/**
 * Settings / status tab — server URL + API key, mirroring the web's Settings page.
 */
@Composable
fun ToolsScreen(
    serverUrl: String,
    apiKey: String,
    onSaveServerUrl: (String) -> Unit,
    onSaveApiKey: (String) -> Unit,
    viewModel: ChatViewModel = hiltViewModel(),
) {
    var serverUrlInput by remember { mutableStateOf(serverUrl) }
    var apiKeyInput by remember { mutableStateOf(apiKey) }
    val isConnected by viewModel.isConnected.collectAsStateWithLifecycle()

    Column(
        modifier = Modifier
            .fillMaxSize()
            .verticalScroll(rememberScrollState())
            .padding(16.dp),
        verticalArrangement = Arrangement.spacedBy(16.dp),
    ) {
        Text("Settings", style = MaterialTheme.typography.titleLarge, fontWeight = FontWeight.SemiBold)

        // Connection status
        Surface(
            color = MaterialTheme.colorScheme.surfaceVariant,
            shape = MaterialTheme.shapes.medium,
        ) {
            Column(Modifier.padding(16.dp)) {
                Text(
                    text = if (isConnected) "● Connected" else "○ Offline",
                    fontWeight = FontWeight.SemiBold,
                    color = if (isConnected) MaterialTheme.colorScheme.secondary else MaterialTheme.colorScheme.onSurfaceVariant,
                )
                Spacer(Modifier.height(4.dp))
                Text(
                    "The Android app is a companion that talks to your PC's Arena backend over the local network.",
                    style = MaterialTheme.typography.bodySmall,
                )
            }
        }

        // Server URL
        OutlinedTextField(
            value = serverUrlInput,
            onValueChange = { serverUrlInput = it },
            label = { Text("Server URL (ws://…)") },
            singleLine = true,
            modifier = Modifier.fillMaxWidth(),
        )

        // API key
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
        ) {
            Text("Save & Connect")
        }

        Button(
            onClick = {
                if (isConnected) viewModel.disconnect() else viewModel.connect()
            },
            modifier = Modifier.fillMaxWidth(),
        ) {
            Text(if (isConnected) "Disconnect" else "Connect to Server")
        }
    }
}
