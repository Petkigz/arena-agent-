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
import kotlinx.coroutines.launch
import com.arena.voice.service.WakeWordService
import com.arena.voice.ui.ArenaVoiceTheme
import com.arena.voice.ui.screens.MainScreen
import com.arena.voice.ui.screens.PresenceStatus
import com.arena.voice.util.SettingsRepository
import com.arena.voice.websocket.VoiceWebSocketClient
import dagger.hilt.android.AndroidEntryPoint
import javax.inject.Inject

@AndroidEntryPoint
class MainActivity : ComponentActivity() {
    
    @Inject
    lateinit var webSocketClient: VoiceWebSocketClient

    @Inject
    lateinit var settings: SettingsRepository

    private var serverUrl by mutableStateOf(SettingsRepository.DEFAULT_SERVER_URL)
    private var isConnected by mutableStateOf(false)
    private var isListening by mutableStateOf(false)
    
    private val requestPermissionLauncher = registerForActivityResult(
        ActivityResultContracts.RequestMultiplePermissions()
    ) { permissions ->
        val denied = permissions.filterValues { !it }.keys
        if (denied.isNotEmpty()) {
            Log.w(TAG, "Some permissions denied: $denied")
        }
        // Start services as long as the mic permission is granted — the other
        // permissions (camera, location, SMS, …) are optional sensors and should
        // not block the core voice assistant.
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

        // Load the persisted server URL so the UI can show/edit it.
        lifecycleScope.launch {
            settings.serverUrl.collect { url ->
                serverUrl = url
            }
        }

        setContent {
            ArenaVoiceTheme {
                Surface(
                    modifier = Modifier.fillMaxSize(),
                    color = MaterialTheme.colorScheme.background
                ) {
                    MainScreen(
                        onStartListening = {
                            isListening = true
                            startWakeWordService()
                        },
                        onStopListening = {
                            isListening = false
                            stopWakeWordService()
                        },
                        onConnect = {
                            isConnected = true
                            connectToServer()
                        },
                        onDisconnect = {
                            isConnected = false
                            disconnectFromServer()
                        },
                        serverUrl = serverUrl,
                        onSaveServerUrl = { url -> saveServerUrl(url) },
                        presenceStatus = when {
                            isListening -> PresenceStatus.LISTENING
                            !isConnected -> PresenceStatus.OFFLINE
                            else -> PresenceStatus.IDLE
                        },
                        statusMessage = when {
                            isListening -> "Listening…"
                            !isConnected -> "Offline — connect to your PC."
                            else -> "I'm here."
                        },
                        onQuickAction = { action -> handleQuickAction(action) },
                    )
                }
            }
        }
        
        checkPermissions()
    }

    private fun saveServerUrl(url: String) {
        lifecycleScope.launch {
            settings.setServerUrl(url)
            serverUrl = url
            // Reconnect using the newly-saved URL.
            disconnectFromServer()
            connectToServer()
        }
    }
    
    /**
     * Request every dangerous permission the app can use, grouped by API level.
     * Normal permissions (INTERNET, ACCESS_NETWORK_STATE, WAKE_LOCK, etc.) are
     * auto-granted at install and are NOT requested here.
     */
    private fun checkPermissions() {
        val permissions = mutableListOf<String>()

        // Always-required
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

        // Activity recognition (API 29+)
        if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.Q) {
            permissions.add(Manifest.permission.ACTIVITY_RECOGNITION)
        }

        // Photo location metadata (API 29+)
        if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.Q) {
            permissions.add(Manifest.permission.ACCESS_MEDIA_LOCATION)
        }

        // Bluetooth runtime permissions (API 31+)
        if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.S) {
            permissions.add(Manifest.permission.BLUETOOTH_CONNECT)
            permissions.add(Manifest.permission.BLUETOOTH_SCAN)
            permissions.add(Manifest.permission.BLUETOOTH_ADVERTISE)
        }

        // Scoped storage: READ_MEDIA_* on 13+, legacy external storage on 12 and below
        if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.TIRAMISU) {
            permissions.add(Manifest.permission.READ_MEDIA_IMAGES)
            permissions.add(Manifest.permission.READ_MEDIA_VIDEO)
            permissions.add(Manifest.permission.READ_MEDIA_AUDIO)
            permissions.add(Manifest.permission.POST_NOTIFICATIONS)
        } else {
            permissions.add(Manifest.permission.READ_EXTERNAL_STORAGE)
            permissions.add(Manifest.permission.WRITE_EXTERNAL_STORAGE)
        }

        // Nearby Wi-Fi devices (API 33+)
        if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.TIRAMISU) {
            permissions.add(Manifest.permission.NEARBY_WIFI_DEVICES)
        }

        // Only request what's not already granted.
        val notGranted = permissions.filter {
            ContextCompat.checkSelfPermission(this, it) != PackageManager.PERMISSION_GRANTED
        }

        if (notGranted.isEmpty()) {
            Log.i(TAG, "All permissions already granted")
            startServices()
        } else {
            Log.i(TAG, "Requesting ${notGranted.size} permission(s)...")
            requestPermissionLauncher.launch(notGranted.toTypedArray())
        }
    }
    
    private fun startServices() {
        connectToServer()
        startWakeWordService()
    }
    
    private fun startWakeWordService() {
        val intent = Intent(this, WakeWordService::class.java).apply {
            action = WakeWordService.ACTION_START
        }
        
        if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.O) {
            startForegroundService(intent)
        } else {
            startService(intent)
        }
        
        Log.i(TAG, "Wake word service started")
    }
    
    private fun stopWakeWordService() {
        val intent = Intent(this, WakeWordService::class.java).apply {
            action = WakeWordService.ACTION_STOP
        }
        startService(intent)
        
        Log.i(TAG, "Wake word service stopped")
    }
    
    private fun connectToServer() {
        // Read the persisted server URL (DataStore) and connect.
        lifecycleScope.launch {
            webSocketClient.connectToSavedServer()
            isConnected = webSocketClient.isConnected()
        }
    }

    /** Quick actions route a chat prompt to the backend (like the web/desktop). */
    private fun handleQuickAction(action: String) {
        val prompt = when (action) {
            "continue_project" -> "What were we working on? Continue the project."
            "whats_new" -> "What's new in my system?"
            "research" -> "Research the latest on my current project."
            "talk" -> null
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
