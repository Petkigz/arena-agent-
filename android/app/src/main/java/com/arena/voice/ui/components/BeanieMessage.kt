package com.arena.voice.ui.components

import androidx.compose.foundation.layout.*
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.Surface
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp
import com.arena.voice.ui.chat.ChatMessage
import com.arena.voice.ui.theme.ArenaRadius
import com.arena.voice.ui.theme.Spacing

/**
 * One message in the conversation timeline (21j review, problem 1):
 *
 *   UserMessage      → accent bubble, right.
 *   AssistantMessage → Beanie's orb + surface bubble, with tool activity as
 *                      timeline rows BELOW the bubble (web parity — the web
 *                      renders ActionSteps under the bubble, not inside it).
 *
 * While streaming, the orb follows the LIVE voice state (one continuous
 * interaction: thinking while working, speaking during TTS).
 */
@Composable
fun BeanieMessage(msg: ChatMessage, voiceStatus: PresenceStatus = PresenceStatus.IDLE) {
    val isUser = msg.role == "user"
    Row(
        modifier = Modifier.fillMaxWidth(),
        horizontalArrangement = if (isUser) Arrangement.End else Arrangement.Start,
        verticalAlignment = Alignment.Top,
    ) {
        if (!isUser) {
            val liveStatus = when {
                !msg.isStreaming -> PresenceStatus.IDLE
                voiceStatus == PresenceStatus.SPEAKING -> PresenceStatus.SPEAKING
                else -> PresenceStatus.THINKING
            }
            ReactiveBeanieOrb(status = liveStatus, sizeDp = 28)
            Spacer(Modifier.width(Spacing.sm))
        }

        Column(Modifier.widthIn(max = 320.dp)) {
            Surface(
                color = if (isUser) MaterialTheme.colorScheme.primary else MaterialTheme.colorScheme.surface,
                shape = RoundedCornerShape(ArenaRadius.xxl),
            ) {
                Column(
                    Modifier.padding(
                        horizontal = Spacing.bubbleX,
                        vertical = Spacing.bubbleY,
                    )
                ) {
                    if (msg.isStreaming && msg.content.isBlank()) {
                        Text(
                            "Beanie is thinking…",
                            color = MaterialTheme.colorScheme.onSurfaceVariant,
                            fontSize = 12.sp,
                        )
                    }
                    Text(
                        text = msg.content.ifBlank { "" },
                        color = if (isUser) Color.White else MaterialTheme.colorScheme.onSurface,
                    )
                    if (msg.isStreaming) {
                        Text("▍", color = MaterialTheme.colorScheme.onSurfaceVariant)
                    }
                }
            }

            // Tool activity belongs to the timeline, not the bubble.
            if (!isUser && msg.actionSteps.isNotEmpty()) {
                Spacer(Modifier.height(Spacing.xs))
                ToolActivityTimeline(msg.actionSteps)
            }
        }
    }
}
