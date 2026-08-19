package com.arena.voice.audio

import android.media.AudioAttributes
import android.media.AudioFormat
import android.media.AudioTrack
import android.util.Base64
import android.util.Log
import com.arena.voice.util.AudioConfig
import javax.inject.Inject
import javax.inject.Singleton

@Singleton
class AudioPlaybackManager @Inject constructor() {

    private var audioTrack: AudioTrack? = null
    @Volatile private var isPlaying = false
    private var playbackThread: Thread? = null

    fun playAudio(audioBase64: String) {
        try {
            val audioBytes = Base64.decode(audioBase64, Base64.DEFAULT)
            playAudio(audioBytes)
        } catch (e: Exception) {
            Log.e(TAG, "Failed to decode audio: ${e.message}")
        }
    }

    fun playAudio(audioBytes: ByteArray) {
        // Stop any current playback (supports barge-in)
        if (isPlaying) {
            Log.i(TAG, "Barge-in: stopping current playback")
            stopPlayback()
        }

        try {
            val bufferSize = AudioTrack.getMinBufferSize(
                AudioConfig.PLAYBACK_SAMPLE_RATE,
                AudioConfig.PLAYBACK_CHANNEL_CONFIG,
                AudioConfig.PLAYBACK_AUDIO_FORMAT
            )

            val audioAttributes = AudioAttributes.Builder()
                .setUsage(AudioAttributes.USAGE_ASSISTANT)
                .setContentType(AudioAttributes.CONTENT_TYPE_SPEECH)
                .build()

            val audioFormat = AudioFormat.Builder()
                .setSampleRate(AudioConfig.PLAYBACK_SAMPLE_RATE)
                .setEncoding(AudioConfig.PLAYBACK_AUDIO_FORMAT)
                .setChannelMask(AudioConfig.PLAYBACK_CHANNEL_CONFIG)
                .build()

            audioTrack = AudioTrack.Builder()
                .setAudioAttributes(audioAttributes)
                .setAudioFormat(audioFormat)
                .setBufferSizeInBytes(bufferSize * 2)
                .setTransferMode(AudioTrack.MODE_STREAM)
                .build()

            audioTrack?.play()
            isPlaying = true

            Log.i(TAG, "Playing audio: ${audioBytes.size} bytes")

            // Write audio data in a background thread
            val track = audioTrack
            playbackThread = Thread {
                try {
                    track?.write(audioBytes, 0, audioBytes.size)
                    // Wait for playback to complete
                    val durationMs = (audioBytes.size.toLong() / (AudioConfig.PLAYBACK_SAMPLE_RATE * 2)) * 1000
                    Thread.sleep(durationMs)
                } catch (e: InterruptedException) {
                    Log.i(TAG, "Playback interrupted (barge-in)")
                } catch (e: Exception) {
                    Log.e(TAG, "Playback error: ${e.message}")
                } finally {
                    stopPlayback()
                }
            }
            playbackThread?.start()

        } catch (e: Exception) {
            Log.e(TAG, "Failed to play audio: ${e.message}")
            stopPlayback()
        }
    }

    fun stopPlayback() {
        if (!isPlaying && playbackThread == null) return

        isPlaying = false

        // Interrupt playback thread
        playbackThread?.interrupt()
        playbackThread = null

        try {
            audioTrack?.let { track ->
                if (track.playState == AudioTrack.PLAYSTATE_PLAYING) {
                    track.stop()
                }
                track.release()
            }
            audioTrack = null

            Log.i(TAG, "Audio playback stopped")

        } catch (e: Exception) {
            Log.e(TAG, "Error stopping playback: ${e.message}")
        }
    }

    fun release() {
        stopPlayback()
    }

    companion object {
        private const val TAG = "AudioPlaybackManager"
    }
}
