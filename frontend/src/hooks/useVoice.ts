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
}

export function useVoice({ conversationId, onTranscript, onError }: UseVoiceOptions): UseVoiceReturn {
  const [voiceState, setVoiceState] = useState<VoiceState>('idle');
  const [transcript, setTranscript] = useState('');
  const [error, setError] = useState<string | null>(null);

  const mediaStreamRef = useRef<MediaStream | null>(null);
  const audioContextRef = useRef<AudioContext | null>(null);
  const processorRef = useRef<ScriptProcessorNode | null>(null);
  const audioQueueRef = useRef<AudioBuffer[]>([]);
  const isPlayingRef = useRef(false);

  const isListening = voiceState !== 'idle' && voiceState !== 'stopped';

  // Use ref to break circular reference for React Compiler
  const playNextBufferRef = useRef<() => void>(() => {});

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
      for (let i = 0; i < int16Array.length; i++) {
        float32Array[i] = int16Array[i] / 32768.0;
      }

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
        if (voiceState === 'idle' || voiceState === 'stopped') return;

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

      // Tell backend to start voice input
      webSocketService.startVoiceInput(conversationId);
    } catch (err) {
      const message = err instanceof Error ? err.message : 'Failed to access microphone';
      setError(message);
      onError?.(message);
    }
  }, [conversationId, voiceState, onError]);

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

    // Clear audio queue
    audioQueueRef.current = [];
    isPlayingRef.current = false;

    // Tell backend to stop
    webSocketService.stopVoiceInput(conversationId);

    setVoiceState('idle');
    setTranscript('');
  }, [conversationId]);

  // Cleanup on unmount
  useEffect(() => {
    return () => {
      stopListening();
    };
  }, [stopListening]);

  return {
    voiceState,
    isListening,
    startListening,
    stopListening,
    transcript,
    error,
  };
}
