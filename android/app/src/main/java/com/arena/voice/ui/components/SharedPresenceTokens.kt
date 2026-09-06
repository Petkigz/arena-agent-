package com.arena.voice.ui.components

import android.content.Context
import androidx.compose.ui.graphics.Color
import org.json.JSONObject

/**
 * Runtime view of the canonical design/tokens.json presence state table.
 *
 * The Android APK packages the root design file as an asset from Gradle. This
 * keeps the token file as the source of truth while allowing the orb, voice
 * pill, composer and working-context affordance to consume the same values at
 * runtime. A missing or malformed asset is deliberately surfaced as an
 * actionable exception instead of silently falling back to stale styling.
 */
object SharedPresenceTokens {
    data class Token(val color: Color, val pulseMs: Int)

    private var cached: Map<String, Token>? = null

    @Synchronized
    private fun load(context: Context): Map<String, Token> {
        cached?.let { return it }

        val source = try {
            context.assets.open("tokens.json").bufferedReader().use { it.readText() }
        } catch (error: Exception) {
            throw IllegalStateException(
                "Arena design token asset tokens.json is missing. " +
                    "Build the Android app from the repository so design/tokens.json is packaged.",
                error,
            )
        }

        val states = try {
            JSONObject(source).getJSONObject("beanie").getJSONObject("states")
        } catch (error: Exception) {
            throw IllegalStateException(
                "Arena design token asset tokens.json has no valid beanie.states table.",
                error,
            )
        }

        val parsed = states.keys().asSequence().associateWith { state ->
            val spec = states.getJSONObject(state)
            val hex = spec.getString("color").removePrefix("#")
            val argb = if (hex.length == 6) "FF$hex" else hex
            Token(
                color = Color(android.graphics.Color.parseColor("#$argb")),
                pulseMs = spec.getInt("duration_ms"),
            )
        }
        cached = parsed
        return parsed
    }

    fun forStatus(context: Context, status: PresenceStatus): Token {
        return load(context)[status.name.lowercase()]
            ?: throw IllegalStateException(
                "Arena design tokens do not define beanie state '${status.name.lowercase()}'."
            )
    }
}
