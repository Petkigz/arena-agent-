package com.arena.voice.ui.theme

import androidx.compose.ui.unit.dp

/**
 * Spacing scale — tokens.json spacing (unit 4, scale [4, 8, 12, 16, 24, 32]).
 * One rhythm for every screen; pinned by tests/test_android_design_tokens.py.
 */
object Spacing {
    val xs = 4.dp   // scale[0]
    val sm = 8.dp   // scale[1]
    val md = 12.dp  // scale[2]
    val lg = 16.dp  // scale[3]
    val xl = 24.dp  // scale[4]
    val xxl = 32.dp // scale[5]

    /** Field inner padding (field_padding 12 x 8). */
    val fieldX = 12.dp
    val fieldY = 8.dp

    /** Message bubble inner padding (bubble_padding 16 x 10). */
    val bubbleX = 16.dp
    val bubbleY = 10.dp
}
