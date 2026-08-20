package com.arena.voice.util

import android.media.AudioFormat

object AudioConfig {
    // Audio configuration
    const val SAMPLE_RATE = 16000  // 16kHz
    const val CHANNEL_CONFIG = AudioFormat.CHANNEL_IN_MONO
    const val AUDIO_FORMAT = AudioFormat.ENCODING_PCM_16BIT
    
    // Buffer sizes
    const val STREAMING_CHUNK_SIZE = 1024  // Samples per chunk
    const val RECORDING_BUFFER_SIZE = 4096  // Buffer size for AudioRecord
    
    // Wake word configuration
    const val WAKE_WORD = "hey_arena"
    const val WAKE_WORD_SENSITIVITY = 0.5f
    
    // Network configuration
    const val DEFAULT_SERVER_URL = "ws://192.168.1.100:8000/ws/voice"
    
    // Audio playback
    const val PLAYBACK_SAMPLE_RATE = 16000
    const val PLAYBACK_CHANNEL_CONFIG = AudioFormat.CHANNEL_OUT_MONO
    const val PLAYBACK_AUDIO_FORMAT = AudioFormat.ENCODING_PCM_16BIT
}
