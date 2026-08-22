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
import androidx.compose.ui.graphics.PathEffect
import androidx.compose.ui.graphics.drawscope.Stroke
import androidx.compose.ui.graphics.drawscope.rotate
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp

/**
 * "Beanie" home screen — mirrors the web/desktop reactive-orb design.
 *
 * The orb is Beanie's *presence*, not an avatar: a layered translucent core
 * wrapped in a voice field of concentric ring-lines. The rings are not
 * decoration — they carry the cognitive/voice state (idle breathe, listening
 * (mic-reactive), thinking (circulating), acting (directional sweep), speaking
 * (outward TTS waves), success ripple, error disturbance, sleeping dim).
 */

enum class PresenceStatus(val color: Color, val pulseMs: Int) {
    IDLE(Color(0xFF3B82F6), 3400),
    WORKING(Color(0xFFF59E0B), 1600),
    LISTENING(Color(0xFF10B981), 1200),
    SPEAKING(Color(0xFF8B5CF6), 1050),
    OFFLINE(Color(0xFF334155), 0),
    THINKING(Color(0xFFF59E0B), 1600),
    ACTING(Color(0xFF38BDF8), 2000),
    OBSERVING(Color(0xFF38BDF8), 2000),
    SUCCESS(Color(0xFF10B981), 2000),
    ERROR(Color(0xFFEF4444), 400),
    SLEEPING(Color(0xFF334155), 5000),
}

/**
 * Reactive presence orb (Compose Canvas).
 *
 * @param level 0..1 amplitude (mic while listening, TTS while speaking). When
 * 0 the field uses autonomous motion so it never looks dead.
 */
@Composable
fun ReactiveBeanieOrb(
    status: PresenceStatus,
    level: Float = 0f,
    sizeDp: Int = 220,
    modifier: Modifier = Modifier,
) {
    val loopMs = if (status.pulseMs > 0) status.pulseMs else 1000

    val transition = rememberInfiniteTransition(label = "orb")

    // Continuous 0..1 phase (restarts each cycle) for rotation / outward / ripple.
    val phase by transition.animateFloat(
        initialValue = 0f,
        targetValue = 1f,
        animationSpec = infiniteRepeatable(
            animation = tween(loopMs, easing = LinearEasing),
            repeatMode = RepeatMode.Restart,
        ),
        label = "phase",
    )

    // 0..1 breathing (reverses) for the core sphere + idle ring pulse.
    val breath by transition.animateFloat(
        initialValue = 0f,
        targetValue = 1f,
        animationSpec = infiniteRepeatable(
            animation = tween(loopMs, easing = FastOutSlowInEasing),
            repeatMode = RepeatMode.Reverse,
        ),
        label = "breath",
    )

    // Smooth the input amplitude toward its target (idle → autonomous motion).
    val smoothLevel by animateFloatAsState(
        targetValue = level,
        animationSpec = tween(durationMillis = 120, easing = LinearEasing),
        label = "level",
    )

    Canvas(modifier = modifier.size(sizeDp.dp)) {
        val cx = size.width / 2f
        val cy = size.height / 2f
        val base = size.minDimension / 2f
        val color = status.color

        // ── Outer glow halo ──
        if (status != PresenceStatus.OFFLINE && status != PresenceStatus.SLEEPING) {
            drawCircle(
                brush = Brush.radialGradient(
                    colors = listOf(color.copy(alpha = 0.28f), Color.Transparent),
                    center = Offset(cx, cy),
                    radius = base,
                ),
                radius = base,
                center = Offset(cx, cy),
            )
        }

        // ── Voice-field rings (reactive line segments) ──
        if (status != PresenceStatus.OFFLINE && status != PresenceStatus.SLEEPING) {
            val ringRadii = listOf(base * 0.62f, base * 0.78f, base * 0.94f)
            ringRadii.forEachIndexed { i, r ->
                val (rotation, scale, alpha) = ringMotion(status, phase, breath, smoothLevel, i)
                if (alpha <= 0.01f) return@forEachIndexed
                rotate(degrees = rotation, pivot = Offset(cx, cy)) {
                    drawCircle(
                        color = color.copy(alpha = alpha),
                        radius = r * scale,
                        center = Offset(cx, cy),
                        style = Stroke(
                            width = 2.dp.toPx(),
                            pathEffect = PathEffect.dashPathEffect(
                                floatArrayOf(22f, 16f),
                                phase = i * 12f,
                            ),
                        ),
                    )
                }
            }
        }

        // ── Core sphere (3D radial gradient, highlight top-left) ──
        val coreScale = 0.96f + 0.05f * breath
        val coreR = base * 0.42f * coreScale
        drawCircle(
            brush = Brush.radialGradient(
                colors = listOf(
                    lighten(color, 0.7f),
                    color,
                    darken(color, 0.6f),
                ),
                center = Offset(cx - coreR * 0.3f, cy - coreR * 0.3f),
                radius = coreR * 1.5f,
            ),
            radius = coreR,
            center = Offset(cx, cy),
        )
        drawCircle(
            color = color.copy(alpha = 0.5f),
            radius = coreR,
            center = Offset(cx, cy),
            style = Stroke(width = 1.5.dp.toPx()),
        )

        // ── Inner highlight (light diffusion, not a face) ──
        drawCircle(
            color = Color.White.copy(alpha = 0.32f),
            radius = base * 0.14f,
            center = Offset(cx - base * 0.16f, cy - base * 0.16f),
        )

        // ── Focal point (presence, subtle) ──
        val focusPulse = if (status == PresenceStatus.OFFLINE || status == PresenceStatus.SLEEPING) 1f
        else 1f + 0.25f * breath
        drawCircle(
            color = color,
            radius = base * 0.07f * focusPulse,
            center = Offset(cx, cy),
        )
    }
}

/**
 * Per-ring motion as a Triple(rotationDegrees, scale, alpha) driven by the
 * looping phase / breath / smoothed amplitude, keyed by state.
 */
private fun ringMotion(
    status: PresenceStatus,
    phase: Float,
    breath: Float,
    level: Float,
    index: Int,
): Triple<Float, Float, Float> {
    return when (status) {
        PresenceStatus.IDLE -> {
            val s = 1f + 0.05f * breath
            Triple(0f, s, 0.28f)
        }
        PresenceStatus.WORKING -> {
            val s = 1f + 0.08f * breath
            Triple(0f, s, 0.4f)
        }
        PresenceStatus.LISTENING -> {
            // Reacts to amplitude; when silent, drifts autonomously.
            val amp = level * 0.14f * (1f - index * 0.18f)
            val auto = 0.04f * breath
            Triple(0f, 1f + amp + auto, 0.3f + level * 0.35f)
        }
        PresenceStatus.SPEAKING -> {
            // Outward-traveling waves.
            val s = 1f + phase * 0.55f + level * 0.1f
            val a = (0.55f * (1f - phase)).coerceIn(0f, 0.55f)
            Triple(0f, s, a)
        }
        PresenceStatus.THINKING -> {
            val dir = if (index % 2 == 0) 1f else -1f
            Triple(phase * 360f * dir, 1f, 0.38f)
        }
        PresenceStatus.ACTING -> {
            val dir = if (index % 2 == 0) 1f else -1f
            Triple(phase * 360f * dir, 1f, 0.42f)
        }
        PresenceStatus.OBSERVING -> {
            val dir = if (index % 2 == 0) 1f else -1f
            Triple(phase * 360f * dir, 1f, 0.36f)
        }
        PresenceStatus.SUCCESS -> {
            val s = 0.55f + phase * 1.15f
            val a = (0.85f * (1f - phase)).coerceIn(0f, 0.85f)
            Triple(0f, s, a)
        }
        PresenceStatus.ERROR -> {
            // Rapid disturbance: scale jitter.
            val jitter = if ((phase * 10).toInt() % 2 == 0) 1.08f else 0.94f
            Triple(0f, jitter, 0.5f)
        }
        PresenceStatus.SLEEPING,
        PresenceStatus.OFFLINE -> Triple(0f, 1f, 0f)
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
            ReactiveBeanieOrb(status = presenceStatus, sizeDp = 220)

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
