package com.arena.voice.util

import android.content.Context
import androidx.datastore.core.DataStore
import androidx.datastore.preferences.core.Preferences
import androidx.datastore.preferences.core.edit
import androidx.datastore.preferences.core.stringPreferencesKey
import androidx.datastore.preferences.preferencesDataStore
import dagger.hilt.android.qualifiers.ApplicationContext
import kotlinx.coroutines.flow.Flow
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

        /** Emulator default: 10.0.2.2 aliases the host machine's localhost. */
        const val DEFAULT_SERVER_URL = "ws://10.0.2.2:8000/ws"
    }

    val serverUrl: Flow<String> = context.dataStore.data.map { prefs ->
        prefs[KEY_SERVER_URL] ?: DEFAULT_SERVER_URL
    }

    suspend fun setServerUrl(url: String) {
        val cleaned = url.trim().let { if (it.isEmpty()) DEFAULT_SERVER_URL else it }
        context.dataStore.edit { prefs -> prefs[KEY_SERVER_URL] = cleaned }
    }
}
