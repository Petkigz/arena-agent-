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
import androidx.compose.ui.Modifier
import androidx.core.content.ContextCompat
import com.arena.voice.service.WakeWordService
import com.arena.voice.ui.ArenaVoiceTheme
import com.arena.voice.ui.screens.MainScreen
import com.arena.voice.websocket.VoiceWebSocketClient
import dagger.hilt.android.AndroidEntryPoint
import javax.inject.Inject

@AndroidEntryPoint
class MainActivity : ComponentActivity() {
    
    @Inject
    lateinit var webSocketClient: VoiceWebSocketClient
    
    private val requestPermissionLauncher = registerForActivityResult(
        ActivityResultContracts.RequestMultiplePermissions()
    ) { permissions ->
        val allGranted = permissions.all { it.value }
        if (allGranted) {
            Log.i(TAG, "All permissions granted")
            startServices()
        } else {
            Log.e(TAG, "Permissions denied")
        }
    }
    
    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        
        setContent {
            ArenaVoiceTheme {
                Surface(
                    modifier = Modifier.fillMaxSize(),
                    color = MaterialTheme.colorScheme.background
                ) {
                    MainScreen(
                        onStartListening = { startWakeWordService() },
                        onStopListening = { stopWakeWordService() },
                        onConnect = { connectToServer() },
                        onDisconnect = { disconnectFromServer() }
                    )
                }
            }
        }
        
        checkPermissions()
    }
    
    private fun checkPermissions() {
        val permissions = mutableListOf(
            Manifest.permission.RECORD_AUDIO,
            Manifest.permission.INTERNET
        )
        
        if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.TIRAMISU) {
            permissions.add(Manifest.permission.POST_NOTIFICATIONS)
        }
        
        val allGranted = permissions.all {
            ContextCompat.checkSelfPermission(this, it) == PackageManager.PERMISSION_GRANTED
        }
        
        if (allGranted) {
            Log.i(TAG, "All permissions already granted")
            startServices()
        } else {
            requestPermissionLauncher.launch(permissions.toTypedArray())
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
        webSocketClient.connect()
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
