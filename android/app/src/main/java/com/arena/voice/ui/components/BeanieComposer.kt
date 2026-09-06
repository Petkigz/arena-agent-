package com.arena.voice.ui.components

import androidx.compose.foundation.BorderStroke
import androidx.compose.foundation.layout.*
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.foundation.text.BasicTextField
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.filled.AttachFile
import androidx.compose.material.icons.filled.Mic
import androidx.compose.material.icons.filled.Send
import androidx.compose.material3.Icon
import androidx.compose.material3.IconButton
import androidx.compose.material3.LocalTextStyle
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.Surface
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.setValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.focus.onFocusChanged
import androidx.compose.ui.graphics.SolidColor
import androidx.compose.ui.unit.sp
import com.arena.voice.ui.theme.ArenaRadius
import com.arena.voice.ui.theme.Elevation
import com.arena.voice.ui.theme.Spacing

/**
 * ComposerDock (21j review, problem 2) — ONE integrated Beanie input surface,
 * not four Material controls beside each other:
 *
 *   ┌─────────────────────────────────────────┐
 *   │  +   Message Beanie…             🎙   ↑  │
 *   └─────────────────────────────────────────┘
 *
 * The outer container owns background, border, radius, elevation, spacing,
 * focus/disabled states. The inner controls are chrome-less (BasicTextField,
 * quiet icons) so nothing reads as "standard Android form". The mic reacts to
 * the SAME presence state machine as the orb and the voice pill.
 */
@Composable
fun BeanieComposer(
    value: String,
    onValueChange: (String) -> Unit,
    onSend: () -> Unit,
    onAttach: () -> Unit,
    onVoiceToggle: () -> Unit,
    voiceStatus: PresenceStatus,
    enabled: Boolean,
    modifier: Modifier = Modifier,
) {
    var focused by remember { mutableStateOf(false) }
    val canSend = enabled && value.isNotBlank()

    Surface(
        color = MaterialTheme.colorScheme.surface,
        shape = RoundedCornerShape(ArenaRadius.xxl),
        // Focus state: the border quietly picks up the accent (focus ring).
        border = BorderStroke(
            width = if (focused) 2.dp else 1.dp,
            color = if (focused) {
                MaterialTheme.colorScheme.primary.copy(alpha = 0.55f)
            } else {
                MaterialTheme.colorScheme.surfaceVariant
            },
        ),
        shadowElevation = Elevation.level1,
        modifier = modifier
            .fillMaxWidth()
            .padding(horizontal = Spacing.lg, vertical = Spacing.sm),
    ) {
        Row(
            verticalAlignment = Alignment.Bottom,
            modifier = Modifier.padding(end = Spacing.xs),
        ) {
            // + attach — quiet, part of the surface.
            IconButton(onClick = onAttach, enabled = enabled) {
                Icon(
                    Icons.Default.AttachFile,
                    contentDescription = "Attach file",
                    tint = MaterialTheme.colorScheme.onSurfaceVariant,
                )
            }

            // The input itself: no Material chrome, no inner borders.
            BasicTextField(
                value = value,
                onValueChange = onValueChange,
                modifier = Modifier
                    .weight(1f)
                    .align(Alignment.CenterVertically)
                    .padding(vertical = 14.dp)
                    .onFocusChanged { focused = it.isFocused },
                textStyle = LocalTextStyle.current.copy(
                    color = MaterialTheme.colorScheme.onBackground,
                ),
                cursorBrush = SolidColor(MaterialTheme.colorScheme.primary),
                maxLines = 4,
                decorationBox = { innerTextField ->
                    Box(Modifier.fillMaxWidth()) {
                        if (value.isEmpty()) {
                            Text(
                                "Message Beanie…",
                                color = MaterialTheme.colorScheme.onSurfaceVariant,
                                fontSize = 15.sp,
                            )
                        }
                        innerTextField()
                    }
                },
            )

            // 🎙 — reacts to the live presence state (listening turns it on).
            val listening = voiceStatus == PresenceStatus.LISTENING
            IconButton(onClick = onVoiceToggle, enabled = enabled) {
                Icon(
                    Icons.Default.Mic,
                    contentDescription = "Voice input",
                    tint = if (listening) {
                        PresenceStatus.LISTENING.color
                    } else {
                        MaterialTheme.colorScheme.onSurfaceVariant
                    },
                )
            }

            // ↑ — the single accent control, alive only when there's text.
            IconButton(onClick = onSend, enabled = canSend) {
                Icon(
                    Icons.Default.Send,
                    contentDescription = "Send",
                    tint = if (canSend) {
                        MaterialTheme.colorScheme.primary
                    } else {
                        MaterialTheme.colorScheme.outline
                    },
                )
            }
        }
    }
}
