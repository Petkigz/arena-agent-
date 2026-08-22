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
 * Local wake-word service for Beanie.
 *
 * The service boundary is ready for a native offline wake-word engine. The
 * current fallback is intentionally marked as development-only; it must not
 * be presented as real wake-word detection in production.
 */
@AndroidEntryPoint
class WakeWordService : Service() {
    @Inject lateinit var webSocketClient: VoiceWebSocketClient

    private var isListening = false
    private var simulationThread: Thread? = null

    override fun onBind(intent: Intent?): IBinder? = null

    override fun onCreate() {
        super.onCreate()
        Log.d(TAG, "Beanie WakeWordService created")
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
            startForeground(NOTIFICATION_ID, createNotification())
            isListening = true
            if (tryStartPorcupine()) {
                Log.i(TAG, "Native wake-word engine started")
            } else {
                Log.w(TAG, "No configured native wake-word engine; using development fallback")
                startDevelopmentFallback()
            }
        } catch (e: Exception) {
            Log.e(TAG, "Failed to start wake-word detection: ${e.message}")
            stopSelf()
        }
    }

    private fun tryStartPorcupine(): Boolean {
        return try {
            Class.forName("ai.picovoice.porcupine.PorcupineManager")
            val accessKeyResId = resources.getIdentifier("pv_access_key", "string", packageName)
            if (accessKeyResId == 0) return false
            val accessKey = getString(accessKeyResId)
            if (accessKey.isBlank() || accessKey == "YOUR_ACCESS_KEY_HERE") return false

            // The actual Porcupine manager should be initialized here once the
            // selected offline Beanie keyword model is committed to the app.
            Log.i(TAG, "Wake-word SDK detected but keyword runtime is not configured")
            false
        } catch (_: ClassNotFoundException) {
            false
        } catch (e: Exception) {
            Log.w(TAG, "Wake-word initialization failed: ${e.message}")
            false
        }
    }

    private fun startDevelopmentFallback() {
        simulationThread = Thread {
            Log.w(TAG, "Development wake-word fallback active; not a production detector")
            while (isListening) {
                try {
                    Thread.sleep(30000)
                    if (isListening) onWakeWordDetected()
                } catch (_: InterruptedException) {
                    break
                }
            }
        }.also { it.start() }
    }

    private fun stopListening() {
        if (!isListening) return
        isListening = false
        simulationThread?.interrupt()
        simulationThread = null
        stopForeground(STOP_FOREGROUND_REMOVE)
        stopSelf()
    }

    private fun onWakeWordDetected() {
        Log.i(TAG, "Beanie wake word detected")
        webSocketClient.onWakeWordDetected()
        val recordingIntent = Intent(this, VoiceRecordingService::class.java).apply {
            action = VoiceRecordingService.ACTION_START
        }
        startService(recordingIntent)
    }

    private fun createNotification(): Notification =
        NotificationCompat.Builder(this, ArenaVoiceApp.WAKE_WORD_CHANNEL_ID)
            .setContentTitle("Beanie")
            .setContentText("Listening for Beanie's wake word")
            .setSmallIcon(android.R.drawable.ic_btn_speak_now)
            .setPriority(NotificationCompat.PRIORITY_LOW)
            .setOngoing(true)
            .build()

    override fun onDestroy() {
        stopListening()
        super.onDestroy()
        Log.d(TAG, "Beanie WakeWordService destroyed")
    }

    companion object {
        private const val TAG = "WakeWordService"
        private const val NOTIFICATION_ID = 1001
        const val ACTION_START = "com.arena.voice.action.START_WAKE_WORD"
        const val ACTION_STOP = "com.arena.voice.action.STOP_WAKE_WORD"
    }
}
