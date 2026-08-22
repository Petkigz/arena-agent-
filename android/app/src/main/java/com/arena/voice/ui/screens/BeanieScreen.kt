package com.arena.voice.ui.screens

import androidx.compose.animation.core.*
import androidx.compose.foundation.Canvas
import androidx.compose.foundation.layout.*
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.filled.Mic
import androidx.compose.material.icons.filled.MicOff
import androidx.compose.material3.*
import androidx.compose.runtime.*
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.geometry.Offset
import androidx.compose.ui.graphics.Brush
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp

/**
 * "Beanie" home screen — matches the web/desktop floating-orb design.
 * A breathing presence orb whose color/pulse reflects the agent state.
 */

enum class PresenceStatus(val color: Color, val pulseMs: Int) {
    IDLE(Color(0xFF3B82F6), 2200),
    WORKING(Color(0xFFF59E0B), 1000),
    LISTENING(Color(0xFF10B981), 1500),
    SPEAKING(Color(0xFF8B5CF6), 1200),
    OFFLINE(Color(0xFF334155), 0),
}

/** A floating, breathing, glowing sphere (Compose Canvas). */
@Composable
fun PresenceOrb(status: PresenceStatus, sizeDp: Int = 220, modifier: Modifier = Modifier) {
    val transition = rememberInfiniteTransition(label = "orb")
    val breath by transition.animateFloat(
        initialValue = 0f,
        targetValue = 1f,
        animationSpec = infiniteRepeatable(
            animation = tween(status.pulseMs, easing = FastOutSlowInEasing),
            repeatMode = RepeatMode.Reverse,
        ),
        label = "breath",
    )

    val radius = sizeDp / 2f

    Canvas(modifier = modifier.size(sizeDp.dp)) {
        val center = Offset(size.width / 2f, size.height / 2f)
        val orbRadius = radius * (0.82f + 0.10f * breath)

        // Outer glow.
        drawCircle(
            brush = Brush.radialGradient(
                colors = listOf(status.color.copy(alpha = 0.25f), Color.Transparent),
                center = center,
                radius = radius,
            ),
            radius = radius,
            center = center,
        )

        // 3D sphere (highlight top-left).
        drawCircle(
            brush = Brush.radialGradient(
                colors = listOf(
                    lighten(status.color, 0.7f),
                    status.color,
                    darken(status.color, 0.6f),
                ),
                center = Offset(center.x - radius * 0.3f, center.y - radius * 0.3f),
                radius = orbRadius * 1.4f,
            ),
            radius = orbRadius,
            center = center,
        )
    }
}

private fun lighten(color: Color, factor: Float): Color {
    return Color(
        red = (color.red + (1f - color.red) * factor).coerceIn(0f, 1f),
        green = (color.green + (1f - color.green) * factor).coerceIn(0f, 1f),
        blue = (color.blue + (1f - color.blue) * factor).coerceIn(0f, 1f),
        alpha = 1f,
    )
}

private fun darken(color: Color, factor: Float): Color {
    return Color(
        red = (color.red * (1f - factor)).coerceIn(0f, 1f),
        green = (color.green * (1f - factor)).coerceIn(0f, 1f),
        blue = (color.blue * (1f - factor)).coerceIn(0f, 1f),
        alpha = 1f,
    )
}

@Composable
fun BeanieScreen(
    presenceStatus: PresenceStatus = PresenceStatus.IDLE,
    statusMessage: String = "I'm here.",
    isListening: Boolean = false,
    onToggleTalk: () -> Unit = {},
    onQuickAction: (String) -> Unit = {},
) {
    Column(
        modifier = Modifier
            .fillMaxSize()
            .padding(16.dp),
        horizontalAlignment = Alignment.CenterHorizontally,
        verticalArrangement = Arrangement.SpaceBetween,
    ) {
        // ── Presence orb ──
        Column(
            horizontalAlignment = Alignment.CenterHorizontally,
            modifier = Modifier.padding(top = 24.dp),
        ) {
            PresenceOrb(status = presenceStatus, sizeDp = 220)

            Spacer(modifier = Modifier.height(16.dp))
            Text(
                text = "BEANIE",
                fontSize = 30.sp,
                fontWeight = FontWeight.ExtraBold,
                color = MaterialTheme.colorScheme.onBackground,
            )
            Text("Personal AI", fontSize = 15.sp, color = Color(0xFFCBD5E1))
            Text(
                text = statusMessage,
                fontSize = 13.sp,
                color = Color(0xFF94A3B8),
                fontStyle = androidx.compose.ui.text.font.FontStyle.Italic,
            )
        }

        // ── Quick actions ──
        val quickActions = listOf(
            "Continue project" to "continue_project",
            "What's new?" to "whats_new",
            "Research" to "research",
            "Talk to me" to "talk",
        )
        Column(
            verticalArrangement = Arrangement.spacedBy(10.dp),
            modifier = Modifier.fillMaxWidth(0.85f),
        ) {
            quickActions.chunked(2).forEach { row ->
                Row(horizontalArrangement = Arrangement.spacedBy(10.dp)) {
                    row.forEach { (label, action) ->
                        OutlinedButton(
                            onClick = { onQuickAction(action) },
                            modifier = Modifier.weight(1f).height(56.dp),
                            shape = RoundedCornerShape(12.dp),
                        ) {
                            Text(label, fontSize = 14.sp, fontWeight = FontWeight.SemiBold)
                        }
                    }
                    repeat(2 - row.size) { Spacer(modifier = Modifier.weight(1f)) }
                }
            }
        }

        // ── Talk to Beanie ──
        Button(
            onClick = onToggleTalk,
            modifier = Modifier
                .fillMaxWidth(0.85f)
                .height(56.dp),
            shape = RoundedCornerShape(14.dp),
        ) {
            Icon(
                imageVector = if (isListening) Icons.Default.MicOff else Icons.Default.Mic,
                contentDescription = null,
            )
            Spacer(modifier = Modifier.width(8.dp))
            Text(if (isListening) "Stop listening" else "🎙  Talk to Beanie")
        }
        Spacer(modifier = Modifier.height(24.dp))
    }
}
