package com.arena.voice.ui.screens

import androidx.activity.compose.rememberLauncherForActivityResult
import androidx.activity.result.contract.ActivityResultContracts
import androidx.compose.foundation.layout.*
import androidx.compose.foundation.lazy.LazyColumn
import androidx.compose.foundation.lazy.items
import androidx.compose.foundation.lazy.rememberLazyListState
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.filled.Add
import androidx.compose.material.icons.filled.AttachFile
import androidx.compose.material.icons.filled.Mic
import androidx.compose.material.icons.filled.Send
import androidx.compose.material.icons.filled.AutoAwesome
import androidx.compose.material3.*
import androidx.compose.runtime.*
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.platform.LocalContext
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp
import androidx.lifecycle.compose.collectAsStateWithLifecycle
import androidx.hilt.navigation.compose.hiltViewModel
import com.arena.voice.ui.chat.ChatViewModel
import com.arena.voice.ui.chat.ChatMessage
import kotlinx.coroutines.launch

/**
 * ChatGPT-style chat: message list + composer [attach][textarea][mic][beanie][send].
 * Pressing the Beanie (✨) button replaces the message list with the floating orb.
 */
@Composable
fun ChatScreen(
    viewModel: ChatViewModel = hiltViewModel(),
    onVoiceToggle: () -> Unit = {},
) {
    val messages = viewModel.messages
    val isConnected by viewModel.isConnected.collectAsStateWithLifecycle()
    val isStreaming by viewModel.isStreaming.collectAsStateWithLifecycle()

    var input by remember { mutableStateOf("") }
    var beanieActive by remember { mutableStateOf(false) }

    val listState = rememberLazyListState()
    val scope = rememberCoroutineScope()
    val context = LocalContext.current

    // Scroll to bottom on new messages.
    LaunchedEffect(messages.size) {
        if (messages.isNotEmpty()) listState.animateScrollToItem(messages.size - 1)
    }

    val filePicker = rememberLauncherForActivityResult(ActivityResultContracts.OpenDocument()) { uri ->
        uri?.let { scope.launch { viewModel.uploadFile(context, it) } }
    }

    Column(modifier = Modifier.fillMaxSize()) {
        // ── Header ──
        Row(
            modifier = Modifier
                .fillMaxWidth()
                .padding(horizontal = 16.dp, vertical = 8.dp),
            verticalAlignment = Alignment.CenterVertically,
        ) {
            Column(Modifier.weight(1f)) {
                Text("Chat", style = MaterialTheme.typography.titleLarge, fontWeight = androidx.compose.ui.text.font.FontWeight.SemiBold)
                Text(
                    if (isConnected) "Connected" else "Offline",
                    fontSize = 12.sp,
                    color = if (isConnected) Color(0xFF10B981) else Color(0xFF94A3B8),
                )
            }
            IconButton(onClick = { viewModel.newConversation() }) {
                Icon(Icons.Default.Add, contentDescription = "New conversation")
            }
        }

        Divider(color = Color(0xFF334155))

        // ── Body: Beanie orb OR message list ──
        if (beanieActive) {
            BeanieScreen(
                presenceStatus = if (isStreaming) PresenceStatus.WORKING else PresenceStatus.IDLE,
                statusMessage = if (isStreaming) "Thinking…" else "I'm here. Talk to me.",
                isListening = false,
                onToggleTalk = onVoiceToggle,
            )
        } else {
            if (messages.isEmpty()) {
                Box(Modifier.fillMaxSize(), contentAlignment = Alignment.Center) {
                    Text(
                        "Start a conversation",
                        color = Color(0xFF94A3B8),
                        style = MaterialTheme.typography.bodyLarge,
                    )
                }
            } else {
                LazyColumn(
                    state = listState,
                    modifier = Modifier.weight(1f),
                    contentPadding = PaddingValues(16.dp),
                    verticalArrangement = Arrangement.spacedBy(12.dp),
                ) {
                    items(messages, key = { it.id }) { msg ->
                        MessageBubble(msg)
                    }
                }
            }
        }

        // ── Composer ──
        Row(
            modifier = Modifier
                .fillMaxWidth()
                .padding(horizontal = 8.dp, vertical = 8.dp),
            verticalAlignment = Alignment.Bottom,
        ) {
            // Attach
            IconButton(onClick = { filePicker.launch(arrayOf("*/*")) }) {
                Icon(Icons.Default.AttachFile, contentDescription = "Attach file")
            }

            // Text input
            OutlinedTextField(
                value = input,
                onValueChange = { input = it },
                modifier = Modifier.weight(1f),
                placeholder = { Text("Message Beanie...") },
                shape = RoundedCornerShape(24.dp),
                maxLines = 4,
            )

            // Beanie (✨) — toggles the orb in place of messages
            IconButton(onClick = { beanieActive = !beanieActive }) {
                Icon(Icons.Default.AutoAwesome, contentDescription = "Beanie")
            }

            // Mic
            IconButton(onClick = onVoiceToggle) {
                Icon(Icons.Default.Mic, contentDescription = "Voice input")
            }

            // Send
            IconButton(
                onClick = {
                    if (input.isNotBlank()) {
                        viewModel.sendMessage(input)
                        input = ""
                    }
                },
                enabled = input.isNotBlank() && isConnected,
            ) {
                Icon(Icons.Default.Send, contentDescription = "Send")
            }
        }
    }
}

@Composable
private fun MessageBubble(msg: ChatMessage) {
    val isUser = msg.role == "user"
    Row(
        modifier = Modifier.fillMaxWidth(),
        horizontalArrangement = if (isUser) Arrangement.End else Arrangement.Start,
    ) {
        Surface(
            color = if (isUser) Color(0xFF3B82F6) else Color(0xFF1E293B),
            shape = RoundedCornerShape(16.dp),
        ) {
            Column(Modifier.padding(12.dp)) {
                Text(
                    text = msg.content.ifBlank { "…" },
                    color = if (isUser) Color.White else Color(0xFFF1F5F9),
                )
                if (msg.actionSteps.isNotEmpty()) {
                    Spacer(Modifier.height(6.dp))
                    msg.actionSteps.takeLast(2).forEach { step ->
                        Text(
                            text = "• $step",
                            color = Color(0xFF94A3B8),
                            fontSize = 11.sp,
                        )
                    }
                }
                if (msg.isStreaming) {
                    Spacer(Modifier.height(4.dp))
                    Text("▍", color = Color(0xFF94A3B8))
                }
            }
        }
    }
}
