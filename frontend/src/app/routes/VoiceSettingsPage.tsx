import { useState, useCallback, useEffect, useRef } from 'react';
import { useSettingsStore } from '../../stores';
import { Button, Input, Card } from '../../components/ui';
import { Mic, Volume2, Waves, Settings, CheckCircle, XCircle } from 'lucide-react';
import {
  listPiperVoices,
  synthesizeVoice,
  selectPiperVoice,
  getSharedSettings,
  updateSharedSettings,
  type PiperVoice,
} from '../../services/api';
import { webSocketService } from '../../services/websocket';

/** Debounce a callback so rapid events (keystrokes, slider ticks) collapse into one call. */
function useDebouncedCallback<T extends (...args: any[]) => void>(
  fn: T,
  delayMs: number
): T {
  const ref = useRef<ReturnType<typeof setTimeout> | null>(null);
  const fnRef = useRef(fn);
  fnRef.current = fn;

  useEffect(() => {
    return () => {
      if (ref.current) clearTimeout(ref.current);
    };
  }, []);

  return useCallback(
    (...args: Parameters<T>) => {
      if (ref.current) clearTimeout(ref.current);
      ref.current = setTimeout(() => fnRef.current(...args), delayMs);
    },
    [delayMs]
  ) as T;
}

export function VoiceSettingsPage() {
  const {
    wakeWord,
    setWakeWord,
    voiceSpeed,
    setVoiceSpeed,
    selectedVoice,
    setSelectedVoice,
    noiseSuppression,
    setNoiseSuppression,
    voiceEnabled,
    setVoiceEnabled,
    vadSensitivity,
    setVadSensitivity,
    responseDelay,
    setResponseDelay,
  } = useSettingsStore();

  const [testing, setTesting] = useState(false);
  const [testResult, setTestResult] = useState<{ type: 'success' | 'error' | 'info'; message: string } | null>(null);
  const [piperVoices, setPiperVoices] = useState<PiperVoice[]>([]);
  const [loadingVoices, setLoadingVoices] = useState(true);

  // Debounced persistence: typing/dragging fires many events; collapse them so
  // we send ONE /settings POST ~400ms after the user stops (regression B2).
  const persistWakeWord = useDebouncedCallback(
    (value: string) => updateSharedSettings({ wake_word: value }).catch(() => {}),
    400
  );
  const persistVoiceSpeed = useDebouncedCallback(
    (value: number) => updateSharedSettings({ voice_speed: value }).catch(() => {}),
    400
  );

  // Load real Piper voices discovered on the backend.
  useEffect(() => {
    let cancelled = false;
    listPiperVoices().then((voices) => {
      if (!cancelled) {
        setPiperVoices(voices);
        setLoadingVoices(false);
        // If the persisted selection is a stale fake id (default/professional/...),
        // switch to the active Piper voice.
        const known = voices.map((v) => v.id);
        if (voices.length > 0 && !known.includes(selectedVoice)) {
          const active = voices.find((v) => v.active);
          setSelectedVoice(active?.id ?? voices[0].id);
        }
      }
    });
    return () => {
      cancelled = true;
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  // Hydrate from the backend's shared settings (wake word / voice / speed), so
  // the web edits the SAME values the desktop + Android apps edit.
  useEffect(() => {
    let cancelled = false;
    getSharedSettings().then((s) => {
      if (cancelled || !s) return;
      if (s.wake_word) setWakeWord(s.wake_word);
      if (typeof s.voice_speed === 'number') setVoiceSpeed(s.voice_speed);
      if (s.voice) setSelectedVoice(s.voice);
    });
    return () => {
      cancelled = true;
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  // A voice list built from real Piper voices, plus a "system OS voice" fallback.
  const availableVoices = piperVoices.length
    ? piperVoices.map((v) => ({
        id: v.id,
        name: v.name,
        description: `Offline Piper voice (${v.quality}, ${v.language}${v.region ? '-' + v.region : ''})${v.has_config ? '' : ' — missing .onnx.json config'}`,
      }))
    : [{ id: 'system', name: 'System Voice', description: 'OS default TTS (pyttsx3) — no Piper model found' }];

  const handleSelectVoice = useCallback(
    (voiceId: string) => {
      setSelectedVoice(voiceId);
      // Persist on the backend (drives /voice/synthesize + the Beanie orb pipeline).
      selectPiperVoice(voiceId).catch(() => {});
      // Also update the shared settings store so desktop/Android see the change.
      updateSharedSettings({ voice: voiceId }).catch(() => {});
      // Best-effort: sync the running voice pipeline too.
      try {
        webSocketService.updateVoiceSettings({ selectedVoice: voiceId });
      } catch {
        /* WS not connected */
      }
    },
    [setSelectedVoice]
  );

  const handleTestWakeWord = useCallback(async () => {
    setTesting(true);
    setTestResult(null);

    try {
      // Request microphone access to verify permissions
      const stream = await navigator.mediaDevices.getUserMedia({ audio: true });
      // Immediately stop - we just needed to verify permissions
      stream.getTracks().forEach((track) => track.stop());
      setTestResult({
        type: 'success',
        message: `Microphone access granted. Wake word "${wakeWord}" is configured and ready.`,
      });
    } catch (err) {
      setTestResult({
        type: 'error',
        message: `Microphone access denied: ${err instanceof Error ? err.message : 'Permission denied'}`,
      });
    } finally {
      setTesting(false);
    }
  }, [wakeWord]);

  const handleTestVoice = useCallback(async () => {
    setTesting(true);
    setTestResult(null);

    const text = `Hello! This is Arena speaking with the ${selectedVoice} voice.`;

    // Prefer backend synthesis (Piper-first, pyttsx3 fallback) so the preview
    // matches what Beanie actually sounds like.
    const synth = await synthesizeVoice(text, selectedVoice);
    if (synth) {
      const audio = new Audio(synth.audio_url);
      audio.onended = () => {
        setTesting(false);
        setTestResult({
          type: 'success',
          message: `Voice test completed (engine: ${synth.engine ?? 'backend'}).`,
        });
      };
      audio.onerror = () => {
        setTesting(false);
        setTestResult({ type: 'error', message: 'Audio playback failed.' });
      };
      audio.play().catch(() => {
        setTesting(false);
        setTestResult({ type: 'error', message: 'Audio playback was blocked by the browser.' });
      });
      return;
    }

    // Fall back to the browser's speech synthesis.
    if ('speechSynthesis' in window) {
      const utterance = new SpeechSynthesisUtterance(text);
      utterance.rate = voiceSpeed;
      utterance.onend = () => {
        setTesting(false);
        setTestResult({
          type: 'success',
          message: 'Voice test completed (browser speech synthesis — backend unavailable).',
        });
      };
      utterance.onerror = (event) => {
        setTesting(false);
        setTestResult({ type: 'error', message: `Voice synthesis error: ${event.error}` });
      };
      window.speechSynthesis.speak(utterance);
    } else {
      setTesting(false);
      setTestResult({ type: 'error', message: 'No speech synthesis available (backend or browser).' });
    }
  }, [selectedVoice, voiceSpeed]);

  return (
    <div className="h-full overflow-y-auto bg-background-primary">
      <div className="max-w-4xl mx-auto px-6 py-8">
        {/* Header */}
        <div className="mb-8">
          <div className="flex items-center gap-3 mb-2">
            <Settings className="w-8 h-8 text-accent-primary" />
            <h1 className="text-3xl font-bold text-text-primary">Voice Settings</h1>
          </div>
          <p className="text-text-secondary">Configure voice interaction settings for Arena</p>
        </div>

        {/* Master Toggle */}
        <Card className="mb-6">
          <div className="flex items-center justify-between">
            <div className="flex items-center gap-3">
              <Mic className="w-6 h-6 text-accent-primary" />
              <div>
                <h3 className="text-lg font-semibold text-text-primary">Enable Voice</h3>
                <p className="text-sm text-text-secondary">Turn voice interaction on or off</p>
              </div>
            </div>
            <label className="relative inline-flex items-center cursor-pointer">
              <input
                type="checkbox"
                checked={voiceEnabled}
                onChange={(e) => setVoiceEnabled(e.target.checked)}
                className="sr-only peer"
              />
              <div className="relative w-11 h-6 bg-background-surface peer-focus:outline-none peer-focus:ring-2 peer-focus:ring-accent-primary rounded-full peer peer-checked:after:translate-x-full peer-checked:after:border-white after:content-[''] after:absolute after:top-[2px] after:left-[2px] after:bg-white after:border-gray-300 after:border after:rounded-full after:h-5 after:w-5 after:transition-all peer-checked:bg-accent-primary"></div>
            </label>
          </div>
        </Card>

        {/* Test result banner */}
        {testResult && (
          <div
            className={`mb-6 p-3 rounded-lg flex items-center gap-2 text-sm ${
              testResult.type === 'success'
                ? 'bg-green-50 text-green-800 border border-green-200'
                : testResult.type === 'error'
                ? 'bg-red-50 text-red-800 border border-red-200'
                : 'bg-blue-50 text-blue-800 border border-blue-200'
            }`}
          >
            {testResult.type === 'success' && <CheckCircle className="w-4 h-4" />}
            {testResult.type === 'error' && <XCircle className="w-4 h-4" />}
            <span>{testResult.message}</span>
          </div>
        )}

        {voiceEnabled && (
          <>
            {/* Wake Word Configuration */}
            <Card className="mb-6">
              <div className="flex items-center gap-3 mb-4">
                <Waves className="w-6 h-6 text-accent-primary" />
                <h3 className="text-lg font-semibold text-text-primary">Wake Word</h3>
              </div>
              <p className="text-sm text-text-secondary mb-4">
                Say this phrase to activate Arena's voice assistant
              </p>

              <div className="space-y-4">
                <div>
                  <label className="block text-sm font-medium text-text-secondary mb-2">
                    Wake Word Phrase
                  </label>
                  <Input
                    value={wakeWord}
                    onChange={(e) => {
                      setWakeWord(e.target.value);
                      persistWakeWord(e.target.value);
                    }}
                    placeholder="e.g., Hey Arena, Computer, Assistant"
                  />
                  <p className="text-xs text-text-muted mt-1">
                    Choose a phrase that's easy to say and unlikely to occur in normal conversation
                  </p>
                </div>

                <Button
                  onClick={handleTestWakeWord}
                  disabled={testing || !wakeWord.trim()}
                  variant="secondary"
                >
                  {testing ? 'Testing...' : 'Test Microphone Access'}
                </Button>
              </div>
            </Card>

            {/* Voice Selection */}
            <Card className="mb-6">
              <div className="flex items-center gap-3 mb-4">
                <Volume2 className="w-6 h-6 text-accent-primary" />
                <h3 className="text-lg font-semibold text-text-primary">Voice Selection</h3>
              </div>
              <p className="text-sm text-text-secondary mb-4">
                Choose the voice personality for Arena (offline Piper voices)
              </p>

              {loadingVoices ? (
                <p className="text-sm text-text-muted mb-4">Discovering Piper voices…</p>
              ) : null}

              <div className="space-y-3 mb-4">
                {availableVoices.map((voice) => (
                  <label
                    key={voice.id}
                    className={`flex items-start gap-3 p-4 rounded-lg border cursor-pointer transition-colors ${
                      selectedVoice === voice.id
                        ? 'border-accent-primary bg-accent-primary/10'
                        : 'border-background-surface hover:border-accent-primary/50'
                    }`}
                  >
                    <input
                      type="radio"
                      name="voice"
                      value={voice.id}
                      checked={selectedVoice === voice.id}
                      onChange={(e) => handleSelectVoice(e.target.value)}
                      className="mt-1"
                    />
                    <div className="flex-1">
                      <div className="font-medium text-text-primary">{voice.name}</div>
                      <div className="text-sm text-text-secondary">{voice.description}</div>
                    </div>
                  </label>
                ))}
              </div>

              <Button onClick={handleTestVoice} disabled={testing} variant="secondary">
                {testing ? 'Speaking...' : 'Test Voice (Play Audio)'}
              </Button>
            </Card>

            {/* Voice Speed */}
            <Card className="mb-6">
              <div className="flex items-center gap-3 mb-4">
                <Volume2 className="w-6 h-6 text-accent-primary" />
                <h3 className="text-lg font-semibold text-text-primary">Voice Speed</h3>
              </div>

              <div className="space-y-4">
                <div>
                  <div className="flex items-center justify-between mb-2">
                    <span className="text-sm text-text-secondary">Speed: {voiceSpeed.toFixed(1)}x</span>
                  </div>
                  <input
                    type="range"
                    min="0.5"
                    max="2"
                    step="0.1"
                    value={voiceSpeed}
                    onChange={(e) => {
                      const speed = parseFloat(e.target.value);
                      setVoiceSpeed(speed);
                      persistVoiceSpeed(speed);
                    }}
                    className="w-full h-2 bg-background-surface rounded-lg appearance-none cursor-pointer accent-accent-primary"
                  />
                  <div className="flex justify-between text-xs text-text-muted mt-1">
                    <span>0.5x (Slow)</span>
                    <span>1x (Normal)</span>
                    <span>2x (Fast)</span>
                  </div>
                </div>
              </div>
            </Card>

            {/* Noise Suppression */}
            <Card className="mb-6">
              <div className="flex items-center justify-between">
                <div className="flex items-center gap-3">
                  <Mic className="w-6 h-6 text-accent-primary" />
                  <div>
                    <h3 className="text-lg font-semibold text-text-primary">Noise Suppression</h3>
                    <p className="text-sm text-text-secondary">
                      Reduce background noise during voice input
                    </p>
                  </div>
                </div>
                <label className="relative inline-flex items-center cursor-pointer">
                  <input
                    type="checkbox"
                    checked={noiseSuppression}
                    onChange={(e) => setNoiseSuppression(e.target.checked)}
                    className="sr-only peer"
                  />
                  <div className="relative w-11 h-6 bg-background-surface peer-focus:outline-none peer-focus:ring-2 peer-focus:ring-accent-primary rounded-full peer peer-checked:after:translate-x-full peer-checked:after:border-white after:content-[''] after:absolute after:top-[2px] after:left-[2px] after:bg-white after:border-gray-300 after:border after:rounded-full after:h-5 after:w-5 after:transition-all peer-checked:bg-accent-primary"></div>
                </label>
              </div>
              {noiseSuppression && (
                <p className="text-xs text-text-muted mt-3">
                  Noise suppression is enabled. Background noise will be filtered during voice input.
                </p>
              )}
            </Card>

            {/* Advanced Settings - NOW WIRED */}
            <Card>
              <h3 className="text-lg font-semibold text-text-primary mb-4">Advanced Settings</h3>

              <div className="space-y-6">
                <div>
                  <div className="flex items-center justify-between mb-2">
                    <label className="text-sm font-medium text-text-secondary">
                      Voice Activity Detection Sensitivity
                    </label>
                    <span className="text-sm text-text-muted">{vadSensitivity}%</span>
                  </div>
                  <input
                    type="range"
                    min="0"
                    max="100"
                    value={vadSensitivity}
                    onChange={(e) => setVadSensitivity(Number(e.target.value))}
                    className="w-full h-2 bg-background-surface rounded-lg appearance-none cursor-pointer accent-accent-primary"
                  />
                  <div className="flex justify-between text-xs text-text-muted mt-1">
                    <span>Low (Less sensitive)</span>
                    <span>High (More sensitive)</span>
                  </div>
                  <p className="text-xs text-text-muted mt-2">
                    Adjust how sensitive Arena is to detecting speech
                  </p>
                </div>

                <div>
                  <div className="flex items-center justify-between mb-2">
                    <label className="text-sm font-medium text-text-secondary">Response Delay</label>
                    <span className="text-sm text-text-muted">{responseDelay}ms</span>
                  </div>
                  <input
                    type="range"
                    min="0"
                    max="2000"
                    step="100"
                    value={responseDelay}
                    onChange={(e) => setResponseDelay(Number(e.target.value))}
                    className="w-full h-2 bg-background-surface rounded-lg appearance-none cursor-pointer accent-accent-primary"
                  />
                  <div className="flex justify-between text-xs text-text-muted mt-1">
                    <span>0ms (Immediate)</span>
                    <span>2000ms (2 seconds)</span>
                  </div>
                  <p className="text-xs text-text-muted mt-2">
                    Delay before Arena starts speaking after you finish
                  </p>
                </div>
              </div>
            </Card>
          </>
        )}

        {!voiceEnabled && (
          <Card>
            <div className="text-center py-8">
              <Mic className="w-16 h-16 text-text-muted mx-auto mb-4" />
              <h3 className="text-lg font-semibold text-text-primary mb-2">
                Voice Interaction Disabled
              </h3>
              <p className="text-text-secondary mb-4">
                Enable voice interaction to configure wake word, voice selection, and other voice settings.
              </p>
              <Button onClick={() => setVoiceEnabled(true)}>Enable Voice</Button>
            </div>
          </Card>
        )}
      </div>
    </div>
  );
}
