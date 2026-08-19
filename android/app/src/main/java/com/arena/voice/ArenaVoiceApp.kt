package com.arena.voice

import android.app.Application
import android.app.NotificationChannel
import android.app.NotificationManager
import android.os.Build
import dagger.hilt.android.HiltAndroidApp

@HiltAndroidApp
class ArenaVoiceApp : Application() {
    
    override fun onCreate() {
        super.onCreate()
        createNotificationChannels()
    }
    
    private fun createNotificationChannels() {
        if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.O) {
            val notificationManager = getSystemService(NotificationManager::class.java)
            
            // Wake word service channel
            val wakeWordChannel = NotificationChannel(
                WAKE_WORD_CHANNEL_ID,
                "Wake Word Detection",
                NotificationManager.IMPORTANCE_LOW
            ).apply {
                description = "Keeps Arena listening for wake word"
                setShowBadge(false)
            }
            notificationManager.createNotificationChannel(wakeWordChannel)
            
            // Voice recording channel
            val recordingChannel = NotificationChannel(
                RECORDING_CHANNEL_ID,
                "Voice Recording",
                NotificationManager.IMPORTANCE_LOW
            ).apply {
                description = "Arena is recording your voice"
                setShowBadge(false)
            }
            notificationManager.createNotificationChannel(recordingChannel)
        }
    }
    
    companion object {
        const val WAKE_WORD_CHANNEL_ID = "wake_word_channel"
        const val RECORDING_CHANNEL_ID = "recording_channel"
    }
}
