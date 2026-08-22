import { logger } from '../services/logger';
import { useEffect, useRef, useState, useCallback } from 'react';
import { webSocketService, type VoiceState } from '../services/websocket';

interface UseVoiceOptions {
  conversationId: string;
  onTranscript?: (text: string, isFinal: boolean) => void;
  onError?: (error: string) => void;
}

interface UseVoiceReturn {
  voiceState: VoiceState;
  isListening: boolean;
  startListening: () => Promise<void>;
  stopListening: () => void;
  transcript: string;
  error: string | null;
  /** 0..1 — microphone amplitude (for the reactive orb's "listening" field). */
  inputLevel: number;
  /** 0..1 — TTS playback amplitude (for the orb's "speaking" field). */
  outputLevel: number;
}

export function useVoice({ conversationId, onTranscript, onError }: UseVoiceOptions): UseVoiceReturn {
  const [voiceState, setVoiceState] = useState<VoiceState>('idle');
  const [transcript, setTranscript] = useState('');
  const [error, setError] = useState<string | null>(null);
  const [inputLevel, setInputLevel] = useState(0);
  const [outputLevel, setOutputLevel] = useState(0);

  const mediaStreamRef = useRef<MediaStream | null>(null);
  const audioContextRef = useRef<AudioContext | null>(null);
  const processorRef = useRef<ScriptProcessorNode | null>(null);
  const analyserRef = useRef<AnalyserNode | null>(null);
  const levelRafRef = useRef<number | null>(null);
  const lastOutputRef = useRef(0);
  const audioQueueRef = useRef<AudioBuffer[]>([]);
  const isPlayingRef = useRef(false);

  // Mirror of voiceState kept in a ref so the audio processor's callback always
  // reads the *current* state instead of the stale value captured when
  // startListening was called (which left the mic stuck in 'idle').
  const voiceStateRef = useRef<VoiceState>('idle');
  voiceStateRef.current = voiceState;

  const isListening = voiceState !== 'idle' && voiceState !== 'stopped';

  // Use ref to break circular reference for React Compiler
  const playNextBufferRef = useRef<() => void>(() => {});

  // ── Amplitude loop (mic level via AnalyserNode + TTS level decay) ─────────
  const stopLevelLoop = useCallback(() => {
    if (levelRafRef.current) {
      cancelAnimationFrame(levelRafRef.current);
      levelRafRef.current = null;
    }
    setInputLevel(0);
    setOutputLevel(0);
  }, []);

  const startLevelLoop = useCallback(() => {
    if (levelRafRef.current) return;
    let last = 0;
    const loop = (ts: number) => {
      // Throttle state updates to ~30 fps (orb smooths the rest in its own rAF).
      if (ts - last > 33) {
        last = ts;
        const analyser = analyserRef.current;
        if (analyser) {
          const data = new Uint8Array(analyser.fftSize);
          analyser.getByteTimeDomainData(data);
          let sum = 0;
          for (let i = 0; i < data.length; i++) {
            const v = (data[i] - 128) / 128;
            sum += v * v;
          }
          const rms = Math.sqrt(sum / data.length);
          setInputLevel(clampLevel((rms - 0.02) / 0.3));
        }
        // Decay the TTS level when nothing has played recently.
        if (ts - lastOutputRef.current > 180) {
          setOutputLevel((prev) => (prev > 0.01 ? prev * 0.6 : 0));
        }
      }
      levelRafRef.current = requestAnimationFrame(loop);
    };
    levelRafRef.current = requestAnimationFrame(loop);
  }, []);

  // Play next buffer from queue
  const playNextBuffer = useCallback(() => {
    if (audioQueueRef.current.length === 0) {
      isPlayingRef.current = false;
      return;
    }

    isPlayingRef.current = true;
    const audioContext = audioContextRef.current;
    if (!audioContext) return;

    const buffer = audioQueueRef.current.shift()!;
    const source = audioContext.createBufferSource();
    source.buffer = buffer;
    source.connect(audioContext.destination);
    source.onended = () => playNextBufferRef.current();
    source.start();
  }, []);

  // Keep ref in sync
  playNextBufferRef.current = playNextBuffer;

  // Play audio chunk from TTS
  const playAudioChunk = useCallback(async (audioData: ArrayBuffer) => {
    try {
      if (!audioContextRef.current) {
        audioContextRef.current = new AudioContext({ sampleRate: 16000 });
      }

      const audioContext = audioContextRef.current;

      // Convert ArrayBuffer to AudioBuffer
      // Assuming 16-bit PCM, mono
      const int16Array = new Int16Array(audioData);
      const float32Array = new Float32Array(int16Array.length);
      let sum = 0;
      for (let i = 0; i < int16Array.length; i++) {
        float32Array[i] = int16Array[i] / 32768.0;
        const v = int16Array[i] / 32768.0;
        sum += v * v;
      }

      // Track playback amplitude so the orb's "speaking" field reacts to TTS.
      const rms = int16Array.length ? Math.sqrt(sum / int16Array.length) : 0;
      setOutputLevel(clampLevel(rms / 0.3));
      lastOutputRef.current = performance.now();

      const audioBuffer = audioContext.createBuffer(1, float32Array.length, 16000);
      audioBuffer.getChannelData(0).set(float32Array);

      audioQueueRef.current.push(audioBuffer);

      if (!isPlayingRef.current) {
        playNextBuffer();
      }
    } catch (err) {
      logger.error('Error playing audio chunk:', err);
    }
  }, [playNextBuffer]);

  // Handle incoming WebSocket events
  useEffect(() => {
    const unsubscribe = webSocketService.subscribe((event) => {
      if (event.type === 'voice_state') {
        setVoiceState(event.data.state);
      } else if (event.type === 'voice_transcript') {
        const { text, is_final } = event.data;
        setTranscript(text);
        onTranscript?.(text, is_final);
      } else if (event.type === 'voice_audio') {
        // Queue audio for playback
        playAudioChunk(event.data);
      } else if (event.type === 'error') {
        setError(event.data.message);
        onError?.(event.data.message);
      }
    });

    return unsubscribe;
  }, [onTranscript, onError, playAudioChunk]);

  // Start listening (request microphone and stream audio)
  const startListening = useCallback(async () => {
    try {
      setError(null);

      // Request microphone access
      const stream = await navigator.mediaDevices.getUserMedia({
        audio: {
          sampleRate: 16000,
          channelCount: 1,
          echoCancellation: true,
          noiseSuppression: true,
        },
      });

      mediaStreamRef.current = stream;

      // Create audio context for processing
      audioContextRef.current = new AudioContext({ sampleRate: 16000 });
      const audioContext = audioContextRef.current;

      const source = audioContext.createMediaStreamSource(stream);

      // Use ScriptProcessorNode to capture audio chunks
      // (In production, consider AudioWorklet for better performance)
      const processor = audioContext.createScriptProcessor(4096, 1, 1);
      processorRef.current = processor;

      processor.onaudioprocess = (event) => {
        if (voiceStateRef.current === 'idle' || voiceStateRef.current === 'stopped') return;

        const inputData = event.inputBuffer.getChannelData(0);

        // Convert float32 to int16 PCM
        const int16Array = new Int16Array(inputData.length);
        for (let i = 0; i < inputData.length; i++) {
          const s = Math.max(-1, Math.min(1, inputData[i]));
          int16Array[i] = s < 0 ? s * 0x8000 : s * 0x7fff;
        }

        // Send to backend
        webSocketService.sendBinary(int16Array.buffer);
      };

      source.connect(processor);
      processor.connect(audioContext.destination);

      // AnalyserNode (parallel tap) for smooth mic-amplitude → orb field.
      const analyser = audioContext.createAnalyser();
      analyser.fftSize = 256;
      analyser.smoothingTimeConstant = 0.4;
      source.connect(analyser);
      analyserRef.current = analyser;
      startLevelLoop();

      // Tell backend to start voice input
      webSocketService.startVoiceInput(conversationId);
    } catch (err) {
      const message = err instanceof Error ? err.message : 'Failed to access microphone';
      setError(message);
      onError?.(message);
    }
  }, [conversationId, onError]);

  // Stop listening
  const stopListening = useCallback(() => {
    // Stop microphone stream
    if (mediaStreamRef.current) {
      mediaStreamRef.current.getTracks().forEach((track) => track.stop());
      mediaStreamRef.current = null;
    }

    // Stop audio processing
    if (processorRef.current) {
      processorRef.current.disconnect();
      processorRef.current = null;
    }

    // Stop audio context
    if (audioContextRef.current && audioContextRef.current.state !== 'closed') {
      audioContextRef.current.close();
      audioContextRef.current = null;
    }

    analyserRef.current = null;
    stopLevelLoop();

    // Clear audio queue
    audioQueueRef.current = [];
    isPlayingRef.current = false;

    // Tell backend to stop
    webSocketService.stopVoiceInput(conversationId);

    setVoiceState('idle');
    setTranscript('');
  }, [conversationId, stopLevelLoop]);

  // Cleanup on unmount
  useEffect(() => {
    return () => {
      stopLevelLoop();
      stopListening();
    };
  }, [stopListening, stopLevelLoop]);

  return {
    voiceState,
    isListening,
    startListening,
    stopListening,
    transcript,
    error,
    inputLevel,
    outputLevel,
  };
}

function clampLevel(n: number): number {
  return n <= 0 ? 0 : n >= 1 ? 1 : n;
}
