package com.arena.voice.service

import android.app.Notification
import android.app.Service
import android.content.Intent
import android.media.AudioRecord
import android.media.MediaRecorder
import android.os.Handler
import android.os.IBinder
import android.os.Looper
import android.util.Log
import androidx.core.app.NotificationCompat
import com.arena.voice.ArenaVoiceApp
import com.arena.voice.util.AudioConfig
import com.arena.voice.websocket.VoiceWebSocketClient
import dagger.hilt.android.AndroidEntryPoint
import kotlinx.coroutines.*
import javax.inject.Inject

/**
 * Records the phone microphone and streams raw PCM (16 kHz, mono, int16) to the
 * backend over the WebSocket. The backend handles utterance detection → STT →
 * cognitive runtime → TTS, and broadcasts `voice_state` transitions.
 *
 * This service stops itself when the backend reports the reply is complete
 * (`voice_state == "idle"`), then re-arms the WakeWordService so Beanie resumes
 * listening for the next utterance.
 */
@AndroidEntryPoint
class VoiceRecordingService : Service() {

    @Inject
    lateinit var webSocketClient: VoiceWebSocketClient

    private var audioRecord: AudioRecord? = null
    private var isRecording = false
    private var recordingJob: Job? = null

    private val mainHandler = Handler(Looper.getMainLooper())

    // Tracks the backend voice_state so we know when the reply has finished.
    private var sawActivity = false
    private val voiceStateListener = object : VoiceWebSocketClient.VoiceWebSocketListener {
        override fun onVoiceState(state: String) {
            when (state) {
                "recording", "listening", "processing", "thinking", "speaking" -> sawActivity = true
                "idle", "stopped" -> if (sawActivity) {
                    Log.i(TAG, "Reply complete (voice_state=$state) — stopping recording")
                    mainHandler.post { stopRecording() }
                }
            }
        }
    }

    override fun onBind(intent: Intent?): IBinder? = null

    override fun onCreate() {
        super.onCreate()
        Log.d(TAG, "VoiceRecordingService created")
    }

    override fun onStartCommand(intent: Intent?, flags: Int, startId: Int): Int {
        when (intent?.action) {
            ACTION_START -> startRecording()
            ACTION_STOP -> stopRecording()
        }
        return START_NOT_STICKY
    }

    private fun startRecording() {
        if (isRecording) return

        try {
            val notification = createNotification()
            startForeground(NOTIFICATION_ID, notification)

            val bufferSize = AudioRecord.getMinBufferSize(
                AudioConfig.SAMPLE_RATE,
                AudioConfig.CHANNEL_CONFIG,
                AudioConfig.AUDIO_FORMAT
            )

            audioRecord = AudioRecord(
                MediaRecorder.AudioSource.MIC,
                AudioConfig.SAMPLE_RATE,
                AudioConfig.CHANNEL_CONFIG,
                AudioConfig.AUDIO_FORMAT,
                bufferSize * 2
            )

            if (audioRecord?.state != AudioRecord.STATE_INITIALIZED) {
                Log.e(TAG, "Failed to initialize AudioRecord")
                stopSelf()
                return
            }

            audioRecord?.startRecording()
            isRecording = true
            sawActivity = false
            webSocketClient.addListener(voiceStateListener)

            Log.i(TAG, "Voice recording started")

            recordingJob = CoroutineScope(Dispatchers.IO).launch {
                recordAndStream()
            }

        } catch (e: Exception) {
            Log.e(TAG, "Failed to start recording: ${e.message}")
            stopSelf()
        }
    }

    private suspend fun CoroutineScope.recordAndStream() {
        val buffer = ShortArray(AudioConfig.STREAMING_CHUNK_SIZE)

        // Safety valve: never hold the mic forever if the backend never sends
        // "idle" (e.g. STT unavailable). Stop after MAX_RECORDING_MS.
        val stopTimeout = launch {
            delay(MAX_RECORDING_MS)
            if (isRecording) {
                Log.w(TAG, "Recording timeout reached — stopping")
                withContext(Dispatchers.Main) { stopRecording() }
            }
        }

        try {
            while (isRecording) {
                val read = audioRecord?.read(buffer, 0, buffer.size) ?: 0

                if (read > 0) {
                    val bytes = ByteArray(read * 2)
                    for (i in 0 until read) {
                        bytes[i * 2] = (buffer[i].toInt() and 0xFF).toByte()
                        bytes[i * 2 + 1] = (buffer[i].toInt() shr 8).toByte()
                    }
                    webSocketClient.sendAudio(bytes)
                }

                delay(10)
            }
        } finally {
            stopTimeout.cancel()
        }
    }

    private fun stopRecording() {
        if (!isRecording) return

        isRecording = false
        recordingJob?.cancel()
        recordingJob = null
        webSocketClient.removeListener(voiceStateListener)

        try {
            audioRecord?.stop()
            audioRecord?.release()
            audioRecord = null

            stopForeground(STOP_FOREGROUND_REMOVE)
            Log.i(TAG, "Voice recording stopped")

        } catch (e: Exception) {
            Log.e(TAG, "Error stopping recording: ${e.message}")
        }

        // Hand the mic back to the wake-word service so Beanie keeps listening.
        rearmWakeWordService()

        stopSelf()
    }

    private fun rearmWakeWordService() {
        val intent = Intent(this, WakeWordService::class.java).apply {
            action = WakeWordService.ACTION_REARM
        }
        try {
            startService(intent)
        } catch (e: Exception) {
            // ForegroundServiceStartNotAllowedException when the app is
            // backgrounded on newer Android — log, don't crash, but show user feedback (G7).
            Log.w(TAG, "Could not re-arm wake-word service: ${e.message}")
            // Show a low-priority notification so owner knows listening paused
            try {
                val notification = NotificationCompat.Builder(this, ArenaVoiceApp.WAKE_WORD_CHANNEL_ID)
                    .setContentTitle("Beanie paused")
                    .setContentText("Tap to resume listening — background start restricted by Android")
                    .setSmallIcon(android.R.drawable.ic_btn_speak_now)
                    .setPriority(NotificationCompat.PRIORITY_LOW)
                    .setAutoCancel(true)
                    .build()
                val nm = getSystemService(android.content.Context.NOTIFICATION_SERVICE) as android.app.NotificationManager
                nm.notify(1003, notification)
            } catch (_: Exception) {
            }
        }
    }

    private fun createNotification(): Notification {
        return NotificationCompat.Builder(this, ArenaVoiceApp.RECORDING_CHANNEL_ID)
            .setContentTitle("Arena Voice")
            .setContentText("Recording your voice…")
            .setSmallIcon(android.R.drawable.ic_btn_speak_now)
            .setPriority(NotificationCompat.PRIORITY_LOW)
            .setOngoing(true)
            .build()
    }

    override fun onDestroy() {
        stopRecording()
        super.onDestroy()
        Log.d(TAG, "VoiceRecordingService destroyed")
    }

    companion object {
        private const val TAG = "VoiceRecordingService"
        private const val NOTIFICATION_ID = 1002

        // Hard cap on a single recording session (60s) as a safety net.
        private const val MAX_RECORDING_MS = 60_000L

        const val ACTION_START = "com.arena.voice.action.START_RECORDING"
        const val ACTION_STOP = "com.arena.voice.action.STOP_RECORDING"
    }
}
