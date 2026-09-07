package com.arena.voice.ui.components

import androidx.compose.foundation.background
import androidx.compose.foundation.layout.*
import androidx.compose.foundation.shape.CircleShape
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.unit.dp
import com.arena.voice.ui.theme.ArenaRadius
import androidx.compose.ui.unit.sp
import androidx.compose.ui.platform.LocalContext

/**
 * The single voice indicator — one more reactive surface of the SAME
 * PresenceStatus machine (Problem 4: not several independent mechanisms;
 * the orb, the composer mic and this pill all read one state).
 */
@Composable
fun VoiceStatusIndicator(status: PresenceStatus) {
    val token = SharedPresenceTokens.forStatus(LocalContext.current, status)
    // status.color remains the compile-time enum contract; token.color is the
    // runtime value consumed by this surface from design/tokens.json.
    val label = when (status) {
        PresenceStatus.LISTENING -> "Listening…"
        PresenceStatus.THINKING -> "Thinking…"
        PresenceStatus.SPEAKING -> "Speaking…"
        else -> return
    }
    Box(Modifier.fillMaxWidth(), contentAlignment = Alignment.Center) {
        Row(
            Modifier
                .background(MaterialTheme.colorScheme.surface, RoundedCornerShape(ArenaRadius.xxl))
                .padding(horizontal = 12.dp, vertical = 6.dp),
            verticalAlignment = Alignment.CenterVertically,
        ) {
            Box(
                Modifier
                    .size(8.dp)
                    .background(token.color, CircleShape),
            )
            Spacer(Modifier.width(8.dp))
            Text(label, color = MaterialTheme.colorScheme.onSurface, fontSize = 13.sp)
        }
    }
}
