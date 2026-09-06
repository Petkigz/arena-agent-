package com.arena.voice.ui

import android.app.Activity
import android.os.Build
import androidx.compose.foundation.isSystemInDarkTheme
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.darkColorScheme
import androidx.compose.material3.dynamicDarkColorScheme
import androidx.compose.material3.dynamicLightColorScheme
import androidx.compose.material3.lightColorScheme
import androidx.compose.runtime.Composable
import androidx.compose.runtime.SideEffect
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.graphics.toArgb
import androidx.compose.ui.platform.LocalContext
import androidx.compose.ui.platform.LocalView
import androidx.core.view.WindowCompat

/**
 * ONE Arena theme — the same design tokens the web and desktop clients consume
 * (design/tokens.json), mapped onto Material 3 roles:
 *
 *   background   ← tokens.color.themes.*.background.primary
 *   surface      ← tokens.color.themes.*.background.secondary
 *   surfaceVariant ← background.surface (elevated / borders)
 *   onBackground/onSurface ← text.primary
 *   onSurfaceVariant ← text.secondary
 *   outline      ← text.muted
 *   primary/secondary/tertiary/error ← accent primary/success/warning/error
 *
 * Drift is machine-guarded: tests/test_android_design_tokens.py parses this
 * file against design/tokens.json, so the three clients cannot diverge.
 *
 * dynamicColor defaults to FALSE: Arena's identity is Arena's palette, not the
 * device wallpaper. (Material You can still be opted into explicitly.)
 */

private val DarkColorScheme = darkColorScheme(
    primary = Color(0xFF3B82F6),
    secondary = Color(0xFF10B981),
    tertiary = Color(0xFFF59E0B),
    error = Color(0xFFEF4444),
    background = Color(0xFF0F172A),
    surface = Color(0xFF1E293B),
    surfaceVariant = Color(0xFF334155),
    onPrimary = Color.White,
    onSecondary = Color.White,
    onTertiary = Color.White,
    onBackground = Color(0xFFF1F5F9),
    onSurface = Color(0xFFF1F5F9),
    onSurfaceVariant = Color(0xFF94A3B8),
    outline = Color(0xFF64748B),
)

private val LightColorScheme = lightColorScheme(
    primary = Color(0xFF3B82F6),
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

@Composable
fun ArenaVoiceTheme(
    darkTheme: Boolean = isSystemInDarkTheme(),
    dynamicColor: Boolean = false,
    content: @Composable () -> Unit
) {
    val colorScheme = when {
        dynamicColor && Build.VERSION.SDK_INT >= Build.VERSION_CODES.S -> {
            val context = LocalContext.current
            if (darkTheme) dynamicDarkColorScheme(context) else dynamicLightColorScheme(context)
        }
        darkTheme -> DarkColorScheme
        else -> LightColorScheme
    }

    val view = LocalView.current
    if (!view.isInEditMode) {
        SideEffect {
            val window = (view.context as Activity).window
            // Status bar follows the canvas, not the accent — Arena chrome stays quiet.
            window.statusBarColor = colorScheme.background.toArgb()
            WindowCompat.getInsetsController(window, view).isAppearanceLightStatusBars = !darkTheme
        }
    }

    MaterialTheme(
        colorScheme = colorScheme,
        typography = Typography,
        content = content
    )
}
