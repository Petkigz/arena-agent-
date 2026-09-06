package com.arena.voice.ui.theme

import androidx.compose.ui.unit.dp

/**
 * Elevation scale — derived from tokens.json shadow (Tailwind) by blur radius:
 * DEFAULT 1-3px -> level1, md 4-6px -> level2, lg 10-15px -> level3,
 * xl 20-25px -> level4. Compose drops shadows as tonal elevation instead of
 * box shadows; the ladder keeps the same quiet hierarchy.
 */
object Elevation {
    val level1 = 1.dp
    val level2 = 3.dp
    val level3 = 6.dp
    val level4 = 12.dp
}
