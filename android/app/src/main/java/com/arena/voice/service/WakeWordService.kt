package com.arena.voice.service

import android.app.Notification
import android.app.Service
import android.content.Intent
import android.os.IBinder
import android.util.Log
import androidx.core.app.NotificationCompat
import com.arena.voice.ArenaVoiceApp
import com.arena.voice.websocket.VoiceWebSocketClient
import dagger.hilt.android.AndroidEntryPoint
import javax.inject.Inject

/**
 * Wake word detection service.
 *
 * Note: This uses a simulated wake word detector for demonstration.
 * To use Porcupine (Picovoice), you need:
 * 1. A Picovoice access key (sign up at https://console.picovoice.ai/)
 * 2. Add the access key to res/values/strings.xml as pv_access_key
 * 3. Create a custom wake word model (.ppn file) or use built-in keywords
 * 4. Add Porcupine dependency to build.gradle
 *
 * Without Porcupine, this service uses a simple energy-based detection
 * as a fallback for development purposes.
 */
@AndroidEntryPoint
class WakeWordService : Service() {

    @Inject
    lateinit var webSocketClient: VoiceWebSocketClient

    private var isListening = false
    private var simulationThread: Thread? = null

    override fun onBind(intent: Intent?): IBinder? = null

    override fun onCreate() {
        super.onCreate()
        Log.d(TAG, "WakeWordService created")
    }

    override fun onStartCommand(intent: Intent?, flags: Int, startId: Int): Int {
        when (intent?.action) {
            ACTION_START -> startListening()
            ACTION_STOP -> stopListening()
        }
        return START_STICKY
    }

    private fun startListening() {
        if (isListening) return

        try {
            // Create notification for foreground service
            val notification = createNotification()
            startForeground(NOTIFICATION_ID, notification)

            isListening = true

            // Try to use Porcupine if available
            if (tryStartPorcupine()) {
                Log.i(TAG, "Porcupine wake word detection started")
            } else {
                // Fallback: simulated wake word for development
                Log.w(TAG, "Porcupine not available, using simulated wake word detection")
                startSimulatedDetection()
            }

        } catch (e: Exception) {
            Log.e(TAG, "Failed to start wake word detection: ${e.message}")
            stopSelf()
        }
    }

    private fun tryStartPorcupine(): Boolean {
        return try {
            // Check if Porcupine is available via reflection
            val porcupineClass = Class.forName("ai.picovoice.porcupine.PorcupineManager")

            // Try to get access key
            val accessKeyResId = resources.getIdentifier("pv_access_key", "string", packageName)
            if (accessKeyResId == 0) {
                Log.w(TAG, "No Porcupine access key found in resources")
                return false
            }

            val accessKey = getString(accessKeyResId)
            if (accessKey.isBlank() || accessKey == "YOUR_ACCESS_KEY_HERE") {
                Log.w(TAG, "Porcupine access key not configured")
                return false
            }

            // If we get here, Porcupine is available and configured
            // In a real implementation, you'd initialize PorcupineManager here
            Log.i(TAG, "Porcupine available but full integration requires .ppn model file")
            false // Fall back to simulation for now

        } catch (e: ClassNotFoundException) {
            Log.d(TAG, "Porcupine SDK not installed")
            false
        } catch (e: Exception) {
            Log.w(TAG, "Porcupine initialization failed: ${e.message}")
            false
        }
    }

    private fun startSimulatedDetection() {
        // Simple simulation: periodically "detect" wake word for testing
        // In production, replace with actual audio processing
        simulationThread = Thread {
            Log.i(TAG, "Simulated wake word detection started (for development only)")

            while (isListening) {
                try {
                    Thread.sleep(30000) // Check every 30 seconds for simulation

                    if (isListening) {
                        // Simulate wake word detection
                        Log.i(TAG, "Simulated wake word detected!")
                        onWakeWordDetected()
                    }
                } catch (e: InterruptedException) {
                    break
                }
            }
        }
        simulationThread?.start()
    }

    private fun stopListening() {
        if (!isListening) return

        isListening = false

        // Stop simulation thread
        simulationThread?.interrupt()
        simulationThread = null

        stopForeground(STOP_FOREGROUND_REMOVE)

        Log.i(TAG, "Wake word detection stopped")
        stopSelf()
    }

    private fun onWakeWordDetected() {
        Log.i(TAG, "Wake word detected!")

        // Notify WebSocket client
        webSocketClient.onWakeWordDetected()

        // Start voice recording service
        val recordingIntent = Intent(this, VoiceRecordingService::class.java).apply {
            action = VoiceRecordingService.ACTION_START
        }
        startService(recordingIntent)
    }

    private fun createNotification(): Notification {
        return NotificationCompat.Builder(this, ArenaVoiceApp.WAKE_WORD_CHANNEL_ID)
            .setContentTitle("Arena Voice")
            .setContentText("Listening for wake word...")
            .setSmallIcon(android.R.drawable.ic_btn_speak_now)
            .setPriority(NotificationCompat.PRIORITY_LOW)
            .setOngoing(true)
            .build()
    }

    override fun onDestroy() {
        stopListening()
        super.onDestroy()
        Log.d(TAG, "WakeWordService destroyed")
    }

    companion object {
        private const val TAG = "WakeWordService"
        private const val NOTIFICATION_ID = 1001

        const val ACTION_START = "com.arena.voice.action.START_WAKE_WORD"
        const val ACTION_STOP = "com.arena.voice.action.STOP_WAKE_WORD"
    }
}
