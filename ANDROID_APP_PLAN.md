# Android Voice App Implementation Plan

## Phase 3b: Android Voice App

### Architecture Overview

```
Android App
    ↓
┌─────────────────────────────────────┐
│  Wake Word Service (Background)     │ ← Always listening
│  (openWakeWord Android)             │
└─────────────────────────────────────┘
    ↓ (wake word detected)
┌─────────────────────────────────────┐
│  Voice Recording Service            │ ← Records speech
│  (AudioRecord API)                  │
└─────────────────────────────────────┘
    ↓ (audio captured)
┌─────────────────────────────────────┐
│  WebSocket Client                   │ ← Streams to PC
│  (OkHttp + WebSocket)               │
└─────────────────────────────────────┘
    ↓ (audio sent)
┌─────────────────────────────────────┐
│  PC Backend                         │ ← Processes STT/TTS
│  (Voice Pipeline)                   │
└─────────────────────────────────────┘
    ↓ (response audio)
┌─────────────────────────────────────┐
│  Audio Playback                     │ ← Plays response
│  (AudioTrack API)                   │
└─────────────────────────────────────┘
```

### Components to Build

#### 1. Android App Structure
- Kotlin + Jetpack Compose
- Material Design 3
- MVVM architecture
- Hilt dependency injection

#### 2. Wake Word Service (`WakeWordService.kt`)
- Android background service
- openWakeWord Android integration
- Always-on listening
- Low power consumption
- Notification for foreground service

#### 3. Voice Recording Service (`VoiceRecordingService.kt`)
- AudioRecord API
- 16kHz sample rate, mono
- Streaming audio to WebSocket
- VAD integration (optional)

#### 4. WebSocket Client (`VoiceWebSocketClient.kt`)
- OkHttp WebSocket client
- Auto-reconnect
- Message handling
- Audio streaming (PCM 16kHz)

#### 5. Audio Playback (`AudioPlaybackManager.kt`)
- AudioTrack API
- Streaming playback
- Queue management

#### 6. UI Components
- Main screen (voice button, status)
- Settings screen (wake word, server address)
- Conversation screen (transcripts)

#### 7. Permissions
- RECORD_AUDIO
- FOREGROUND_SERVICE
- INTERNET
- POST_NOTIFICATIONS (Android 13+)

### Dependencies

```gradle
// Jetpack Compose
implementation("androidx.compose.ui:ui:1.5.0")
implementation("androidx.compose.material3:material3:1.1.0")
implementation("androidx.compose.ui:ui-tooling-preview:1.5.0")

// WebSocket
implementation("com.squareup.okhttp3:okhttp:4.11.0")

// Wake word
implementation("ai.picovoice:porcupine-android:2.2.0")

// Audio
implementation("com.google.android.exoplayer:exoplayer:2.19.0")

// Hilt
implementation("com.google.dagger:hilt-android:2.48")
kapt("com.google.dagger:hilt-android-compiler:2.48")

// Lifecycle
implementation("androidx.lifecycle:lifecycle-viewmodel-compose:2.6.1")
implementation("androidx.lifecycle:lifecycle-runtime-compose:2.6.1")
```

### Implementation Order

1. **Project Setup** - Android Studio project with dependencies
2. **Wake Word Service** - Background service with openWakeWord
3. **WebSocket Client** - Connection to PC backend
4. **Voice Recording** - Audio capture and streaming
5. **Audio Playback** - Response playback
6. **UI** - Jetpack Compose UI
7. **Integration** - Connect all components
8. **Testing** - End-to-end testing

### File Structure

```
app/
├── src/main/
│   ├── java/com/arena/voice/
│   │   ├── ArenaVoiceApp.kt
│   │   ├── MainActivity.kt
│   │   ├── di/
│   │   │   └── AppModule.kt
│   │   ├── service/
│   │   │   ├── WakeWordService.kt
│   │   │   └── VoiceRecordingService.kt
│   │   ├── websocket/
│   │   │   └── VoiceWebSocketClient.kt
│   │   ├── audio/
│   │   │   ├── AudioPlaybackManager.kt
│   │   │   └── AudioRecorder.kt
│   │   ├── ui/
│   │   │   ├── MainActivity.kt
│   │   │   ├── MainViewModel.kt
│   │   │   ├── screens/
│   │   │   │   ├── MainScreen.kt
│   │   │   │   ├── SettingsScreen.kt
│   │   │   │   └── ConversationScreen.kt
│   │   │   └── components/
│   │   │       ├── VoiceButton.kt
│   │   │       └── StatusIndicator.kt
│   │   └── util/
│   │       └── AudioUtils.kt
│   └── res/
│       ├── values/
│       │   ├── strings.xml
│       │   ├── colors.xml
│       │   └── themes.xml
│       └── drawable/
│           └── ic_microphone.xml
└── build.gradle.kts
```

### Configuration

```kotlin
object VoiceConfig {
    const val SAMPLE_RATE = 16000
    const val CHANNELS = 1
    const val BITS_PER_SAMPLE = 16
    
    const val WAKE_WORD = "hey_arena"
    const val WAKE_WORD_SENSITIVITY = 0.5f
    
    const val DEFAULT_SERVER = "ws://192.168.1.100:8000/ws"
    
    const val RECORDING_BUFFER_SIZE = 4096
    const val STREAMING_CHUNK_SIZE = 1024
}
```

### WebSocket Messages

**Android → PC:**
```json
{
  "type": "voice_start",
  "conversation_id": "conv_123"
}

{
  "type": "voice_audio",
  "audio": "base64_encoded_pcm",
  "sample_rate": 16000
}

{
  "type": "voice_stop",
  "conversation_id": "conv_123"
}
```

**PC → Android:**
```json
{
  "type": "voice_state",
  "state": "listening"
}

{
  "type": "voice_transcript",
  "text": "What's the weather?",
  "is_final": true
}

{
  "type": "voice_audio",
  "audio": "base64_encoded_pcm",
  "sample_rate": 16000
}
```

### Permissions (AndroidManifest.xml)

```xml
<uses-permission android:name="android.permission.RECORD_AUDIO" />
<uses-permission android:name="android.permission.INTERNET" />
<uses-permission android:name="android.permission.FOREGROUND_SERVICE" />
<uses-permission android:name="android.permission.FOREGROUND_SERVICE_MICROPHONE" />
<uses-permission android:name="android.permission.POST_NOTIFICATIONS" />
```

### Success Criteria

- ✅ Wake word detection <200ms latency
- ✅ Background service stays alive
- ✅ WebSocket connection stable
- ✅ Audio streaming <100ms latency
- ✅ Audio playback <200ms latency
- ✅ Battery consumption <5% per hour
- ✅ UI responsive and intuitive

### Next Steps

1. Create Android Studio project
2. Implement wake word service
3. Implement WebSocket client
4. Implement voice recording
5. Implement audio playback
6. Build UI
7. Integrate and test
