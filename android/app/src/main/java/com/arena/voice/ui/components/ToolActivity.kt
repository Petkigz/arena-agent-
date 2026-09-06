package com.arena.voice.ui.components

import androidx.compose.animation.core.LinearEasing
import androidx.compose.animation.core.animateFloat
import androidx.compose.animation.core.infiniteRepeatable
import androidx.compose.animation.core.rememberInfiniteTransition
import androidx.compose.animation.core.tween
import androidx.compose.foundation.background
import androidx.compose.foundation.layout.*
import androidx.compose.foundation.shape.CircleShape
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.filled.CheckCircle
import androidx.compose.material.icons.filled.Error
import androidx.compose.material.icons.filled.Refresh
import androidx.compose.material3.Icon
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.runtime.getValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.draw.clip
import androidx.compose.ui.graphics.graphicsLayer
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp
import com.arena.voice.ui.chat.ToolActivity

/**
 * Tool activity as part of the RESPONSE TIMELINE (21j review, problem 5) —
 * plain semantic rows under the message, never a card nested in the bubble:
 *
 *   Beanie
 *     Searching files              ⟳
 *     Found 3 matching files       ✓
 *     Here's what I found…
 *
 * Same semantic event the web's ActionSteps renders (status icons + tinted
 * labels); raw diagnostic output never reaches the surface.
 */
@Composable
fun ToolActivityTimeline(activities: List<ToolActivity>) {
    Column(verticalArrangement = Arrangement.spacedBy(6.dp)) {
        activities.takeLast(3).forEach { activity ->
            ToolActivityRow(activity)
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
