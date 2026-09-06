package com.arena.voice

import android.Manifest
import android.content.Intent
import android.content.pm.PackageManager
import android.os.Build
import android.os.Bundle
import android.util.Log
import androidx.activity.ComponentActivity
import androidx.activity.compose.setContent
import androidx.activity.result.contract.ActivityResultContracts
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.Surface
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.setValue
import androidx.compose.ui.Modifier
import androidx.core.content.ContextCompat
import androidx.lifecycle.lifecycleScope
import com.arena.voice.api.ApiClient
import com.arena.voice.service.WakeWordService
import com.arena.voice.ui.AppScaffold
import com.arena.voice.ui.ArenaVoiceTheme
import com.arena.voice.ui.screens.PresenceStatus
import com.arena.voice.util.SettingsRepository
import com.arena.voice.websocket.VoiceWebSocketClient
import dagger.hilt.android.AndroidEntryPoint
import kotlinx.coroutines.launch
import org.json.JSONObject
import javax.inject.Inject

@AndroidEntryPoint
class MainActivity : ComponentActivity() {

    @Inject
    lateinit var webSocketClient: VoiceWebSocketClient

    @Inject
    lateinit var settings: SettingsRepository

    @Inject
    lateinit var apiClient: ApiClient

    private var serverUrl by mutableStateOf(SettingsRepository.DEFAULT_SERVER_URL)
    private var apiKey by mutableStateOf("")
    private var theme by mutableStateOf("dark")
    private var isConnected by mutableStateOf(false)
    private var isListening by mutableStateOf(false)
    private var voiceState by mutableStateOf<String?>(null)

    private val requestPermissionLauncher = registerForActivityResult(
        ActivityResultContracts.RequestMultiplePermissions()
    ) { permissions ->
        val denied = permissions.filterValues { !it }.keys
        if (denied.isNotEmpty()) {
            Log.w(TAG, "Some permissions denied: $denied")
        }
        val micGranted = permissions[Manifest.permission.RECORD_AUDIO] == true ||
            ContextCompat.checkSelfPermission(
                this, Manifest.permission.RECORD_AUDIO
            ) == PackageManager.PERMISSION_GRANTED
        if (micGranted) {
            startServices()
        } else {
            Log.e(TAG, "Microphone permission denied — voice assistant cannot start.")
        }
    }

    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)

        // Load persisted settings so the UI can show/edit them.
        lifecycleScope.launch {
            settings.serverUrl.collect { url -> serverUrl = url }
        }
        lifecycleScope.launch {
            settings.apiKey.collect { key -> apiKey = key }
        }
        lifecycleScope.launch {
            settings.theme.collect { t -> theme = t }
        }

        // Hydrate the theme from the backend's shared settings so a theme change
        // made on web/desktop is honored here too (fall back to the local
        // DataStore value on failure). (regression B3) — now supports 'system'.
        lifecycleScope.launch {
            val raw = apiClient.getSharedSettings()
            if (raw != null) {
                runCatching {
                    val backendTheme = JSONObject(raw).optString("theme", "")
                    if (backendTheme == "dark" || backendTheme == "light" || backendTheme == "system") {
                        settings.setTheme(backendTheme)
                        theme = backendTheme
                    }
                }
            }
        }

        // Reflect the backend voice pipeline (listening/thinking/speaking/…)
        // onto the presence orb. The callback runs on OkHttp's thread; snapshot
        // state writes are thread-safe and schedule recomposition on the main
        // thread.
        webSocketClient.addListener(object : VoiceWebSocketClient.VoiceWebSocketListener {
            override fun onVoiceState(state: String) {
                voiceState = state
            }
            override fun onConnected() {
                isConnected = true
            }
            override fun onDisconnected(reason: String) {
                isConnected = false
            }
        })

        setContent {
            // Support 'system' theme (follows OS dark mode) — matches web dark/light/system parity (G7).
            val isSystemDark = androidx.compose.foundation.isSystemInDarkTheme()
            val useDark = when (theme.lowercase()) {
                "light" -> false
                "system" -> isSystemDark
                else -> true // dark default
            }
            ArenaVoiceTheme(darkTheme = useDark, dynamicColor = false) {
                Surface(
                    modifier = Modifier.fillMaxSize(),
                    color = MaterialTheme.colorScheme.background,
                ) {
                    AppScaffold(
                        presenceStatus = resolvePresenceStatus(),
                        statusMessage = resolveStatusMessage(),
                        isListening = isListening,
                        serverUrl = serverUrl,
                        apiKey = apiKey,
                        onToggleTalk = { toggleTalk() },
                        onQuickAction = { action -> handleQuickAction(action) },
                        onLandingSubmit = { text -> handleLandingSubmit(text) },
                        onSaveServerUrl = { url -> saveServerUrl(url) },
                        onSaveApiKey = { key -> saveApiKey(key) },
                        onSaveTheme = { t -> saveTheme(t) },
                    )
                }
            }
        }

        checkPermissions()
    }

    /** Map the backend voice_state + local flags onto the orb's presence states. */
    private fun resolvePresenceStatus(): PresenceStatus {
        when (voiceState) {
            "listening", "recording" -> return PresenceStatus.LISTENING
            "processing", "thinking" -> return PresenceStatus.THINKING
            "speaking" -> return PresenceStatus.SPEAKING
        }
        return when {
            isListening -> PresenceStatus.LISTENING
            !isConnected -> PresenceStatus.OFFLINE
            else -> PresenceStatus.IDLE
        }
    }

    private fun resolveStatusMessage(): String {
        when (voiceState) {
            "listening" -> return "Listening…"
            "recording" -> return "Listening…"
            "processing" -> return "Thinking…"
            "thinking" -> return "Thinking…"
            "speaking" -> return "Speaking…"
        }
        return when {
            isListening -> "Listening…"
            !isConnected -> "Offline — connect to your PC."
            else -> "What are we working on today?"
        }
    }

    private fun saveServerUrl(url: String) {
        lifecycleScope.launch {
            settings.setServerUrl(url)
            serverUrl = url
            disconnectFromServer()
            connectToServer()
        }
    }

    private fun saveApiKey(key: String) {
        lifecycleScope.launch {
            settings.setApiKey(key)
            apiKey = key
        }
    }

    private fun saveTheme(t: String) {
        lifecycleScope.launch {
            val raw = t.trim().lowercase()
            val normalized = when (raw) {
                "light" -> "light"
                "system" -> "system"
                else -> "dark"
            }
            settings.setTheme(normalized)
            theme = normalized
        }
    }

    private fun toggleTalk() {
        if (isListening) {
            isListening = false
            stopWakeWordService()
        } else {
            isListening = true
            startWakeWordService()
        }
    }

    /**
     * Request every dangerous permission the app can use, grouped by API level.
     * Normal permissions are auto-granted at install and NOT requested here.
     */
    private fun checkPermissions() {
        val permissions = mutableListOf<String>()

        permissions.add(Manifest.permission.RECORD_AUDIO)
        permissions.add(Manifest.permission.CAMERA)
        permissions.add(Manifest.permission.ACCESS_FINE_LOCATION)
        permissions.add(Manifest.permission.ACCESS_COARSE_LOCATION)
        permissions.add(Manifest.permission.READ_CONTACTS)
        permissions.add(Manifest.permission.WRITE_CONTACTS)
        permissions.add(Manifest.permission.READ_PHONE_STATE)
        permissions.add(Manifest.permission.READ_SMS)
        permissions.add(Manifest.permission.SEND_SMS)
        permissions.add(Manifest.permission.RECEIVE_SMS)
        permissions.add(Manifest.permission.BODY_SENSORS)

        if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.Q) {
            permissions.add(Manifest.permission.ACTIVITY_RECOGNITION)
            permissions.add(Manifest.permission.ACCESS_MEDIA_LOCATION)
        }
        if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.S) {
            permissions.add(Manifest.permission.BLUETOOTH_CONNECT)
            permissions.add(Manifest.permission.BLUETOOTH_SCAN)
            permissions.add(Manifest.permission.BLUETOOTH_ADVERTISE)
        }
        if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.TIRAMISU) {
            permissions.add(Manifest.permission.READ_MEDIA_IMAGES)
            permissions.add(Manifest.permission.READ_MEDIA_VIDEO)
            permissions.add(Manifest.permission.READ_MEDIA_AUDIO)
            permissions.add(Manifest.permission.POST_NOTIFICATIONS)
            permissions.add(Manifest.permission.NEARBY_WIFI_DEVICES)
        } else {
            permissions.add(Manifest.permission.READ_EXTERNAL_STORAGE)
            permissions.add(Manifest.permission.WRITE_EXTERNAL_STORAGE)
        }

        val notGranted = permissions.filter {
            ContextCompat.checkSelfPermission(this, it) != PackageManager.PERMISSION_GRANTED
        }

        if (notGranted.isEmpty()) {
            startServices()
        } else {
            requestPermissionLauncher.launch(notGranted.toTypedArray())
        }
    }

    private fun startServices() {
        connectToServer()
        startWakeWordService()
    }

    private fun startWakeWordService() {
        // A microphone foreground service must not start until RECORD_AUDIO is
        // granted, and on newer Android it can throw SecurityException /
        // ForegroundServiceStartNotAllowedException — log instead of crashing.
        val micGranted = ContextCompat.checkSelfPermission(
            this, Manifest.permission.RECORD_AUDIO
        ) == PackageManager.PERMISSION_GRANTED
        if (!micGranted) {
            Log.w(TAG, "Skipping wake-word service: RECORD_AUDIO not granted")
            return
        }
        try {
            val intent = Intent(this, WakeWordService::class.java).apply {
                action = WakeWordService.ACTION_START
            }
            if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.O) {
                startForegroundService(intent)
            } else {
                startService(intent)
            }
            Log.i(TAG, "Wake word service started")
        } catch (e: Exception) {
            Log.e(TAG, "Could not start wake-word service: ${e.message}")
        }
    }

    private fun stopWakeWordService() {
        val intent = Intent(this, WakeWordService::class.java).apply {
            action = WakeWordService.ACTION_STOP
        }
        startService(intent)
        Log.i(TAG, "Wake word service stopped")
    }

    private fun connectToServer() {
        lifecycleScope.launch {
            webSocketClient.connectToSavedServer()
            isConnected = webSocketClient.isConnected()
        }
    }

    /** Landing composer: send from the home screen into the shared conversation. */
    private fun handleLandingSubmit(text: String) {
        val content = text.trim()
        if (content.isNotEmpty()) {
            webSocketClient.sendUserMessage(webSocketClient.conversationId, content)
        }
    }

    private fun handleQuickAction(action: String) {
        if (action == "talk") {
            // The chip is a voice entry point, not an empty prompt.
            toggleTalk()
            return
        }
        val prompt = when (action) {
            "continue_project" -> "What were we working on? Continue the project."
            "whats_new" -> "What's new in my system?"
            "research" -> "Research the latest on my current project."
            else -> null
        }
        if (prompt != null) {
            webSocketClient.sendUserMessage(webSocketClient.conversationId, prompt)
        }
    }

    private fun disconnectFromServer() {
        webSocketClient.disconnect()
    }

    override fun onDestroy() {
        stopWakeWordService()
        disconnectFromServer()
        super.onDestroy()
    }

    companion object {
        private const val TAG = "MainActivity"
    }
}
