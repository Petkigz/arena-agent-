package com.arena.voice.ui.screens

import androidx.activity.compose.rememberLauncherForActivityResult
import androidx.activity.result.contract.ActivityResultContracts
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.PaddingValues
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.lazy.LazyColumn
import androidx.compose.foundation.lazy.items
import androidx.compose.foundation.lazy.rememberLazyListState
import androidx.compose.material3.DrawerValue
import androidx.compose.material3.ExperimentalMaterial3Api
import androidx.compose.material3.ModalNavigationDrawer
import androidx.compose.material3.rememberDrawerState
import androidx.compose.runtime.Composable
import androidx.compose.runtime.LaunchedEffect
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.rememberCoroutineScope
import androidx.compose.runtime.setValue
import androidx.compose.ui.Modifier
import androidx.compose.ui.platform.LocalContext
import androidx.lifecycle.compose.collectAsStateWithLifecycle
import androidx.hilt.navigation.compose.hiltViewModel
import com.arena.voice.ui.chat.ChatViewModel
import com.arena.voice.ui.components.BeanieComposer
import com.arena.voice.ui.components.BeanieEmptyState
import com.arena.voice.ui.components.BeanieMessage
import com.arena.voice.ui.components.BeanieTopBar
import com.arena.voice.ui.components.ConversationDrawer
import com.arena.voice.ui.components.PresenceStatus
import com.arena.voice.ui.components.VoiceStatusIndicator
import com.arena.voice.ui.components.WorkingContextAffordance
import com.arena.voice.ui.theme.Spacing
import kotlinx.coroutines.launch

/**
 * Chat — composition only (21j review): every visual piece lives in
 * ui/components and every value in ui/theme. This screen wires state.
 *
 *   BeanieTopBar
 *   ConversationSurface   (EmptyState | MessageTimeline)
 *   VoiceStatusIndicator  ┐
 *   WorkingContext        ├ presence + context, above the dock
 *   BeanieComposer        ┘
 */
@OptIn(ExperimentalMaterial3Api::class)
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
    val workingContext by viewModel.workingContext.collectAsStateWithLifecycle()

    var input by remember { mutableStateOf("") }
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
            ConversationDrawer(
                conversations = conversations,
                currentConversationId = viewModel.conversationId,
                onNewConversation = {
                    viewModel.newConversation()
                    scope.launch { drawerState.close() }
                },
                onSelectConversation = { id ->
                    viewModel.selectConversation(id)
                    scope.launch { drawerState.close() }
                },
                onNavigate = { route ->
                    scope.launch { drawerState.close() }
                    onNavigate(route)
                },
                onOpenSettings = {
                    scope.launch { drawerState.close() }
                    onOpenSettings()
                },
            )
        },
    ) {
        Column(modifier = Modifier.fillMaxSize()) {
            BeanieTopBar(
                isConnected = isConnected,
                onOpenDrawer = { scope.launch { drawerState.open() } },
                onNewConversation = { viewModel.newConversation() },
                onOpenSettings = onOpenSettings,
            )

            // ── Conversation surface ──
            if (messages.isEmpty()) {
                BeanieEmptyState(Modifier.weight(1f))
            } else {
                LazyColumn(
                    state = listState,
                    modifier = Modifier.weight(1f),
                    contentPadding = PaddingValues(Spacing.lg),
                    verticalArrangement = Arrangement.spacedBy(Spacing.md),
                ) {
                    items(messages, key = { it.id }) { msg ->
                        BeanieMessage(msg, voiceStatus)
                    }
                }
            }

            // ── Presence + context, above the dock ──
            VoiceStatusIndicator(voiceStatus)
            workingContext?.let { WorkingContextAffordance(it) }

            // ── Composer dock ──
            BeanieComposer(
                value = input,
                onValueChange = { input = it },
                onSend = {
                    if (input.isNotBlank()) {
                        viewModel.sendMessage(input)
                        input = ""
                    }
                },
                onAttach = { filePicker.launch(arrayOf("*/*")) },
                onVoiceToggle = onVoiceToggle,
                voiceStatus = voiceStatus,
                enabled = isConnected,
            )
        }
    }
}
