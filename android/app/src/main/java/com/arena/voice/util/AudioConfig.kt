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
    
    // Wake word configuration.
    // The canonical wake phrase is "hi android"; the WakeWordService's keyword
    // spotter also accepts a few common aliases (see WAKE_PHRASES there).
    const val WAKE_WORD = "hi android"
    const val WAKE_WORD_SENSITIVITY = 0.5f

    // Network configuration: the server URL lives in
    // VoiceWebSocketClient.DEFAULT_SERVER_URL (ws://10.0.2.2:8000/ws for the
    // emulator; override with your PC's LAN IP on a physical device).
    
    // Audio playback
    const val PLAYBACK_SAMPLE_RATE = 16000
    const val PLAYBACK_CHANNEL_CONFIG = AudioFormat.CHANNEL_OUT_MONO
    const val PLAYBACK_AUDIO_FORMAT = AudioFormat.ENCODING_PCM_16BIT
}
