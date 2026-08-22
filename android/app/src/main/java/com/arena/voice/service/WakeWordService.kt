package com.arena.voice.service

import android.app.Notification
import android.app.Service
import android.content.Intent
import android.media.AudioRecord
import android.media.MediaRecorder
import android.os.Build
import android.os.IBinder
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
 * This listens to the phone microphone and wakes Beanie when it hears sustained
 * loudness (an energy-based voice-activity trigger). It is a REAL microphone
 * listener — it replaced the old 30-second "simulated" timer that faked a wake
 * event with no audio input at all.
 *
 * Honest scope: this is loudness-triggered VAD, NOT keyword spotting. It will
 * wake on any sustained speech (or loud noise), not specifically on "Hey Beanie".
 * True keyword spotting needs Picovoice Porcupine, which requires:
 *   1. a Picovoice access key (console.picovoice.ai),
 *   2. a .ppn keyword model, and
 *   3. a 16 KB-page-size-aligned Porcupine SDK (the earlier build failed on the
 *      Android 16 KB page-size requirement — see build.gradle.kts note).
 *
 * Flow: detect loudness → release the mic → start VoiceRecordingService (which
 * streams PCM to the backend) → VoiceRecordingService re-arms this service when
 * the utterance ends (voice_state "idle").
 */
@AndroidEntryPoint
class WakeWordService : Service() {

    @Inject
    lateinit var webSocketClient: VoiceWebSocketClient

    private var isListening = false
    private var audioRecord: AudioRecord? = null
    private var detectionThread: Thread? = null

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
            startEnergyDetection()
            Log.i(TAG, "Energy-based voice-activity detection started")
        } catch (e: Exception) {
            Log.e(TAG, "Failed to start voice-activity detection: ${e.message}")
            stopSelf()
        }
    }

    /** (Re)start the microphone detection loop after a recording session ends. */
    private fun rearm() {
        // If the service was stopped, bring it back to the foreground first.
        if (!isListening) {
            startListening()
            return
        }
        // A recording session just finished; start listening again on a fresh mic.
        if (detectionThread == null || !detectionThread!!.isAlive) {
            startEnergyDetection()
        }
    }

    /**
     * Captures mic PCM and wakes on sustained loudness (energy VAD).
     *
     * The trigger is: N consecutive chunks whose RMS exceeds a threshold derived
     * from [AudioConfig.WAKE_WORD_SENSITIVITY] (higher sensitivity = easier to
     * wake). This is real audio analysis, not a timer.
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

            // Only trigger if we are still supposed to be listening (not if we
            // were torn down mid-detection).
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
        // Wake the detection thread so it exits promptly instead of blocking on read().
        try {
            audioRecord?.stop()
        } catch (_: Exception) {
        }
        stopForeground(STOP_FOREGROUND_REMOVE)
        Log.i(TAG, "Voice-activity detection stopped")
        stopSelf()
    }

    private fun onWakeWordDetected() {
        Log.i(TAG, "Wake triggered — handing the mic to the recording service")
        isListening = false
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
            .setContentText("Listening for your voice…")
            .setSmallIcon(android.R.drawable.ic_btn_speak_now)
            .setPriority(NotificationCompat.PRIORITY_LOW)
            .setOngoing(true)
            .build()
    }

    override fun onDestroy() {
        isListening = false
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

    companion object {
        private const val TAG = "WakeWordService"
        private const val NOTIFICATION_ID = 1001

        // Detection tuning: 512 samples/chunk @16kHz = 32ms per chunk; a wake
        // needs 5 consecutive loud chunks (~160ms of sustained loudness).
        private const val CHUNK_SAMPLES = 512
        private const val STREAK_THRESHOLD = 5

        const val ACTION_START = "com.arena.voice.action.START_WAKE_WORD"
        const val ACTION_STOP = "com.arena.voice.action.STOP_WAKE_WORD"
        const val ACTION_REARM = "com.arena.voice.action.REARM_WAKE_WORD"
    }
}
