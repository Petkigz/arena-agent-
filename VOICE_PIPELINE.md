# Voice Pipeline Implementation Plan

## Phase 3a: PC Voice Pipeline

### Architecture Overview

```
Microphone Input
    ↓
Audio Capture Service (PyAudio)
    ↓
Audio Buffer (circular buffer)
    ↓
┌─────────────────────────────────────┐
│  Wake Word Detector (openWakeWord)  │ ← Always listening
└─────────────────────────────────────┘
    ↓ (wake word detected)
┌─────────────────────────────────────┐
│  Voice Activity Detector (Silero)   │ ← Detects speech start/end
└─────────────────────────────────────┘
    ↓ (speech detected)
┌─────────────────────────────────────┐
│  Speech-to-Text (faster-whisper)    │ ← Transcribes speech
└─────────────────────────────────────┘
    ↓ (transcription complete)
┌─────────────────────────────────────┐
│  Voice Orchestrator                 │ ← Routes to cognitive runtime
└─────────────────────────────────────┘
    ↓ (response ready)
┌─────────────────────────────────────┐
│  Text-to-Speech (Piper)             │ ← Synthesizes response
└─────────────────────────────────────┘
    ↓
Audio Playback (PyAudio)
```

### Components to Build

#### 1. Audio Capture Service (`backend/voice/audio_capture.py`)
- PyAudio-based audio capture
- Circular buffer for continuous audio
- Configurable sample rate (16kHz for wake word, 16kHz for STT)
- Audio format: 16-bit PCM, mono

#### 2. Wake Word Detector (`backend/voice/wake_word.py`)
- openWakeWord integration
- Custom wake word support ("Hey Arena", "Computer", etc.)
- Low-latency detection (<100ms)
- Configurable sensitivity

#### 3. Voice Activity Detector (`backend/voice/vad.py`)
- Silero VAD integration
- Detects speech start/end
- Configurable threshold
- Handles silence detection

#### 4. Speech-to-Text (`backend/voice/stt.py`)
- faster-whisper integration
- Real-time streaming transcription
- Configurable model size (tiny/base/small/medium)
- Language detection

#### 5. Text-to-Speech (`backend/voice/tts.py`)
- Piper TTS integration
- Streaming audio synthesis
- Configurable voice selection
- Speed control

#### 6. Voice Orchestrator (`backend/voice/orchestrator.py`)
- Coordinates all voice components
- Manages state machine (idle → listening → processing → speaking)
- Integrates with WebSocket
- Handles barge-in (interrupt while speaking)

#### 7. Voice Service (`backend/voice/service.py`)
- Main voice service API
- WebSocket message handlers
- Configuration management
- Error handling

### Dependencies

```bash
pip install openwakeword
pip install silero-vad
pip install faster-whisper
pip install piper-tts
pip install pyaudio
pip install numpy
pip install webrtc-audio-processing
```

### Implementation Order

1. **Audio Capture** - Foundation for all voice features
2. **Wake Word Detection** - Always-on listening
3. **Voice Activity Detection** - Speech detection
4. **Speech-to-Text** - Transcription
5. **Text-to-Speech** - Response synthesis
6. **Voice Orchestrator** - State management
7. **Voice Service** - API and WebSocket integration
8. **Testing** - End-to-end testing

### Configuration

```python
VOICE_CONFIG = {
    "sample_rate": 16000,  # 16kHz for wake word and STT
    "channels": 1,  # Mono
    "chunk_size": 1024,  # Audio buffer size
    "wake_word": "hey_arena",
    "wake_word_sensitivity": 0.5,
    "vad_threshold": 0.5,
    "stt_model": "base",  # tiny/base/small/medium
    "tts_voice": "en_US-lessac-medium",
    "tts_speed": 1.0,
    "noise_suppression": True,
    "barge_in_enabled": True,
}
```

### State Machine

```
IDLE
  ↓ (wake word detected)
LISTENING
  ↓ (speech start)
RECORDING
  ↓ (speech end)
PROCESSING
  ↓ (transcription complete)
THINKING
  ↓ (response ready)
SPEAKING
  ↓ (speech complete)
IDLE
```

### WebSocket Messages

**Client → Server:**
```json
{
  "type": "voice_start",
  "conversation_id": "conv_123"
}

{
  "type": "voice_stop",
  "conversation_id": "conv_123"
}
```

**Server → Client:**
```json
{
  "type": "voice_status",
  "status": "listening",  // idle/listening/recording/processing/thinking/speaking
  "conversation_id": "conv_123"
}

{
  "type": "voice_transcript",
  "transcript": "What's the weather?",
  "is_final": true,
  "conversation_id": "conv_123"
}

{
  "type": "voice_audio",
  "audio": "base64_encoded_audio",
  "conversation_id": "conv_123"
}
```

### Next Steps

1. Install dependencies
2. Implement audio capture service
3. Implement wake word detector
4. Implement VAD
5. Implement STT
6. Implement TTS
7. Implement orchestrator
8. Implement voice service
9. Integrate with WebSocket
10. Test end-to-end

### Success Criteria

- ✅ Wake word detection <100ms latency
- ✅ Speech detection accuracy >95%
- ✅ Transcription accuracy >90%
- ✅ TTS latency <500ms
- ✅ Barge-in support (interrupt while speaking)
- ✅ Noise suppression in noisy environments
- ✅ WebSocket streaming for real-time feedback
