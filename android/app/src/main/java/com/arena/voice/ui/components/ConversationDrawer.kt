package com.arena.voice.ui.components

import androidx.compose.foundation.layout.*
import androidx.compose.foundation.lazy.LazyColumn
import androidx.compose.foundation.lazy.items
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.filled.Add
import androidx.compose.material.icons.filled.Settings
import androidx.compose.material3.*
import androidx.compose.runtime.Composable
import androidx.compose.ui.Modifier
import androidx.compose.ui.text.font.FontWeight
import com.arena.voice.ui.theme.Spacing

/**
 * ConversationDrawer (21j review, problem 7) — grouped navigation with visual
 * priority, not a flat list of equally-weighted items:
 *
 *   Beanie
 *   + New chat
 *   RECENT      ← current conversation visibly selected
 *   WORKSPACE   ← Pansophy · Files · Images · Projects
 *   Settings    ← quiet, at the bottom
 *
 * Grouping comes from section labels + spacing — no hard dividers.
 */
@Composable
fun ConversationDrawer(
    conversations: List<Pair<String, String>>,
    currentConversationId: String?,
    onNewConversation: () -> Unit,
    onSelectConversation: (String) -> Unit,
    onNavigate: (String) -> Unit,
    onOpenSettings: () -> Unit,
) {
    ModalDrawerSheet {
        Column(
            Modifier
                .fillMaxHeight()
                .padding(vertical = Spacing.md)
        ) {
            Text(
                "Beanie",
                style = MaterialTheme.typography.titleMedium,
                fontWeight = FontWeight.Bold,
                modifier = Modifier.padding(horizontal = Spacing.lg, vertical = Spacing.xs),
            )
            NavigationDrawerItem(
                label = { Text("New chat") },
                selected = false,
                icon = { Icon(Icons.Default.Add, contentDescription = null) },
                onClick = onNewConversation,
                modifier = Modifier.padding(horizontal = Spacing.md),
            )

            DrawerSectionLabel("RECENT")
            LazyColumn(Modifier.weight(1f)) {
                items(conversations, key = { it.first }) { (id, title) ->
                    NavigationDrawerItem(
                        label = { Text(title.ifBlank { "Conversation" }, maxLines = 1) },
                        selected = id == currentConversationId,
                        onClick = { onSelectConversation(id) },
                        modifier = Modifier.padding(horizontal = Spacing.md),
                    )
                }
            }

            DrawerSectionLabel("WORKSPACE")
            listOf(
                "Pansophy" to "pansophy",
                "Files" to "files",
                "Images" to "images",
                "Projects" to "projects",
            ).forEach { (label, route) ->
                NavigationDrawerItem(
                    label = { Text(label) },
                    selected = false,
                    onClick = { onNavigate(route) },
                    modifier = Modifier.padding(horizontal = Spacing.md),
                )
            }

            Spacer(Modifier.height(Spacing.md))
            NavigationDrawerItem(
                label = { Text("Settings") },
                selected = false,
                icon = { Icon(Icons.Default.Settings, contentDescription = null) },
                onClick = onOpenSettings,
                modifier = Modifier.padding(horizontal = Spacing.md),
            )
        }
    }
}

@Composable
private fun DrawerSectionLabel(label: String) {
    Text(
        label,
        style = MaterialTheme.typography.labelMedium,
        color = MaterialTheme.colorScheme.onSurfaceVariant,
        modifier = Modifier.padding(
            start = Spacing.lg,
            end = Spacing.lg,
            top = Spacing.md,
            bottom = Spacing.xs,
        ),
    )
}
