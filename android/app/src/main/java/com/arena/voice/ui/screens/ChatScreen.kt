package com.arena.voice.ui.screens

import androidx.activity.compose.rememberLauncherForActivityResult
import androidx.activity.result.contract.ActivityResultContracts
import androidx.compose.foundation.background
import androidx.compose.foundation.layout.*
import androidx.compose.foundation.lazy.LazyColumn
import androidx.compose.foundation.lazy.items
import androidx.compose.foundation.lazy.rememberLazyListState
import androidx.compose.foundation.shape.CircleShape
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.filled.Add
import androidx.compose.material.icons.filled.AttachFile
import androidx.compose.material.icons.filled.Menu
import androidx.compose.material.icons.filled.Mic
import androidx.compose.material.icons.filled.MoreVert
import androidx.compose.material.icons.filled.Send
import androidx.compose.material.icons.filled.Settings
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
 * ChatGPT-style chat:
 *   header  : ☰ Beanie … · "● Online"
 *   body    : Beanie orb beside assistant messages, user bubbles on the right
 *   composer: + | Message Beanie… | 🎙 | ↑
 *   ☰ opens : conversation drawer (New Chat + history + Settings)
 */
@Composable
fun ChatScreen(
    viewModel: ChatViewModel = hiltViewModel(),
    onVoiceToggle: () -> Unit = {},
    onOpenSettings: () -> Unit = {},
) {
    val messages = viewModel.messages
    val conversations = viewModel.conversations
    val isConnected by viewModel.isConnected.collectAsStateWithLifecycle()
    val isStreaming by viewModel.isStreaming.collectAsStateWithLifecycle()

    var input by remember { mutableStateOf("") }
    var menuExpanded by remember { mutableStateOf(false) }

    val listState = rememberLazyListState()
    val scope = rememberCoroutineScope()
    val context = LocalContext.current
    val drawerState = rememberDrawerState(DrawerValue.Closed)

    // Scroll to bottom on new messages.
    LaunchedEffect(messages.size) {
        if (messages.isNotEmpty()) listState.animateScrollToItem(messages.size - 1)
    }

    // Load the conversation sidebar once connected.
    LaunchedEffect(Unit) {
        viewModel.loadConversations()
    }

    val filePicker = rememberLauncherForActivityResult(ActivityResultContracts.OpenDocument()) { uri ->
        uri?.let { scope.launch { viewModel.uploadFile(context, it) } }
    }

    ModalNavigationDrawer(
        drawerState = drawerState,
        drawerContent = {
            ModalDrawerSheet {
                Text(
                    "Beanie",
                    style = MaterialTheme.typography.titleMedium,
                    fontWeight = androidx.compose.ui.text.font.FontWeight.Bold,
                    modifier = Modifier.padding(16.dp),
                )
                NavigationDrawerItem(
                    label = { Text("New conversation") },
                    selected = false,
                    icon = { Icon(Icons.Default.Add, contentDescription = null) },
                    onClick = {
                        viewModel.newConversation()
                        scope.launch { drawerState.close() }
                    },
                    modifier = Modifier.padding(horizontal = 12.dp),
                )
                Divider(color = Color(0xFF334155), modifier = Modifier.padding(vertical = 8.dp))
                LazyColumn(modifier = Modifier.weight(1f)) {
                    items(conversations, key = { it.first }) { (id, title) ->
                        NavigationDrawerItem(
                            label = { Text(title.ifBlank { "Conversation" }, maxLines = 1) },
                            selected = id == viewModel.conversationId,
                            onClick = {
                                viewModel.selectConversation(id)
                                scope.launch { drawerState.close() }
                            },
                            modifier = Modifier.padding(horizontal = 12.dp),
                        )
                    }
                }
                Divider(color = Color(0xFF334155), modifier = Modifier.padding(vertical = 8.dp))
                NavigationDrawerItem(
                    label = { Text("Settings") },
                    selected = false,
                    icon = { Icon(Icons.Default.Settings, contentDescription = null) },
                    onClick = {
                        scope.launch { drawerState.close() }
                        onOpenSettings()
                    },
                    modifier = Modifier.padding(horizontal = 12.dp),
                )
            }
        },
    ) {
        Column(modifier = Modifier.fillMaxSize()) {
            // ── Header ──
            Row(
                modifier = Modifier
                    .fillMaxWidth()
                    .padding(horizontal = 4.dp, vertical = 8.dp),
                verticalAlignment = Alignment.CenterVertically,
            ) {
                IconButton(onClick = { scope.launch { drawerState.open() } }) {
                    Icon(Icons.Default.Menu, contentDescription = "Conversations")
                }
                Column(Modifier.weight(1f)) {
                    Text(
                        "Beanie",
                        style = MaterialTheme.typography.titleLarge,
                        fontWeight = androidx.compose.ui.text.font.FontWeight.SemiBold,
                    )
                    Row(verticalAlignment = Alignment.CenterVertically) {
                        Box(
                            Modifier
                                .size(8.dp)
                                .background(
                                    if (isConnected) Color(0xFF10B981) else Color(0xFF94A3B8),
                                    CircleShape,
                                ),
                        )
                        Spacer(Modifier.width(5.dp))
                        Text(
                            if (isConnected) "Online" else "Offline",
                            fontSize = 12.sp,
                            color = if (isConnected) Color(0xFF10B981) else Color(0xFF94A3B8),
                        )
                    }
                }
                Box {
                    IconButton(onClick = { menuExpanded = true }) {
                        Icon(Icons.Default.MoreVert, contentDescription = "More options")
                    }
                    DropdownMenu(expanded = menuExpanded, onDismissRequest = { menuExpanded = false }) {
                        DropdownMenuItem(
                            text = { Text("New conversation") },
                            onClick = {
                                menuExpanded = false
                                viewModel.newConversation()
                            },
                        )
                        DropdownMenuItem(
                            text = { Text("Settings") },
                            onClick = {
                                menuExpanded = false
                                onOpenSettings()
                            },
                        )
                    }
                }
            }

            Divider(color = Color(0xFF334155))

            // ── Body: messages (Beanie orb beside assistant messages) ──
            if (messages.isEmpty()) {
                Column(
                    Modifier
                        .fillMaxSize()
                        .padding(24.dp),
                    horizontalAlignment = Alignment.CenterHorizontally,
                    verticalArrangement = Arrangement.Center,
                ) {
                    ReactiveBeanieOrb(status = PresenceStatus.IDLE, sizeDp = 96)
                    Spacer(Modifier.height(16.dp))
                    Text("I'm Beanie.", color = Color(0xFFF1F5F9), fontSize = 18.sp)
                    Text(
                        "Send a message or tap the mic to talk.",
                        color = Color(0xFF94A3B8),
                        fontSize = 13.sp,
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

            // ── Composer: + | Message Beanie… | 🎙 | ↑ ──
            Row(
                modifier = Modifier
                    .fillMaxWidth()
                    .padding(horizontal = 8.dp, vertical = 8.dp),
                verticalAlignment = Alignment.Bottom,
            ) {
                IconButton(onClick = { filePicker.launch(arrayOf("*/*")) }) {
                    Icon(Icons.Default.AttachFile, contentDescription = "Attach file")
                }

                OutlinedTextField(
                    value = input,
                    onValueChange = { input = it },
                    modifier = Modifier.weight(1f),
                    placeholder = { Text("Message Beanie…") },
                    shape = RoundedCornerShape(24.dp),
                    maxLines = 4,
                )

                IconButton(onClick = onVoiceToggle) {
                    Icon(Icons.Default.Mic, contentDescription = "Voice input")
                }

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
}

@Composable
private fun MessageBubble(msg: ChatMessage) {
    val isUser = msg.role == "user"
    Row(
        modifier = Modifier.fillMaxWidth(),
        horizontalArrangement = if (isUser) Arrangement.End else Arrangement.Start,
        verticalAlignment = Alignment.Bottom,
    ) {
        // Beanie's orb beside assistant messages (matches the web BeanieAvatar).
        if (!isUser) {
            ReactiveBeanieOrb(
                status = if (msg.isStreaming) PresenceStatus.THINKING else PresenceStatus.IDLE,
                sizeDp = 28,
            )
            Spacer(Modifier.width(8.dp))
        }
        Surface(
            color = if (isUser) Color(0xFF3B82F6) else Color(0xFF1E293B),
            shape = RoundedCornerShape(16.dp),
        ) {
            Column(Modifier.padding(12.dp)) {
                if (msg.isStreaming && msg.content.isBlank()) {
                    Text("Beanie is thinking…", color = Color(0xFF94A3B8), fontSize = 12.sp)
                }
                Text(
                    text = msg.content.ifBlank { "" },
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
