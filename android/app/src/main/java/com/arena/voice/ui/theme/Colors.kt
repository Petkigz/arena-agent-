package com.arena.voice.ui.theme

import androidx.compose.material3.darkColorScheme
import androidx.compose.material3.lightColorScheme
import androidx.compose.ui.graphics.Color

/**
 * ONE Arena palette — the same design tokens the web and desktop clients
 * consume (design/tokens.json), mapped onto Material 3 roles:
 *
 *   background / surface / surfaceVariant ← background primary/secondary/surface
 *   onBackground / onSurface / onSurfaceVariant / outline ← text primary/secondary/muted
 *   primary / secondary / tertiary / error ← accent primary/success/warning/error
 *
 * Drift is machine-guarded: tests/test_android_design_tokens.py parses this
 * file against design/tokens.json, so the three clients cannot diverge.
 */

val DarkColorScheme = darkColorScheme(
    primary = Color(0xFF3D74FF),
    secondary = Color(0xFF10B981),
    tertiary = Color(0xFFF59E0B),
    error = Color(0xFFEF4444),
    background = Color(0xFF060A16),
    surface = Color(0xFF0B1226),
    surfaceVariant = Color(0xFF151F3A),
    onPrimary = Color.White,
    onSecondary = Color.White,
    onTertiary = Color.White,
    onBackground = Color(0xFFF1F5F9),
    onSurface = Color(0xFFF1F5F9),
    onSurfaceVariant = Color(0xFF94A3B8),
    outline = Color(0xFF64748B),
)

val LightColorScheme = lightColorScheme(
    primary = Color(0xFF3D74FF),
    secondary = Color(0xFF10B981),
    tertiary = Color(0xFFF59E0B),
    error = Color(0xFFEF4444),
    background = Color(0xFFF8FAFC),
    surface = Color(0xFFE2E8F0),
    surfaceVariant = Color(0xFFCBD5E1),
    onPrimary = Color.White,
    onSecondary = Color.White,
    onTertiary = Color.White,
    onBackground = Color(0xFF1E293B),
    onSurface = Color(0xFF1E293B),
    onSurfaceVariant = Color(0xFF475569),
    outline = Color(0xFF64748B),
)
