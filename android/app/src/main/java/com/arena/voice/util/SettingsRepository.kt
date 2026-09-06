package com.arena.voice.util

import android.content.Context
import androidx.datastore.core.DataStore
import androidx.datastore.preferences.core.Preferences
import androidx.datastore.preferences.core.edit
import androidx.datastore.preferences.core.booleanPreferencesKey
import androidx.datastore.preferences.core.stringPreferencesKey
import androidx.datastore.preferences.preferencesDataStore
import dagger.hilt.android.qualifiers.ApplicationContext
import kotlinx.coroutines.flow.Flow
import kotlinx.coroutines.flow.first
import kotlinx.coroutines.flow.distinctUntilChanged
import kotlinx.coroutines.flow.map
import javax.inject.Inject
import javax.inject.Singleton

/**
 * Persisted voice-app settings (backed by Jetpack DataStore).
 *
 * The server URL was previously hardcoded (ws://10.0.2.2:8000/ws — the emulator
 * alias to the host). This lets a physical device point at the PC's LAN IP
 * without rebuilding the app.
 */

private val Context.dataStore: DataStore<Preferences> by preferencesDataStore(name = "arena_settings")

@Singleton
class SettingsRepository @Inject constructor(
    @ApplicationContext private val context: Context,
) {
    companion object {
        private val KEY_SERVER_URL = stringPreferencesKey("server_url")
        private val KEY_API_KEY = stringPreferencesKey("api_key")
        private val KEY_THEME = stringPreferencesKey("theme")
        private val KEY_WAKE_WORD = booleanPreferencesKey("wake_word_enabled")

        /** Emulator default: 10.0.2.2 aliases the host machine's localhost. */
        const val DEFAULT_SERVER_URL = "ws://10.0.2.2:8000/ws"
    }

    val serverUrl: Flow<String> = context.dataStore.data.map { prefs ->
        prefs[KEY_SERVER_URL] ?: DEFAULT_SERVER_URL
    }

    /** API key for authenticated backends (matches the web's X-API-Key / VITE_API_KEY). */
    val apiKey: Flow<String> = context.dataStore.data.map { prefs ->
        prefs[KEY_API_KEY] ?: ""
    }

    /**
     * Always-on wake-word listening ("Hey Beanie"). OPT-IN, default false: a
     * foreground mic service holds the microphone (status-bar indicator) and
     * the recognizer beeps on its idle cycle — the owner decides when that
     * trade is wanted. The mic button / Settings toggle both write this.
     */
    val wakeWordEnabled: Flow<Boolean> = context.dataStore.data.map { prefs ->
        prefs[KEY_WAKE_WORD] ?: false
    }.distinctUntilChanged()

    /** Theme ("dark" | "light" | "system"), cached locally for instant app-level re-skinning. */
    val theme: Flow<String> = context.dataStore.data.map { prefs ->
        prefs[KEY_THEME] ?: "dark"
    }

    suspend fun setServerUrl(url: String) {
        val cleaned = url.trim().let { if (it.isEmpty()) DEFAULT_SERVER_URL else it }
        context.dataStore.edit { prefs -> prefs[KEY_SERVER_URL] = cleaned }
    }

    suspend fun setApiKey(key: String) {
        context.dataStore.edit { prefs -> prefs[KEY_API_KEY] = key.trim() }
    }

    suspend fun setWakeWordEnabled(enabled: Boolean) {
        context.dataStore.edit { prefs -> prefs[KEY_WAKE_WORD] = enabled }
    }

    suspend fun setTheme(theme: String) {
        val raw = theme.trim().lowercase()
        val normalized = when (raw) {
            "light" -> "light"
            "system" -> "system"
            else -> "dark"
        }
        context.dataStore.edit { prefs -> prefs[KEY_THEME] = normalized }
    }

    /** Derive the HTTP base URL (http://…) from the WebSocket URL (ws://…). */
    suspend fun httpBaseUrl(): String {
        val ws = serverUrl.first()
        return ws
            .replace("wss://", "https://")
            .replace("ws://", "http://")
            .substringBefore("/ws")
    }
}
