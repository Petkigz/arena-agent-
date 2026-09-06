package com.arena.voice.ui.components

import androidx.compose.foundation.layout.*
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.unit.sp
import com.arena.voice.ui.theme.Spacing

/**
 * Empty conversation surface — Beanie's presence and an invitation, nothing
 * else. The orb is the same shared component as the landing and the timeline.
 */
@Composable
fun BeanieEmptyState(modifier: Modifier = Modifier) {
    Column(
        modifier
            .fillMaxSize()
            .padding(Spacing.xl),
        horizontalAlignment = Alignment.CenterHorizontally,
        verticalArrangement = Arrangement.Center,
    ) {
        ReactiveBeanieOrb(status = PresenceStatus.IDLE, sizeDp = 96)
        Spacer(Modifier.height(Spacing.lg))
        Text("I'm Beanie.", color = MaterialTheme.colorScheme.onBackground, fontSize = 18.sp)
        Text(
            "Send a message or tap the mic to talk.",
            color = MaterialTheme.colorScheme.onSurfaceVariant,
            fontSize = 13.sp,
        )
    }
}
