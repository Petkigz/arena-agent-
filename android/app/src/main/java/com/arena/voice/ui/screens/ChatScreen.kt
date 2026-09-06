package com.arena.voice.ui.screens

import androidx.activity.compose.rememberLauncherForActivityResult
import androidx.activity.result.contract.ActivityResultContracts
import androidx.compose.foundation.background
import androidx.compose.foundation.clickable
import androidx.compose.foundation.layout.*
import androidx.compose.foundation.lazy.LazyColumn
import androidx.compose.foundation.lazy.items
import androidx.compose.foundation.lazy.rememberLazyListState
import androidx.compose.foundation.shape.CircleShape
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.material.icons.Icons
import androidx.compose.animation.core.LinearEasing
import androidx.compose.animation.core.animateFloat
import androidx.compose.animation.core.infiniteRepeatable
import androidx.compose.animation.core.rememberInfiniteTransition
import androidx.compose.animation.core.tween
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.filled.Add
import androidx.compose.material.icons.filled.AttachFile
import androidx.compose.material.icons.filled.CheckCircle
import androidx.compose.material.icons.filled.Error
import androidx.compose.material.icons.filled.Menu
import androidx.compose.material.icons.filled.Mic
import androidx.compose.material.icons.filled.MoreVert
import androidx.compose.material.icons.filled.Refresh
import androidx.compose.material.icons.filled.Send
import androidx.compose.material.icons.filled.Settings
import androidx.compose.material3.*
import androidx.compose.runtime.*
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.draw.clip
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.graphics.graphicsLayer
import androidx.compose.ui.platform.LocalContext
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp
import androidx.lifecycle.compose.collectAsStateWithLifecycle
import androidx.hilt.navigation.compose.hiltViewModel
import com.arena.voice.ui.chat.ChatViewModel
import com.arena.voice.ui.chat.ChatMessage
import com.arena.voice.ui.chat.ToolActivity
import com.arena.voice.ui.chat.WorkingContext
import kotlinx.coroutines.launch

/**
 * ChatGPT-style chat:
 *   header  : ☰ Beanie … · "● Online"
 *   body    : Beanie orb beside assistant messages, user bubbles on the right
 *   composer: + | Message Beanie… | 🎙 | ↑
 *   ☰ opens : conversation drawer (New Chat + history + Settings)
 */
@OptIn(androidx.compose.material3.ExperimentalMaterial3Api::class)
@Composable
fun ChatScreen(
    viewModel: ChatViewModel = hiltViewModel(),
    onVoiceToggle: () -> Unit = {},
    onOpenSettings: () -> Unit = {},
    onNavigate: (String) -> Unit = {},
    voiceStatus: PresenceStatus = PresenceStatus.IDLE,
) {
    val messages = viewModel.messages
    val conversations = viewModel.conversations
    val isConnected by viewModel.isConnected.collectAsStateWithLifecycle()
    val isStreaming by viewModel.isStreaming.collectAsStateWithLifecycle()
    val workingContext by viewModel.workingContext.collectAsStateWithLifecycle()

    var input by remember { mutableStateOf("") }
    var menuExpanded by remember { mutableStateOf(false) }
    var showContextSheet by remember { mutableStateOf(false) }

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
                Divider(color = MaterialTheme.colorScheme.surfaceVariant, modifier = Modifier.padding(vertical = 8.dp))
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
                Divider(color = MaterialTheme.colorScheme.surfaceVariant, modifier = Modifier.padding(vertical = 8.dp))

                // Workspace (review section 5): full functionality, mobile
                // navigation — grouped like the desktop sidebar.
                Text(
                    "Workspace",
                    style = MaterialTheme.typography.labelMedium,
                    color = MaterialTheme.colorScheme.onSurfaceVariant,
                    modifier = Modifier.padding(horizontal = 16.dp, vertical = 4.dp),
                )
                listOf(
                    "Pansophy" to "pansophy",
                    "Files" to "files",
                    "Images" to "images",
                    "Projects" to "projects",
                ).forEach { (label, route) ->
                    NavigationDrawerItem(
                        label = { Text(label) },
                        selected = false,
                        onClick = {
                            scope.launch { drawerState.close() }
                            onNavigate(route)
                        },
                        modifier = Modifier.padding(horizontal = 12.dp),
                    )
                }

                Divider(color = MaterialTheme.colorScheme.surfaceVariant, modifier = Modifier.padding(vertical = 8.dp))
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
                                    if (isConnected) MaterialTheme.colorScheme.secondary else MaterialTheme.colorScheme.outline,
                                    CircleShape,
                                ),
                        )
                        Spacer(Modifier.width(5.dp))
                        Text(
                            if (isConnected) "Online" else "Offline",
                            fontSize = 12.sp,
                            color = if (isConnected) MaterialTheme.colorScheme.secondary else MaterialTheme.colorScheme.outline,
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

            Divider(color = MaterialTheme.colorScheme.surfaceVariant)

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
                    Text("I'm Beanie.", color = MaterialTheme.colorScheme.onBackground, fontSize = 18.sp)
                    Text(
                        "Send a message or tap the mic to talk.",
                        color = MaterialTheme.colorScheme.onSurfaceVariant,
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
                        MessageBubble(msg, voiceStatus)
                    }
                }
            }

            // ── Floating voice indicator (listening / thinking / speaking) ──
            val voiceLabel = when (voiceStatus) {
                PresenceStatus.LISTENING -> "Listening…"
                PresenceStatus.THINKING -> "Thinking…"
                PresenceStatus.SPEAKING -> "Speaking…"
                else -> null
            }
            if (voiceLabel != null) {
                // Presence colors come from the shared Beanie state machine (tokens-pinned).
                val voiceColor = when (voiceStatus) {
                    PresenceStatus.LISTENING -> PresenceStatus.LISTENING.color
                    PresenceStatus.THINKING -> PresenceStatus.THINKING.color
                    PresenceStatus.SPEAKING -> PresenceStatus.SPEAKING.color
                    else -> PresenceStatus.IDLE.color
                }
                Box(Modifier.fillMaxWidth(), contentAlignment = Alignment.Center) {
                    Row(
                        Modifier
                            .background(MaterialTheme.colorScheme.surface, RoundedCornerShape(16.dp))
                            .padding(horizontal = 12.dp, vertical = 6.dp),
                        verticalAlignment = Alignment.CenterVertically,
                    ) {
                        Box(
                            Modifier
                                .size(8.dp)
                                .background(voiceColor, CircleShape),
                        )
                        Spacer(Modifier.width(8.dp))
                        Text(voiceLabel, color = MaterialTheme.colorScheme.onSurface, fontSize = 13.sp)
                    }
                }
            }

            // ── Inline working-context card (review section 4) ──
            workingContext?.let { context ->
                WorkingContextCard(context, onClick = { showContextSheet = true })
            }
            if (showContextSheet && workingContext != null) {
                // Context as a bottom sheet (review: mobile context is
                // progressive — tap the card for the full picture).
                ModalBottomSheet(onDismissRequest = { showContextSheet = false }) {
                    Text(
                        "Working context",
                        style = MaterialTheme.typography.titleMedium,
                        modifier = Modifier.padding(horizontal = 24.dp, vertical = 4.dp),
                    )
                    workingContext?.project?.let {
                        ContextSheetRow("Project", it)
                    }
                    workingContext?.objective?.let {
                        ContextSheetRow("Objective", it)
                    }
                    workingContext?.let { ctx ->
                        if (ctx.memories > 0) {
                            ContextSheetRow("Relevant memories", "${ctx.memories}")
                        }
                    }
                    Spacer(Modifier.height(28.dp))
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
                    shape = RoundedCornerShape(16.dp),
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
private fun MessageBubble(msg: ChatMessage, voiceStatus: PresenceStatus = PresenceStatus.IDLE) {
    val isUser = msg.role == "user"
    Row(
        modifier = Modifier.fillMaxWidth(),
        horizontalArrangement = if (isUser) Arrangement.End else Arrangement.Start,
        verticalAlignment = Alignment.Bottom,
    ) {
        // Beanie's orb beside assistant messages (matches the web BeanieAvatar).
        if (!isUser) {
            // While streaming, the orb follows the LIVE voice state (review:
            // one continuous interaction — thinking while working, speaking
            // during TTS) instead of a fixed "thinking" placeholder.
            val liveStatus = when {
                !msg.isStreaming -> PresenceStatus.IDLE
                voiceStatus == PresenceStatus.SPEAKING -> PresenceStatus.SPEAKING
                else -> PresenceStatus.THINKING
            }
            ReactiveBeanieOrb(status = liveStatus, sizeDp = 28)
            Spacer(Modifier.width(8.dp))
        }
        Surface(
            color = if (isUser) MaterialTheme.colorScheme.primary else MaterialTheme.colorScheme.surface,
            shape = RoundedCornerShape(16.dp),
        ) {
            Column(Modifier.padding(12.dp)) {
                if (msg.isStreaming && msg.content.isBlank()) {
                    Text("Beanie is thinking…", color = MaterialTheme.colorScheme.onSurfaceVariant, fontSize = 12.sp)
                }
                Text(
                    text = msg.content.ifBlank { "" },
                    color = if (isUser) Color.White else MaterialTheme.colorScheme.onSurface,
                )
                if (msg.actionSteps.isNotEmpty()) {
                    Spacer(Modifier.height(6.dp))
                    ToolActivityCard(msg.actionSteps)
                }
                if (msg.isStreaming) {
                    Spacer(Modifier.height(4.dp))
                    Text("▍", color = MaterialTheme.colorScheme.onSurfaceVariant)
                }
            }
        }
    }
}


/**
 * Inline "Working context" card (design review section 4): while Beanie works,
 * the conversation itself carries what Beanie is working on — same semantic
 * card as desktop/web, mobile presentation.
 */
@Composable
private fun WorkingContextCard(context: WorkingContext) {
    Surface(
        color = MaterialTheme.colorScheme.surface,
        shape = RoundedCornerShape(12.dp),
        modifier = Modifier
            .fillMaxWidth()
            .padding(horizontal = 16.dp, vertical = 4.dp),
    ) {
        Column(Modifier.padding(12.dp)) {
            Text(
                "Working context",
                fontSize = 12.sp,
                fontWeight = androidx.compose.ui.text.font.FontWeight.SemiBold,
                color = MaterialTheme.colorScheme.onSurfaceVariant,
            )
            context.project?.let {
                Text("Project: $it", fontSize = 12.sp, color = MaterialTheme.colorScheme.onSurface)
            }
            context.objective?.let {
                Text("Objective: $it", fontSize = 12.sp, color = MaterialTheme.colorScheme.onSurface)
            }
            if (context.memories > 0) {
                Text(
                    "${context.memories} relevant memories",
                    fontSize = 12.sp,
                    color = MaterialTheme.colorScheme.onSurface,
                )
            }
        }
    }
}


@Composable
private fun ContextSheetRow(label: String, value: String) {
    Column(Modifier.padding(horizontal = 24.dp, vertical = 8.dp)) {
        Text(
            label,
            style = MaterialTheme.typography.labelMedium,
            color = MaterialTheme.colorScheme.onSurfaceVariant,
        )
        Text(value, style = MaterialTheme.typography.bodyLarge)
    }
}

/**
 * Tool activity rendered as the SAME semantic event the web renders (review:
 * "Searching files / 3 results / ✓ Completed" — never raw diagnostics):
 * a compact card with a per-status icon and status-tinted labels.
 */
@Composable
private fun ToolActivityCard(activities: List<ToolActivity>) {
    Surface(
        color = MaterialTheme.colorScheme.surfaceVariant.copy(alpha = 0.45f),
        shape = RoundedCornerShape(8.dp),
    ) {
        Column(
            Modifier.padding(horizontal = 10.dp, vertical = 8.dp),
            verticalArrangement = Arrangement.spacedBy(6.dp),
        ) {
            activities.takeLast(3).forEach { activity ->
                ToolActivityRow(activity)
            }
        }
    }
}

@Composable
private fun ToolActivityRow(activity: ToolActivity) {
    val labelColor = when (activity.status) {
        "complete" -> MaterialTheme.colorScheme.secondary
        "in_progress" -> MaterialTheme.colorScheme.primary
        "error" -> MaterialTheme.colorScheme.error
        else -> MaterialTheme.colorScheme.onSurfaceVariant
    }
    Row(verticalAlignment = Alignment.CenterVertically) {
        when (activity.status) {
            "complete" -> Icon(
                Icons.Default.CheckCircle,
                contentDescription = activity.status,
                tint = labelColor,
                modifier = Modifier.size(16.dp),
            )
            "error" -> Icon(
                Icons.Default.Error,
                contentDescription = activity.status,
                tint = labelColor,
                modifier = Modifier.size(16.dp),
            )
            "in_progress" -> {
                // Spinning indicator — same semantic as the web's Loader2.
                val transition = rememberInfiniteTransition(label = "tool")
                val rotation by transition.animateFloat(
                    initialValue = 0f,
                    targetValue = 360f,
                    animationSpec = infiniteRepeatable(tween(1000, easing = LinearEasing)),
                    label = "rotation",
                )
                Icon(
                    Icons.Default.Refresh,
                    contentDescription = activity.status,
                    tint = labelColor,
                    modifier = Modifier
                        .size(16.dp)
                        .graphicsLayer { rotationZ = rotation },
                )
            }
            else -> Box(
                Modifier
                    .size(16.dp)
                    .clip(CircleShape),
                contentAlignment = Alignment.Center,
            ) {
                Box(
                    Modifier
                        .size(8.dp)
                        .clip(CircleShape)
                        .background(MaterialTheme.colorScheme.outline)
                )
            }
        }
        Spacer(Modifier.width(8.dp))
        Text(activity.label, fontSize = 12.sp, color = labelColor)
    }
}
