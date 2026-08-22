import { useState, useEffect } from 'react';
import { useNavigate } from 'react-router-dom';
import { Card } from '../../components/ui';
import { useModelSettingsStore, type ModelConfig } from '../../stores';
import { ArrowLeft, Brain, Mic, Volume2, Gauge, Zap, Cpu, Shield, RotateCcw, CheckCircle, XCircle, Layers } from 'lucide-react';
import { getSharedSettings } from '../../services/api';

interface LoraAdapter {
  name: string;
  base_model: string;
  size_mb: number;
  training_info?: { skill_name?: string };
}

interface LoraStatus {
  adapters_count: number;
  adapters: LoraAdapter[];
  active?: string;
  datasets: string[];
  note?: string;
}

export function ModelSettingsPage() {
  const navigate = useNavigate();
  const {
    llmModels,
    selectedLLM,
    sttModels,
    selectedSTT,
    ttsModels,
    selectedTTS,
    confidenceThresholds,
    setSelectedLLM,
    setSelectedSTT,
    setSelectedTTS,
    toggleModel,
    setConfidenceThreshold,
    resetConfidenceThresholds,
    validateModelConfig,
  } = useModelSettingsStore();

  const [testingModel, setTestingModel] = useState<string | null>(null);
  const [testResults, setTestResults] = useState<Record<string, ReturnType<typeof validateModelConfig>>>({});
  const [loraStatus, setLoraStatus] = useState<LoraStatus | null>(null);
  const [vlmStatus, setVlmStatus] = useState<{ available: boolean; model_id?: string; engine?: string; note?: string } | null>(null);

  useEffect(() => {
    let cancelled = false;
    // Fetch LoRA status
    fetch('/loras/status').then((r) => r.ok ? r.json() : null).then((data) => {
      if (!cancelled && data) setLoraStatus(data);
    }).catch(() => {});
    // Fetch VLM status
    fetch('/vision/vlm-status').then((r) => r.ok ? r.json() : null).then((data) => {
      if (!cancelled && data) setVlmStatus(data);
    }).catch(() => {});
    return () => { cancelled = true; };
  }, []);

  const handleTestModel = async (type: 'llm' | 'stt' | 'tts', model: ModelConfig) => {
    setTestingModel(model.id);

    // Run validation checks
    const result = validateModelConfig(type, model.id);
    
    // Simulate backend connectivity check
    await new Promise((resolve) => setTimeout(resolve, 800));
    
    setTestResults((prev) => ({ ...prev, [model.id]: result }));
    setTestingModel(null);
  };

  const renderPerformanceBar = (value: number, label: string, icon: React.ReactNode) => (
    <div className="flex items-center gap-2 text-xs text-text-secondary">
      {icon}
      <span className="w-16">{label}</span>
      <div className="flex-1 bg-background-surface rounded-full h-2">
        <div
          className="bg-accent-primary h-2 rounded-full transition-all"
          style={{ width: `${value * 10}%` }}
        />
      </div>
      <span className="w-8 text-right">{value}/10</span>
    </div>
  );

  const renderModelCard = (
    type: 'llm' | 'stt' | 'tts',
    model: ModelConfig,
    isSelected: boolean,
    onSelect: () => void
  ) => {
    const testResult = testResults[model.id];
    const isTesting = testingModel === model.id;

    return (
      <Card
        key={model.id}
        className={`cursor-pointer transition-all ${
          isSelected
            ? 'border-accent-primary bg-accent-primary/10'
            : 'hover:border-accent-primary/50'
        } ${!model.enabled ? 'opacity-50' : ''}`}
        onClick={onSelect}
      >
        <div className="space-y-3">
          {/* Header */}
          <div className="flex items-start justify-between">
            <div className="flex-1">
              <div className="flex items-center gap-2">
                <h3 className="text-lg font-semibold text-text-primary">{model.name}</h3>
                {isSelected && (
                  <span className="px-2 py-0.5 text-xs font-medium bg-accent-primary text-white rounded">
                    Selected
                  </span>
                )}
              </div>
              <p className="text-sm text-text-secondary mt-1">{model.description}</p>
            </div>

            {/* Enable/Disable toggle */}
            <label className="relative inline-flex items-center cursor-pointer">
              <input
                type="checkbox"
                checked={model.enabled}
                onChange={(e) => {
                  e.stopPropagation();
                  toggleModel(type, model.id);
                }}
                className="sr-only peer"
              />
              <div className="relative w-11 h-6 bg-background-surface peer-focus:outline-none peer-focus:ring-2 peer-focus:ring-accent-primary rounded-full peer peer-checked:after:translate-x-full peer-checked:after:border-white after:content-[''] after:absolute after:top-[2px] after:left-[2px] after:bg-white after:border-gray-300 after:border after:rounded-full after:h-5 after:w-5 after:transition-all peer-checked:bg-accent-primary"></div>
            </label>
          </div>

          {/* Model info */}
          <div className="flex items-center gap-4 text-xs text-text-muted">
            <div className="flex items-center gap-1">
              <Cpu className="w-3 h-3" />
              <span>{model.size}</span>
            </div>
            <div className="flex items-center gap-1">
              <Cpu className="w-3 h-3" />
              <span>{model.performance.memoryUsage}</span>
            </div>
          </div>

          {/* Performance metrics */}
          <div className="space-y-2">
            {renderPerformanceBar(model.performance.speed, 'Speed', <Zap className="w-3 h-3" />)}
            {renderPerformanceBar(model.performance.quality, 'Quality', <Gauge className="w-3 h-3" />)}
          </div>

          {/* Test button and results */}
          <div className="space-y-2">
            <button
              onClick={(e) => {
                e.stopPropagation();
                handleTestModel(type, model);
              }}
              disabled={isTesting}
              className="w-full px-3 py-2 text-sm font-medium text-accent-primary bg-background-surface hover:bg-background-surface/80 rounded transition-colors disabled:opacity-50"
            >
              {isTesting ? 'Testing...' : 'Validate Model'}
            </button>

            {testResult && (
              <div className="bg-background-surface rounded p-3 space-y-1">
                {testResult.checks.map((check, idx) => (
                  <div key={idx} className="flex items-center gap-2 text-xs">
                    {check.passed ? (
                      <CheckCircle className="w-3 h-3 text-green-500 flex-shrink-0" />
                    ) : (
                      <XCircle className="w-3 h-3 text-red-500 flex-shrink-0" />
                    )}
                    <span className="text-text-secondary">
                      {check.name}: {check.detail}
                    </span>
                  </div>
                ))}
              </div>
            )}
          </div>
        </div>
      </Card>
    );
  };

  return (
    <div className="h-full overflow-y-auto bg-background-primary">
      <div className="max-w-4xl mx-auto px-6 py-8">
        {/* Header */}
        <div className="mb-8">
          <button
            onClick={() => navigate('/settings')}
            className="flex items-center gap-2 text-text-secondary hover:text-text-primary mb-4"
          >
            <ArrowLeft className="w-5 h-5" />
            <span>Back to Settings</span>
          </button>
          <h1 className="text-3xl font-bold text-text-primary">Model Configuration</h1>
          <p className="text-text-secondary mt-2">
            Select and configure AI models for Arena
          </p>
        </div>

        {/* LLM Models */}
        <section className="mb-8">
          <div className="flex items-center gap-3 mb-4">
            <Brain className="w-6 h-6 text-accent-primary" />
            <h2 className="text-2xl font-semibold text-text-primary">Language Models (LLM)</h2>
          </div>
          <p className="text-sm text-text-secondary mb-4">
            Select the language model for reasoning and conversation
          </p>
          <div className="space-y-4">
            {llmModels.map((model) =>
              renderModelCard('llm', model, selectedLLM === model.id, () =>
                setSelectedLLM(model.id)
              )
            )}
          </div>
        </section>

        {/* STT Models */}
        <section className="mb-8">
          <div className="flex items-center gap-3 mb-4">
            <Mic className="w-6 h-6 text-accent-primary" />
            <h2 className="text-2xl font-semibold text-text-primary">Speech-to-Text (STT)</h2>
          </div>
          <p className="text-sm text-text-secondary mb-4">
            Select the speech-to-text model for voice input
          </p>
          <div className="space-y-4">
            {sttModels.map((model) =>
              renderModelCard('stt', model, selectedSTT === model.id, () =>
                setSelectedSTT(model.id)
              )
            )}
          </div>
        </section>

        {/* TTS Models */}
        <section className="mb-8">
          <div className="flex items-center gap-3 mb-4">
            <Volume2 className="w-6 h-6 text-accent-primary" />
            <h2 className="text-2xl font-semibold text-text-primary">Text-to-Speech (TTS)</h2>
          </div>
          <p className="text-sm text-text-secondary mb-4">
            Select the text-to-speech model for voice output
          </p>
          <div className="space-y-4">
            {ttsModels.map((model) =>
              renderModelCard('tts', model, selectedTTS === model.id, () =>
                setSelectedTTS(model.id)
              )
            )}
          </div>
        </section>

        {/* LoRA Continual Learning (P2 AGI) */}
        <section className="mb-8">
          <div className="flex items-center gap-3 mb-4">
            <Layers className="w-6 h-6 text-accent-primary" />
            <h2 className="text-2xl font-semibold text-text-primary">Continual Learning — LoRA Adapters</h2>
          </div>
          <p className="text-sm text-text-secondary mb-4">
            LoRA enables the agent to get better at tasks it has seen before without catastrophic forgetting — a key human intelligence capability. Adapters live in <code>data/loras/</code> and are discovered automatically.
          </p>
          <Card className="space-y-4">
            {loraStatus ? (
              <>
                <div className="text-sm text-text-primary">
                  <span className="font-medium">Active:</span> {loraStatus.active || '(none — base model)'}
                </div>
                <div className="text-sm text-text-secondary">
                  {loraStatus.adapters_count} adapter(s) — datasets: {loraStatus.datasets.join(', ') || '(none)'}
                </div>
                {loraStatus.adapters.length ? (
                  <ul className="space-y-2">
                    {loraStatus.adapters.map((a) => (
                      <li key={a.name} className="flex items-center justify-between p-2 bg-background-surface rounded">
                        <div>
                          <span className="font-medium">{a.name}</span>
                          <span className="text-xs text-text-muted ml-2">{a.base_model} — {a.size_mb} MB {a.training_info?.skill_name ? `(skill: ${a.training_info.skill_name})` : ''}</span>
                        </div>
                        <div className="flex gap-2">
                          <button
                            onClick={() => {
                              fetch('/loras/activate', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ adapter_name: a.name }) })
                                .then(() => fetch('/loras/status').then((r) => r.json()).then(setLoraStatus));
                            }}
                            className="px-2 py-1 text-xs bg-accent-primary text-white rounded"
                          >
                            Activate
                          </button>
                        </div>
                      </li>
                    ))}
                  </ul>
                ) : (
                  <p className="text-xs text-text-muted">No adapters yet. Prepare dataset via POST /loras/dataset then POST /loras/train-job, or run scripts/train_lora.py</p>
                )}
                {loraStatus.active && (
                  <button
                    onClick={() => {
                      fetch('/loras/deactivate', { method: 'POST' }).then(() => fetch('/loras/status').then((r) => r.json()).then(setLoraStatus));
                    }}
                    className="px-3 py-1.5 text-sm bg-background-surface text-text-secondary rounded"
                  >
                    Deactivate (use base model)
                  </button>
                )}
                {loraStatus.note && <p className="text-xs text-text-muted">{loraStatus.note}</p>}
              </>
            ) : (
              <p className="text-xs text-text-muted">Loading LoRA status… (backend may be offline)</p>
            )}
          </Card>
        </section>

        {/* VLM Status (P2 AGI: true visual understanding) */}
        <section className="mb-8">
          <div className="flex items-center gap-3 mb-4">
            <Brain className="w-6 h-6 text-accent-primary" />
            <h2 className="text-2xl font-semibold text-text-primary">Vision — VLM Status</h2>
          </div>
          <p className="text-sm text-text-secondary mb-4">
            True VLM (Moondream2 / Llava-Phi) with OCR+LLM fallback. RX 580 8GB can hold Moondream2 1.8B Q4 alongside Qwen 3B fast. Honest status.
          </p>
          <Card className="space-y-2">
            {vlmStatus ? (
              <>
                <div className="text-sm">
                  <span className="font-medium">Available:</span> {vlmStatus.available ? '✅ Yes' : '❌ No (fallback OCR+LLM)'}
                </div>
                <div className="text-xs text-text-muted">Engine: {vlmStatus.engine} — Model: {vlmStatus.model_id}</div>
                {vlmStatus.note && <p className="text-xs text-text-muted">{vlmStatus.note}</p>}
              </>
            ) : (
              <p className="text-xs text-text-muted">Loading VLM status…</p>
            )}
          </Card>
        </section>

        {/* Confidence Thresholds */}
        <section className="mb-8">
          <div className="flex items-center justify-between mb-4">
            <div className="flex items-center gap-3">
              <Shield className="w-6 h-6 text-accent-primary" />
              <h2 className="text-2xl font-semibold text-text-primary">Confidence Thresholds</h2>
            </div>
            <button
              onClick={resetConfidenceThresholds}
              className="flex items-center gap-2 px-3 py-1.5 text-sm text-text-secondary hover:text-text-primary bg-background-surface hover:bg-background-surface/80 rounded transition-colors"
            >
              <RotateCcw className="w-4 h-4" />
              <span>Reset</span>
            </button>
          </div>
          <p className="text-sm text-text-secondary mb-4">
            Configure minimum confidence levels for AI model outputs
          </p>
          <Card className="space-y-6">
            <div>
              <div className="flex items-center justify-between mb-2">
                <label className="text-sm font-medium text-text-primary">
                  Speech-to-Text Minimum Confidence
                </label>
                <span className="text-sm text-text-muted">
                  {Math.round(confidenceThresholds.sttMinConfidence * 100)}%
                </span>
              </div>
              <input
                type="range"
                min="0"
                max="100"
                value={confidenceThresholds.sttMinConfidence * 100}
                onChange={(e) =>
                  setConfidenceThreshold('sttMinConfidence', Number(e.target.value) / 100)
                }
                className="w-full h-2 bg-background-surface rounded-lg appearance-none cursor-pointer accent-accent-primary"
              />
              <p className="text-xs text-text-muted mt-1">
                Reject transcriptions below this confidence score
              </p>
            </div>

            <div>
              <div className="flex items-center justify-between mb-2">
                <label className="text-sm font-medium text-text-primary">
                  Intent Detection Minimum Confidence
                </label>
                <span className="text-sm text-text-muted">
                  {Math.round(confidenceThresholds.intentMinConfidence * 100)}%
                </span>
              </div>
              <input
                type="range"
                min="0"
                max="100"
                value={confidenceThresholds.intentMinConfidence * 100}
                onChange={(e) =>
                  setConfidenceThreshold('intentMinConfidence', Number(e.target.value) / 100)
                }
                className="w-full h-2 bg-background-surface rounded-lg appearance-none cursor-pointer accent-accent-primary"
              />
              <p className="text-xs text-text-muted mt-1">
                Minimum confidence for intent classification results
              </p>
            </div>

            <div>
              <div className="flex items-center justify-between mb-2">
                <label className="text-sm font-medium text-text-primary">
                  Entity Extraction Minimum Confidence
                </label>
                <span className="text-sm text-text-muted">
                  {Math.round(confidenceThresholds.entityMinConfidence * 100)}%
                </span>
              </div>
              <input
                type="range"
                min="0"
                max="100"
                value={confidenceThresholds.entityMinConfidence * 100}
                onChange={(e) =>
                  setConfidenceThreshold('entityMinConfidence', Number(e.target.value) / 100)
                }
                className="w-full h-2 bg-background-surface rounded-lg appearance-none cursor-pointer accent-accent-primary"
              />
              <p className="text-xs text-text-muted mt-1">
                Minimum confidence for named entity recognition
              </p>
            </div>
          </Card>
        </section>
      </div>
    </div>
  );
}
