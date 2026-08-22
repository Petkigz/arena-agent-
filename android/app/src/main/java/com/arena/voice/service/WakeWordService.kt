package com.arena.voice.service

import android.app.Notification
import android.app.Service
import android.content.Intent
import android.media.AudioRecord
import android.media.MediaRecorder
import android.os.Build
import android.os.Bundle
import android.os.Handler
import android.os.IBinder
import android.os.Looper
import android.speech.RecognitionListener
import android.speech.RecognizerIntent
import android.speech.SpeechRecognizer
import android.util.Log
import androidx.core.app.NotificationCompat
import com.arena.voice.ArenaVoiceApp
import com.arena.voice.util.AudioConfig
import com.arena.voice.websocket.VoiceWebSocketClient
import dagger.hilt.android.AndroidEntryPoint
import kotlin.math.sqrt
import javax.inject.Inject

/**
 * Wake-word / voice-activity detection service.
 *
 * Two detection paths, tried in order:
 *
 * 1. **Keyword spotting** (preferred) — Android's built-in [SpeechRecognizer]
 *    transcribes short audio bursts and this service matches them against the
 *    wake phrase ("hi android", plus aliases). This actually recognizes the
 *    WORDS, so it wakes only when you say the phrase — not on any loud noise.
 *
 * 2. **Energy VAD** (fallback) — if no speech recognizer is available (e.g. no
 *    Google recognition service, or offline), it falls back to loudness-triggered
 *    detection (AudioRecord + RMS threshold).
 *
 * Honest limitations:
 *  - SpeechRecognizer recognition quality/availability depends on the device's
 *    speech service and may require network on some devices (on-device
 *    recognition is increasingly available but not guaranteed).
 *  - True always-on, fully-offline keyword spotting (Picovoice Porcupine) still
 *    requires an access key + a .ppn model + a 16 KB-page-size-aligned SDK
 *    (the earlier build failed on that — see build.gradle.kts note).
 *
 * Flow: detect wake → release the mic → start VoiceRecordingService (streams PCM
 * to the backend) → VoiceRecordingService re-arms this service when the backend
 * reports the reply finished (voice_state "idle").
 */
@AndroidEntryPoint
class WakeWordService : Service() {

    @Inject
    lateinit var webSocketClient: VoiceWebSocketClient

    private var isListening = false
    private var audioRecord: AudioRecord? = null
    private var detectionThread: Thread? = null
    private var speechRecognizer: SpeechRecognizer? = null
    private var restartRunnable: Runnable? = null
    private val mainHandler = Handler(Looper.getMainLooper())

    override fun onBind(intent: Intent?): IBinder? = null

    override fun onCreate() {
        super.onCreate()
        Log.d(TAG, "WakeWordService created")
    }

    override fun onStartCommand(intent: Intent?, flags: Int, startId: Int): Int {
        when (intent?.action) {
            ACTION_START -> startListening()
            ACTION_STOP -> stopListening()
            ACTION_REARM -> rearm()
        }
        return START_STICKY
    }

    private fun startListening() {
        if (isListening) return
        try {
            val notification = createNotification()
            startForeground(NOTIFICATION_ID, notification)
            isListening = true

            if (SpeechRecognizer.isRecognitionAvailable(this)) {
                Log.i(TAG, "Starting keyword spotting (SpeechRecognizer) for wake phrase")
                startKeywordDetection()
            } else {
                Log.w(TAG, "SpeechRecognizer unavailable — falling back to energy VAD")
                startEnergyDetection()
            }
        } catch (e: Exception) {
            Log.e(TAG, "Failed to start wake-word detection: ${e.message}")
            stopSelf()
        }
    }

    /** (Re)start detection after a recording session ends. */
    private fun rearm() {
        if (!isListening) {
            startListening()
            return
        }
        // Restart keyword spotting; if that's not the active path, restart VAD.
        if (speechRecognizer != null) {
            scheduleRestart()
        } else if (detectionThread == null || !detectionThread!!.isAlive) {
            startEnergyDetection()
        }
    }

    // ── Keyword spotting (SpeechRecognizer) ─────────────────────────────────

    private fun startKeywordDetection() {
        val recognizer = SpeechRecognizer.createSpeechRecognizer(this)
        speechRecognizer = recognizer
        recognizer.setRecognitionListener(object : RecognitionListener {
            override fun onReadyForSpeech(params: Bundle?) {}
            override fun onBeginningOfSpeech() {}
            override fun onRmsChanged(rmsdB: Float) {}
            override fun onBufferReceived(buffer: ByteArray?) {}
            override fun onEndOfSpeech() {}

            override fun onError(error: Int) {
                if (isListening) {
                    Log.d(TAG, "Recognizer error $error — restarting")
                    scheduleRestart()
                }
            }

            override fun onResults(results: Bundle?) {
                if (handleResults(results)) return
                if (isListening) scheduleRestart()
            }

            override fun onPartialResults(partialResults: Bundle?) {
                handleResults(partialResults)
            }

            override fun onEvent(eventType: Int, params: Bundle?) {}
        })
        startRecognizer()
    }

    private fun startRecognizer() {
        if (!isListening || speechRecognizer == null) return
        val intent = Intent(RecognizerIntent.ACTION_RECOGNIZE_SPEECH).apply {
            putExtra(RecognizerIntent.EXTRA_LANGUAGE_MODEL, RecognizerIntent.LANGUAGE_MODEL_FREE_FORM)
            putExtra(RecognizerIntent.EXTRA_PARTIAL_RESULTS, true)
            putExtra(RecognizerIntent.EXTRA_MAX_RESULTS, 3)
            putExtra(RecognizerIntent.EXTRA_CALLING_PACKAGE, packageName)
        }
        try {
            speechRecognizer?.startListening(intent)
        } catch (e: Exception) {
            Log.w(TAG, "startListening failed: ${e.message}")
            scheduleRestart()
        }
    }

    /** Returns true if a recognized phrase matched the wake word (caller stops). */
    private fun handleResults(bundle: Bundle?): Boolean {
        val matches = bundle?.getStringArrayList(SpeechRecognizer.RESULTS_RECOGNITION) ?: return false
        for (match in matches) {
            if (isWakePhrase(match)) {
                Log.i(TAG, "Wake phrase detected: \"$match\"")
                onWakeWordDetected()
                return true
            }
        }
        return false
    }

    private fun scheduleRestart() {
        if (!isListening) return
        restartRunnable?.let { mainHandler.removeCallbacks(it) }
        val runnable = Runnable { if (isListening) startRecognizer() }
        restartRunnable = runnable
        mainHandler.postDelayed(runnable, RESTART_DELAY_MS)
    }

    // ── Energy VAD (offline fallback) ───────────────────────────────────────

    /**
     * Captures mic PCM and wakes on sustained loudness (energy VAD). Used only
     * when no speech recognizer is available.
     */
    private fun startEnergyDetection() {
        detectionThread = Thread {
            var record: AudioRecord? = null
            try {
                val minBuf = AudioRecord.getMinBufferSize(
                    AudioConfig.SAMPLE_RATE,
                    AudioConfig.CHANNEL_CONFIG,
                    AudioConfig.AUDIO_FORMAT
                )
                if (minBuf == AudioRecord.ERROR || minBuf == AudioRecord.ERROR_BAD_VALUE) {
                    Log.e(TAG, "AudioRecord.getMinBufferSize failed")
                    return@Thread
                }

                record = AudioRecord(
                    MediaRecorder.AudioSource.MIC,
                    AudioConfig.SAMPLE_RATE,
                    AudioConfig.CHANNEL_CONFIG,
                    AudioConfig.AUDIO_FORMAT,
                    minBuf * 2
                )
                if (record.state != AudioRecord.STATE_INITIALIZED) {
                    Log.e(TAG, "AudioRecord failed to initialize")
                    return@Thread
                }

                audioRecord = record
                record.startRecording()

                val chunk = ShortArray(CHUNK_SAMPLES)
                val threshold = 0.03f + (1f - AudioConfig.WAKE_WORD_SENSITIVITY) * 0.09f
                var loudStreak = 0

                while (isListening) {
                    val read = record.read(chunk, 0, chunk.size)
                    if (read <= 0) continue

                    val rms = rms(chunk, read)
                    if (rms > threshold) {
                        loudStreak++
                        if (loudStreak >= STREAK_THRESHOLD) {
                            Log.i(TAG, "Voice activity detected (rms=$rms)")
                            break
                        }
                    } else {
                        loudStreak = 0
                    }
                }
            } catch (e: Exception) {
                Log.e(TAG, "Voice-activity detection error: ${e.message}")
            } finally {
                try {
                    record?.stop()
                } catch (_: Exception) {
                }
                try {
                    record?.release()
                } catch (_: Exception) {
                }
                audioRecord = null
            }

            if (isListening) {
                onWakeWordDetected()
            }
        }
        detectionThread?.start()
    }

    /** Normalized RMS (0..1) of the first [length] int16 samples. */
    private fun rms(samples: ShortArray, length: Int): Float {
        if (length <= 0) return 0f
        var sum = 0.0
        for (i in 0 until length) {
            val f = samples[i] / 32768.0
            sum += f * f
        }
        return sqrt(sum / length).toFloat()
    }

    private fun stopListening() {
        isListening = false
        restartRunnable?.let { mainHandler.removeCallbacks(it) }
        restartRunnable = null

        // Stop the recognizer if it is running.
        try {
            speechRecognizer?.cancel()
        } catch (_: Exception) {
        }
        try {
            speechRecognizer?.destroy()
        } catch (_: Exception) {
        }
        speechRecognizer = null

        // Wake the VAD thread so it exits promptly instead of blocking on read().
        try {
            audioRecord?.stop()
        } catch (_: Exception) {
        }
        stopForeground(STOP_FOREGROUND_REMOVE)
        Log.i(TAG, "Wake-word detection stopped")
        stopSelf()
    }

    private fun onWakeWordDetected() {
        Log.i(TAG, "Wake triggered — handing the mic to the recording service")
        isListening = false
        restartRunnable?.let { mainHandler.removeCallbacks(it) }
        restartRunnable = null
        try {
            speechRecognizer?.cancel()
        } catch (_: Exception) {
        }
        try {
            speechRecognizer?.destroy()
        } catch (_: Exception) {
        }
        speechRecognizer = null
        stopForeground(STOP_FOREGROUND_REMOVE)

        // Notify the backend that a wake event happened.
        webSocketClient.onWakeWordDetected()

        // Start the recording service (it acquires the mic; we released ours above).
        val recordingIntent = Intent(this, VoiceRecordingService::class.java).apply {
            action = VoiceRecordingService.ACTION_START
        }
        if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.O) {
            startForegroundService(recordingIntent)
        } else {
            startService(recordingIntent)
        }
    }

    private fun createNotification(): Notification {
        return NotificationCompat.Builder(this, ArenaVoiceApp.WAKE_WORD_CHANNEL_ID)
            .setContentTitle("Arena Voice")
            .setContentText("Listening for \"Hi Android\"…")
            .setSmallIcon(android.R.drawable.ic_btn_speak_now)
            .setPriority(NotificationCompat.PRIORITY_LOW)
            .setOngoing(true)
            .build()
    }

    override fun onDestroy() {
        isListening = false
        restartRunnable?.let { mainHandler.removeCallbacks(it) }
        restartRunnable = null
        try {
            speechRecognizer?.destroy()
        } catch (_: Exception) {
        }
        speechRecognizer = null
        detectionThread?.interrupt()
        detectionThread = null
        try {
            audioRecord?.release()
        } catch (_: Exception) {
        }
        audioRecord = null
        super.onDestroy()
        Log.d(TAG, "WakeWordService destroyed")
    }

    private fun isWakePhrase(text: String): Boolean {
        val normalized = text.lowercase()
            .replace(Regex("[^a-z0-9 ]"), " ")
            .replace(Regex("\\s+"), " ")
            .trim()
        return WAKE_PHRASES.any { normalized.contains(it) }
    }

    companion object {
        private const val TAG = "WakeWordService"
        private const val NOTIFICATION_ID = 1001

        // Detection tuning: 512 samples/chunk @16kHz = 32ms per chunk; a wake
        // needs 5 consecutive loud chunks (~160ms of sustained loudness).
        private const val CHUNK_SAMPLES = 512
        private const val STREAK_THRESHOLD = 5

        // Gap between recognition attempts (the recognizer handles one short
        // utterance per session, so we keep re-arming it).
        private const val RESTART_DELAY_MS = 500L

        // Accepted wake phrases (normalized, lowercase). The canonical one is
        // "hi android" (AudioConfig.WAKE_WORD); the rest are common aliases.
        private val WAKE_PHRASES = listOf(
            "hi android",
            "hey android",
            "hi beanie",
            "hey beanie",
            "hey arena",
        )

        const val ACTION_START = "com.arena.voice.action.START_WAKE_WORD"
        const val ACTION_STOP = "com.arena.voice.action.STOP_WAKE_WORD"
        const val ACTION_REARM = "com.arena.voice.action.REARM_WAKE_WORD"
    }
}
