package com.arena.voice.ui.screens

import androidx.compose.animation.core.*
import androidx.compose.foundation.Canvas
import androidx.compose.foundation.layout.*
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.filled.Mic
import androidx.compose.material.icons.filled.MicOff
import androidx.compose.material.icons.filled.Send
import androidx.compose.material3.*
import androidx.compose.runtime.*
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.geometry.Offset
import androidx.compose.ui.graphics.Brush
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.graphics.PathEffect
import androidx.compose.ui.graphics.drawscope.Stroke
import androidx.compose.ui.graphics.drawscope.rotate
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp
import com.arena.voice.ui.components.PresenceStatus
import com.arena.voice.ui.components.ReactiveBeanieOrb

/**
 * "Beanie" home screen — mirrors the web/desktop reactive-orb design.
 *
 * The orb is Beanie's *presence*, not an avatar: a layered translucent core
 * wrapped in a voice field of concentric ring-lines. The rings are not
 * decoration — they carry the cognitive/voice state (idle breathe, listening
 * (mic-reactive), thinking (circulating), acting (directional sweep), speaking
 * (outward TTS waves), success ripple, error disturbance, sleeping dim).
 */


@Composable
fun BeanieScreen(
    presenceStatus: PresenceStatus = PresenceStatus.IDLE,
    statusMessage: String = "What are we working on today?",
    isListening: Boolean = false,
    onToggleTalk: () -> Unit = {},
    onQuickAction: (String) -> Unit = {},
    onSubmit: (String) -> Unit = {},
) {
    var input by remember { mutableStateOf("") }

    Column(
        modifier = Modifier
            .fillMaxSize()
            .padding(16.dp),
        horizontalAlignment = Alignment.CenterHorizontally,
        verticalArrangement = Arrangement.Center,
    ) {
        // ── Presence orb — Beanie's identity ──
        ReactiveBeanieOrb(status = presenceStatus, sizeDp = 200)

        Spacer(modifier = Modifier.height(16.dp))
        Text(
            text = "Beanie",
            fontSize = 30.sp,
            fontWeight = FontWeight.Bold,
            color = MaterialTheme.colorScheme.onBackground,
        )
        Text(greeting(), fontSize = 16.sp, color = MaterialTheme.colorScheme.onSurfaceVariant)
        Text(
            text = statusMessage,
            fontSize = 12.sp,
            color = MaterialTheme.colorScheme.outline,
            fontStyle = androidx.compose.ui.text.font.FontStyle.Italic,
        )

        Spacer(modifier = Modifier.height(24.dp))

        // ── Landing composer: Ask Beanie anything… | 🎙 | ➤ ──
        Row(
            modifier = Modifier.fillMaxWidth(),
            verticalAlignment = Alignment.CenterVertically,
        ) {
            OutlinedTextField(
                value = input,
                onValueChange = { input = it },
                modifier = Modifier.weight(1f),
                placeholder = { Text("Ask Beanie anything…") },
                shape = RoundedCornerShape(16.dp),
                maxLines = 3,
            )
            IconButton(onClick = onToggleTalk) {
                Icon(
                    imageVector = if (isListening) Icons.Default.MicOff else Icons.Default.Mic,
                    contentDescription = "Voice input",
                    tint = MaterialTheme.colorScheme.onSurfaceVariant,
                )
            }
            IconButton(
                onClick = {
                    if (input.isNotBlank()) {
                        onSubmit(input)
                        input = ""
                    }
                },
                enabled = input.isNotBlank(),
            ) {
                Icon(
                    Icons.Default.Send,
                    contentDescription = "Send",
                    tint = MaterialTheme.colorScheme.primary,
                )
            }
        }

        Spacer(modifier = Modifier.height(12.dp))

        // ── Subtle suggestions (the old 56dp tiles, dramatically reduced) ──
        Row(horizontalArrangement = Arrangement.spacedBy(8.dp)) {
            listOf(
                "Continue project" to "continue_project",
                "What's new?" to "whats_new",
                "Research" to "research",
                "Talk to me" to "talk",
            ).forEach { (label, action) ->
                TextButton(onClick = { onQuickAction(action) }) {
                    Text(label, fontSize = 12.sp, color = MaterialTheme.colorScheme.onSurfaceVariant)
                }
            }
        }
    }
}

/** Time-based greeting — same rule as the desktop landing. */
private fun greeting(): String {
    val hour = java.util.Calendar.getInstance().get(java.util.Calendar.HOUR_OF_DAY)
    return when {
        hour < 12 -> "Good morning."
        hour < 18 -> "Good afternoon."
        else -> "Good evening."
    }
}
