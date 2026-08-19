package com.arena.voice.service

import android.app.Notification
import android.app.Service
import android.content.Intent
import android.media.AudioFormat
import android.media.AudioRecord
import android.media.MediaRecorder
import android.os.IBinder
import android.util.Log
import androidx.core.app.NotificationCompat
import com.arena.voice.ArenaVoiceApp
import com.arena.voice.websocket.VoiceWebSocketClient
import com.arena.voice.util.AudioConfig
import dagger.hilt.android.AndroidEntryPoint
import kotlinx.coroutines.*
import javax.inject.Inject

@AndroidEntryPoint
class VoiceRecordingService : Service() {
    
    @Inject
    lateinit var webSocketClient: VoiceWebSocketClient
    
    private var audioRecord: AudioRecord? = null
    private var isRecording = false
    private var recordingJob: Job? = null
    
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
            // Create notification for foreground service
            val notification = createNotification()
            startForeground(NOTIFICATION_ID, notification)
            
            // Initialize AudioRecord
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
            
            Log.i(TAG, "Voice recording started")
            
            // Start recording coroutine
            recordingJob = CoroutineScope(Dispatchers.IO).launch {
                recordAndStream()
            }
            
        } catch (e: Exception) {
            Log.e(TAG, "Failed to start recording: ${e.message}")
            stopSelf()
        }
    }
    
    private suspend fun recordAndStream() {
        val buffer = ShortArray(AudioConfig.STREAMING_CHUNK_SIZE)
        
        while (isRecording) {
            val read = audioRecord?.read(buffer, 0, buffer.size) ?: 0
            
            if (read > 0) {
                // Convert to bytes
                val bytes = ByteArray(read * 2)
                for (i in 0 until read) {
                    bytes[i * 2] = (buffer[i].toInt() and 0xFF).toByte()
                    bytes[i * 2 + 1] = (buffer[i].toInt() shr 8).toByte()
                }
                
                // Stream to WebSocket
                webSocketClient.sendAudio(bytes)
            }
            
            delay(10)  // Small delay to prevent busy waiting
        }
    }
    
    private fun stopRecording() {
        if (!isRecording) return
        
        isRecording = false
        recordingJob?.cancel()
        recordingJob = null
        
        try {
            audioRecord?.stop()
            audioRecord?.release()
            audioRecord = null
            
            stopForeground(STOP_FOREGROUND_REMOVE)
            
            Log.i(TAG, "Voice recording stopped")
            
        } catch (e: Exception) {
            Log.e(TAG, "Error stopping recording: ${e.message}")
        }
        
        stopSelf()
    }
    
    private fun createNotification(): Notification {
        return NotificationCompat.Builder(this, ArenaVoiceApp.RECORDING_CHANNEL_ID)
            .setContentTitle("Arena Voice")
            .setContentText("Recording your voice...")
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
        
        const val ACTION_START = "com.arena.voice.action.START_RECORDING"
        const val ACTION_STOP = "com.arena.voice.action.STOP_RECORDING"
    }
}
