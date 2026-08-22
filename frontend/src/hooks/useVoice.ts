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
  /** Normalized microphone activity, 0..1, for Beanie's reactive presence. */
  audioLevel: number;
}

export function useVoice({ conversationId, onTranscript, onError }: UseVoiceOptions): UseVoiceReturn {
  const [voiceState, setVoiceState] = useState<VoiceState>('idle');
  const [transcript, setTranscript] = useState('');
  const [error, setError] = useState<string | null>(null);
  const [audioLevel, setAudioLevel] = useState(0);

  const voiceStateRef = useRef<VoiceState>('idle');
  const mediaStreamRef = useRef<MediaStream | null>(null);
  const audioContextRef = useRef<AudioContext | null>(null);
  const processorRef = useRef<ScriptProcessorNode | null>(null);
  const audioQueueRef = useRef<AudioBuffer[]>([]);
  const isPlayingRef = useRef(false);

  const setCurrentVoiceState = useCallback((state: VoiceState) => {
    voiceStateRef.current = state;
    setVoiceState(state);
  }, []);

  const isListening = voiceState !== 'idle' && voiceState !== 'stopped';

  const playNextBufferRef = useRef<() => void>(() => {});

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

  playNextBufferRef.current = playNextBuffer;

  const playAudioChunk = useCallback(async (audioData: ArrayBuffer) => {
    try {
      if (!audioContextRef.current) audioContextRef.current = new AudioContext({ sampleRate: 16000 });
      const audioContext = audioContextRef.current;
      const int16Array = new Int16Array(audioData);
      const float32Array = new Float32Array(int16Array.length);
      for (let i = 0; i < int16Array.length; i++) float32Array[i] = int16Array[i] / 32768.0;

      const audioBuffer = audioContext.createBuffer(1, float32Array.length, 16000);
      audioBuffer.getChannelData(0).set(float32Array);
      audioQueueRef.current.push(audioBuffer);
      if (!isPlayingRef.current) playNextBuffer();
    } catch (err) {
      logger.error('Error playing audio chunk:', err);
    }
  }, [playNextBuffer]);

  useEffect(() => {
    const unsubscribe = webSocketService.subscribe((event) => {
      if (event.type === 'voice_state') {
        setCurrentVoiceState(event.data.state);
      } else if (event.type === 'voice_transcript') {
        const { text, is_final } = event.data;
        setTranscript(text);
        onTranscript?.(text, is_final);
      } else if (event.type === 'voice_audio') {
        playAudioChunk(event.data);
      } else if (event.type === 'error') {
        setError(event.data.message);
        onError?.(event.data.message);
      }
    });
    return unsubscribe;
  }, [onTranscript, onError, playAudioChunk, setCurrentVoiceState]);

  const startListening = useCallback(async () => {
    try {
      setError(null);
      const stream = await navigator.mediaDevices.getUserMedia({
        audio: { sampleRate: 16000, channelCount: 1, echoCancellation: true, noiseSuppression: true },
      });
      mediaStreamRef.current = stream;

      audioContextRef.current = new AudioContext({ sampleRate: 16000 });
      const audioContext = audioContextRef.current;
      const source = audioContext.createMediaStreamSource(stream);
      const processor = audioContext.createScriptProcessor(4096, 1, 1);
      processorRef.current = processor;

      processor.onaudioprocess = (event) => {
        const state = voiceStateRef.current;
        if (state === 'idle' || state === 'stopped') return;

        const inputData = event.inputBuffer.getChannelData(0);
        let sumSquares = 0;
        const int16Array = new Int16Array(inputData.length);
        for (let i = 0; i < inputData.length; i++) {
          const s = Math.max(-1, Math.min(1, inputData[i]));
          sumSquares += s * s;
          int16Array[i] = s < 0 ? s * 0x8000 : s * 0x7fff;
        }
        const rms = Math.sqrt(sumSquares / Math.max(1, inputData.length));
        setAudioLevel(Math.min(1, rms * 4));
        webSocketService.sendBinary(int16Array.buffer);
      };

      source.connect(processor);
      processor.connect(audioContext.destination);
      webSocketService.startVoiceInput(conversationId);
      setCurrentVoiceState('listening');
    } catch (err) {
      const message = err instanceof Error ? err.message : 'Failed to access microphone';
      setError(message);
      onError?.(message);
      setCurrentVoiceState('idle');
    }
  }, [conversationId, onError, setCurrentVoiceState]);

  const stopListening = useCallback(() => {
    mediaStreamRef.current?.getTracks().forEach((track) => track.stop());
    mediaStreamRef.current = null;
    processorRef.current?.disconnect();
    processorRef.current = null;
    if (audioContextRef.current && audioContextRef.current.state !== 'closed') audioContextRef.current.close();
    audioContextRef.current = null;
    audioQueueRef.current = [];
    isPlayingRef.current = false;
    webSocketService.stopVoiceInput(conversationId);
    setCurrentVoiceState('idle');
    setTranscript('');
    setAudioLevel(0);
  }, [conversationId, setCurrentVoiceState]);

  useEffect(() => () => stopListening(), [stopListening]);

  return { voiceState, isListening, startListening, stopListening, transcript, error, audioLevel };
}
