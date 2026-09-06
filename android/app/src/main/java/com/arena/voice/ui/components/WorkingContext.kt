package com.arena.voice.ui.components

import androidx.compose.foundation.layout.*
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.filled.KeyboardArrowRight
import androidx.compose.material3.*
import androidx.compose.runtime.*
import androidx.compose.foundation.background
import androidx.compose.foundation.clickable
import androidx.compose.foundation.shape.CircleShape
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.draw.clip
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.text.style.TextOverflow
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp
import com.arena.voice.ui.chat.WorkingContext
import com.arena.voice.ui.theme.ArenaRadius
import com.arena.voice.ui.theme.Spacing

/**
 * Working context, mobile presentation (design review section 4 + 21j review):
 *
 *   collapsed → ONE quiet line:  ◉ Working on  Project · Objective   ›
 *   expanded  → bottom sheet with the full picture (detail belongs there).
 *
 * The component owns its sheet state — screens just compose it.
 */
@OptIn(ExperimentalMaterial3Api::class)
@Composable
fun WorkingContextAffordance(context: WorkingContext) {
    val hasDetail = context.project != null || context.objective != null || context.memories > 0
    if (!hasDetail) return

    var showSheet by remember { mutableStateOf(false) }

    Row(
        Modifier
            .fillMaxWidth()
            .padding(horizontal = Spacing.lg, vertical = Spacing.xs)
            .clip(RoundedCornerShape(ArenaRadius.xl))
            .background(MaterialTheme.colorScheme.surfaceVariant.copy(alpha = 0.35f))
            .clickable { showSheet = true }
            .padding(horizontal = Spacing.md, vertical = Spacing.sm),
        verticalAlignment = Alignment.CenterVertically,
    ) {
        Box(
            Modifier
                .size(8.dp)
                .background(PresenceStatus.WORKING.color, CircleShape)
        )
        Spacer(Modifier.width(Spacing.sm))
        Text("Working on", fontSize = 12.sp, color = MaterialTheme.colorScheme.onSurfaceVariant)
        Spacer(Modifier.width(Spacing.sm))
        Text(
            listOfNotNull(context.project, context.objective)
                .joinToString(" · ")
                .ifBlank { "current work" },
            fontSize = 12.sp,
            fontWeight = FontWeight.SemiBold,
            color = MaterialTheme.colorScheme.onSurface,
            maxLines = 1,
            overflow = TextOverflow.Ellipsis,
            modifier = Modifier.weight(1f, fill = false),
        )
        Icon(
            Icons.Default.KeyboardArrowRight,
            contentDescription = "Working context",
            tint = MaterialTheme.colorScheme.outline,
            modifier = Modifier.size(18.dp),
        )
    }

    if (showSheet) {
        ModalBottomSheet(onDismissRequest = { showSheet = false }) {
            Text(
                "Working context",
                style = MaterialTheme.typography.titleMedium,
                modifier = Modifier.padding(horizontal = Spacing.xl, vertical = Spacing.xs),
            )
            context.project?.let { ContextSheetRow("PROJECT", it) }
            context.objective?.let { ContextSheetRow("OBJECTIVE", it) }
            if (context.memories > 0) {
                ContextSheetRow("RELEVANT MEMORY", "${context.memories} memories")
            }
            Spacer(Modifier.height(Spacing.xxl))
        }
    }
}

@Composable
private fun ContextSheetRow(label: String, value: String) {
    Column(Modifier.padding(horizontal = Spacing.xl, vertical = Spacing.sm)) {
        Text(
            label,
            style = MaterialTheme.typography.labelMedium,
            color = MaterialTheme.colorScheme.onSurfaceVariant,
        )
        Text(value, style = MaterialTheme.typography.bodyLarge)
    }
}
