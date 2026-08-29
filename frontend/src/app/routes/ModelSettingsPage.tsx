import { useState, useEffect } from 'react';
import { useNavigate } from 'react-router-dom';
import { Card } from '../../components/ui';
import { useModelSettingsStore, type ModelConfig } from '../../stores';
import { ArrowLeft, Brain, Mic, Volume2, Gauge, Zap, Cpu, Shield, RotateCcw, CheckCircle, XCircle, Layers } from 'lucide-react';
import { apiKeyHeader, apiUrl } from '../../services/api';

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
  runtime_applied?: boolean;
  datasets: string[];
  note?: string;
}

interface LoraEvaluationReport {
  report_id: string;
  adapter_name: string;
  adapter_model: string;
  skill_improvement: number | null;
  unrelated_regression: number | null;
  provider_model_identity_verified: boolean;
  deployment_eligible: boolean;
  runtime_applied: boolean;
  errors: string[];
}

interface TrainingCandidate {
  candidate_id: string;
  skill_name: string;
  prompt: string;
  response: string;
  action_type: string;
  status: 'pending' | 'approved' | 'rejected' | 'exported';
  source_type: string;
  verification_reason: string;
  evidence: string[];
  redactions: string[];
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
  const [trainingCandidates, setTrainingCandidates] = useState<TrainingCandidate[]>([]);
  const [candidateBusy, setCandidateBusy] = useState<string | null>(null);
  const [candidateMessage, setCandidateMessage] = useState('');
  const [correction, setCorrection] = useState({ skill_name: 'general', prompt: '', response: '' });
  const [evaluationForm, setEvaluationForm] = useState({
    adapter_name: '', base_model: '', adapter_model: '', skill_name: '', unrelated_skill_name: 'general',
  });
  const [evaluationReport, setEvaluationReport] = useState<LoraEvaluationReport | null>(null);
  const [evaluationBusy, setEvaluationBusy] = useState(false);
  const [evaluationMessage, setEvaluationMessage] = useState('');
  const [vlmStatus, setVlmStatus] = useState<{ available: boolean; model_id?: string; engine?: string; note?: string } | null>(null);

  useEffect(() => {
    let cancelled = false;
    const headers = apiKeyHeader();
    // Fetch LoRA status — include API key so it works when ARENA_API_KEY enabled (security)
    fetch(apiUrl('/loras/status'), { headers }).then((r) => r.ok ? r.json() : null).then((data) => {
      if (!cancelled && data) setLoraStatus(data);
    }).catch(() => {});
    fetch(apiUrl('/loras/training-candidates'), { headers }).then((r) => r.ok ? r.json() : null).then((data) => {
      if (!cancelled && Array.isArray(data?.candidates)) setTrainingCandidates(data.candidates);
    }).catch(() => {});
    // Fetch VLM status — include API key
    fetch(apiUrl('/vision/vlm-status'), { headers }).then((r) => r.ok ? r.json() : null).then((data) => {
      if (!cancelled && data) setVlmStatus(data);
    }).catch(() => {});
    return () => { cancelled = true; };
  }, []);

  const refreshCandidates = async () => {
    const response = await fetch(apiUrl('/loras/training-candidates'), { headers: apiKeyHeader() });
    if (response.ok) {
      const data = await response.json();
      if (Array.isArray(data?.candidates)) setTrainingCandidates(data.candidates);
    }
  };

  const decideCandidate = async (candidate: TrainingCandidate, approved: boolean) => {
    setCandidateBusy(candidate.candidate_id);
    try {
      if (approved) {
        const saved = await fetch(apiUrl(`/loras/training-candidates/${encodeURIComponent(candidate.candidate_id)}`), {
          method: 'PUT',
          headers: { 'Content-Type': 'application/json', ...apiKeyHeader() },
          body: JSON.stringify({
            prompt: candidate.prompt,
            response: candidate.response,
            skill_name: candidate.skill_name,
            note: 'Saved before approval in Model Settings',
          }),
        });
        if (!saved.ok) throw new Error('Could not save the exact pair before approval');
      }
      const response = await fetch(apiUrl(`/loras/training-candidates/${encodeURIComponent(candidate.candidate_id)}/decision`), {
        method: 'POST',
        headers: { 'Content-Type': 'application/json', ...apiKeyHeader() },
        body: JSON.stringify({ approved, note: approved ? 'Approved in Model Settings' : 'Rejected in Model Settings' }),
      });
      if (!response.ok) throw new Error('Could not update candidate');
      setCandidateMessage(approved ? 'Exact edited pair approved' : 'Candidate rejected');
      await refreshCandidates();
    } catch (error) {
      setCandidateMessage(error instanceof Error ? error.message : 'Could not update candidate');
    } finally {
      setCandidateBusy(null);
    }
  };

  const updateCandidate = (candidateId: string, patch: Partial<TrainingCandidate>) => {
    setTrainingCandidates((current) => current.map((item) =>
      item.candidate_id === candidateId ? { ...item, ...patch } : item
    ));
  };

  const saveCandidate = async (candidate: TrainingCandidate) => {
    setCandidateBusy(candidate.candidate_id);
    const response = await fetch(apiUrl(`/loras/training-candidates/${encodeURIComponent(candidate.candidate_id)}`), {
      method: 'PUT',
      headers: { 'Content-Type': 'application/json', ...apiKeyHeader() },
      body: JSON.stringify({
        prompt: candidate.prompt,
        response: candidate.response,
        skill_name: candidate.skill_name,
        note: 'Edited in Model Settings',
      }),
    });
    setCandidateMessage(response.ok ? 'Candidate edits saved; approval is still required' : 'Could not save candidate');
    await refreshCandidates();
    setCandidateBusy(null);
  };

  const exportSkill = async (skillName: string) => {
    setCandidateBusy(`export:${skillName}`);
    const response = await fetch(apiUrl('/loras/training-candidates/export'), {
      method: 'POST',
      headers: { 'Content-Type': 'application/json', ...apiKeyHeader() },
      body: JSON.stringify({ skill_name: skillName }),
    });
    const data = await response.json().catch(() => ({}));
    setCandidateMessage(response.ok && data?.success
      ? `Exported ${data.count} reviewed examples for ${skillName}`
      : data?.error || 'Dataset export failed');
    await refreshCandidates();
    setCandidateBusy(null);
  };

  const addOwnerCorrection = async () => {
    setCandidateBusy('owner-correction');
    try {
      const response = await fetch(apiUrl('/loras/training-candidates/owner-correction'), {
        method: 'POST',
        headers: { 'Content-Type': 'application/json', ...apiKeyHeader() },
        body: JSON.stringify(correction),
      });
      if (!response.ok) throw new Error('Could not add owner correction');
      setCorrection({ skill_name: correction.skill_name, prompt: '', response: '' });
      setCandidateMessage('Owner correction added to the review queue');
      await refreshCandidates();
    } catch (error) {
      setCandidateMessage(error instanceof Error ? error.message : 'Could not add correction');
    } finally {
      setCandidateBusy(null);
    }
  };

  const evaluateAdapter = async () => {
    setEvaluationBusy(true);
    setEvaluationMessage('');
    setEvaluationReport(null);
    try {
      const response = await fetch(apiUrl('/loras/evaluations'), {
        method: 'POST',
        headers: { 'Content-Type': 'application/json', ...apiKeyHeader() },
        body: JSON.stringify(evaluationForm),
      });
      const data = await response.json().catch(() => ({}));
      if (!data?.report) throw new Error(data?.error || data?.detail || 'Evaluation could not run');
      setEvaluationReport(data.report);
      setEvaluationMessage(data.report.deployment_eligible
        ? 'Evaluation passed. Nothing has been deployed; review the metrics and use the separate Deploy button.'
        : 'Evaluation did not pass deployment gates. Runtime remains unchanged.');
    } catch (error) {
      setEvaluationMessage(error instanceof Error ? error.message : 'Evaluation failed');
    } finally {
      setEvaluationBusy(false);
    }
  };

  const deployEvaluatedAdapter = async () => {
    if (!evaluationReport?.deployment_eligible) return;
    setEvaluationBusy(true);
    try {
      const response = await fetch(apiUrl('/loras/deploy-evaluated'), {
        method: 'POST',
        headers: { 'Content-Type': 'application/json', ...apiKeyHeader() },
        body: JSON.stringify({ report_id: evaluationReport.report_id }),
      });
      const data = await response.json().catch(() => ({}));
      if (!data?.runtime_applied) throw new Error(data?.error || 'Provider deployment was not verified');
      setEvaluationMessage('Provider model verified and applied for default requests in this process.');
      setEvaluationReport((current) => current ? { ...current, runtime_applied: true } : current);
      const status = await fetch(apiUrl('/loras/status'), { headers: apiKeyHeader() });
      if (status.ok) setLoraStatus(await status.json());
    } catch (error) {
      setEvaluationMessage(error instanceof Error ? error.message : 'Deployment failed');
    } finally {
      setEvaluationBusy(false);
    }
  };

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
            LoRA provides skill-specific adaptation tooling without modifying the base weights. Arena can build reviewed datasets and train PEFT adapters, but behavior changes only after the external inference provider loads or merges an adapter and held-out evaluation confirms improvement. Adapters live in <code>data/loras/</code>.
          </p>
          <Card className="space-y-4">
            {loraStatus ? (
              <>
                <div className="text-sm text-text-primary">
                  <span className="font-medium">Selected:</span> {loraStatus.active || '(none — base model)'}
                  {loraStatus.active && !loraStatus.runtime_applied && (
                    <span className="text-xs text-amber-600 ml-2">not loaded by inference runtime</span>
                  )}
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
                              fetch(apiUrl('/loras/activate'), { method: 'POST', headers: { 'Content-Type': 'application/json', ...apiKeyHeader() }, body: JSON.stringify({ adapter_name: a.name }) })
                                .then(() => fetch(apiUrl('/loras/status'), { headers: apiKeyHeader() }).then((r) => r.json()).then(setLoraStatus));
                            }}
                            className="px-2 py-1 text-xs bg-accent-primary text-white rounded"
                          >
                            Select metadata only
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
                      fetch(apiUrl('/loras/deactivate'), { method: 'POST', headers: apiKeyHeader() }).then(() => fetch(apiUrl('/loras/status'), { headers: apiKeyHeader() }).then((r) => r.json()).then(setLoraStatus));
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

            <div className="border-t border-border pt-4 space-y-3">
              <div>
                <h3 className="font-medium text-text-primary">Held-out Provider Evaluation</h3>
                <p className="text-xs text-text-muted mt-1">
                  Evaluation calls two distinct provider model identifiers against the reviewed skill holdout and an unrelated-domain holdout (at least three examples in each). It records scores and model identity, but does not deploy anything. Deployment is a separate owner action and is cleared on restart until re-verified.
                </p>
              </div>
              <div className="grid grid-cols-1 md:grid-cols-2 gap-2">
                {([
                  ['adapter_name', 'Adapter folder'], ['base_model', 'Provider base model ID'],
                  ['adapter_model', 'Provider adapter/merged model ID'], ['skill_name', 'Skill dataset'],
                  ['unrelated_skill_name', 'Unrelated regression dataset'],
                ] as const).map(([field, placeholder]) => (
                  <input
                    key={field}
                    value={evaluationForm[field]}
                    onChange={(event) => setEvaluationForm((current) => ({ ...current, [field]: event.target.value }))}
                    placeholder={placeholder}
                    className="px-3 py-2 text-sm bg-background-surface border border-border rounded text-text-primary"
                  />
                ))}
              </div>
              <button
                onClick={evaluateAdapter}
                disabled={evaluationBusy || !evaluationForm.adapter_name || !evaluationForm.base_model || !evaluationForm.adapter_model || !evaluationForm.skill_name || !evaluationForm.unrelated_skill_name}
                className="px-3 py-1.5 text-sm bg-background-surface border border-border text-text-primary rounded disabled:opacity-50"
              >
                {evaluationBusy ? 'Working…' : 'Evaluate only (no deployment)'}
              </button>
              {evaluationMessage && <p className="text-xs text-text-secondary">{evaluationMessage}</p>}
              {evaluationReport && (
                <div className="rounded border border-border p-3 text-xs text-text-secondary space-y-2">
                  <p>Skill improvement: <strong>{evaluationReport.skill_improvement ?? 'unknown'}</strong> · unrelated regression: <strong>{evaluationReport.unrelated_regression ?? 'unknown'}</strong></p>
                  <p>Provider identity verified: {evaluationReport.provider_model_identity_verified ? 'yes' : 'no'} · deployment eligible: {evaluationReport.deployment_eligible ? 'yes' : 'no'}</p>
                  {evaluationReport.errors.length > 0 && <p className="text-red-600">{evaluationReport.errors.join('; ')}</p>}
                  {evaluationReport.deployment_eligible && !evaluationReport.runtime_applied && (
                    <button
                      onClick={deployEvaluatedAdapter}
                      disabled={evaluationBusy}
                      className="px-3 py-1.5 text-sm bg-accent-primary text-white rounded disabled:opacity-50"
                    >
                      Deploy this evaluated provider model
                    </button>
                  )}
                  {evaluationReport.runtime_applied && <p className="text-green-600">Applied and provider-probed for this process.</p>}
                </div>
              )}
            </div>

            <div className="border-t border-border pt-4 space-y-3">
              <div>
                <h3 className="font-medium text-text-primary">Reviewed Training Examples</h3>
                <p className="text-xs text-text-muted mt-1">
                  Verified outcomes only propose redacted candidates. Nothing enters a dataset until you edit and approve it. At least 5 approved examples are required so export includes a held-out evaluation split.
                </p>
              </div>
              {candidateMessage && <p className="text-xs text-text-secondary">{candidateMessage}</p>}
              <div className="rounded border border-border p-3 space-y-2">
                <h4 className="text-sm font-medium text-text-primary">Add an owner correction</h4>
                <input
                  value={correction.skill_name}
                  onChange={(event) => setCorrection({ ...correction, skill_name: event.target.value })}
                  className="w-full px-3 py-2 rounded border border-border bg-background-primary text-xs"
                  placeholder="Skill name"
                />
                <textarea
                  value={correction.prompt}
                  onChange={(event) => setCorrection({ ...correction, prompt: event.target.value })}
                  className="w-full min-h-16 px-3 py-2 rounded border border-border bg-background-primary text-xs"
                  placeholder="Prompt or situation"
                />
                <textarea
                  value={correction.response}
                  onChange={(event) => setCorrection({ ...correction, response: event.target.value })}
                  className="w-full min-h-20 px-3 py-2 rounded border border-border bg-background-primary text-xs"
                  placeholder="Preferred response"
                />
                <button
                  disabled={candidateBusy === 'owner-correction' || correction.prompt.trim().length < 3 || correction.response.trim().length < 3}
                  onClick={addOwnerCorrection}
                  className="px-3 py-1.5 text-xs bg-background-secondary border border-border rounded disabled:opacity-50"
                >
                  Add to review queue
                </button>
              </div>
              {trainingCandidates.filter((item) => item.status === 'pending').length === 0 ? (
                <p className="text-xs text-text-muted">No candidates are waiting for review.</p>
              ) : trainingCandidates.filter((item) => item.status === 'pending').map((candidate) => (
                <div key={candidate.candidate_id} className="rounded border border-border bg-background-surface p-3 space-y-2">
                  <div className="flex items-center justify-between gap-2">
                    <span className="text-xs font-medium text-text-primary">{candidate.action_type} · {candidate.source_type}</span>
                    <span className="text-xs text-text-muted">{candidate.candidate_id}</span>
                  </div>
                  <input
                    value={candidate.skill_name}
                    onChange={(event) => updateCandidate(candidate.candidate_id, { skill_name: event.target.value })}
                    className="w-full px-3 py-2 rounded border border-border bg-background-primary text-xs"
                    aria-label="Training skill"
                  />
                  <textarea
                    value={candidate.prompt}
                    onChange={(event) => updateCandidate(candidate.candidate_id, { prompt: event.target.value })}
                    className="w-full min-h-20 px-3 py-2 rounded border border-border bg-background-primary text-xs"
                    aria-label="Training prompt"
                  />
                  <textarea
                    value={candidate.response}
                    onChange={(event) => updateCandidate(candidate.candidate_id, { response: event.target.value })}
                    className="w-full min-h-24 px-3 py-2 rounded border border-border bg-background-primary text-xs"
                    aria-label="Training response"
                  />
                  <p className="text-xs text-text-muted">Evidence: {candidate.verification_reason || candidate.evidence.join(', ')}</p>
                  {candidate.redactions.length > 0 && (
                    <p className="text-xs text-amber-600">Redacted: {candidate.redactions.join(', ')}</p>
                  )}
                  <div className="flex flex-wrap gap-2">
                    <button
                      disabled={candidateBusy === candidate.candidate_id}
                      onClick={() => saveCandidate(candidate)}
                      className="px-2 py-1 text-xs border border-border rounded"
                    >
                      Save edits
                    </button>
                    <button
                      disabled={candidateBusy === candidate.candidate_id}
                      onClick={() => decideCandidate(candidate, false)}
                      className="px-2 py-1 text-xs bg-red-600 text-white rounded"
                    >
                      Reject
                    </button>
                    <button
                      disabled={candidateBusy === candidate.candidate_id}
                      onClick={() => decideCandidate(candidate, true)}
                      className="px-2 py-1 text-xs bg-green-600 text-white rounded"
                    >
                      Approve exact pair
                    </button>
                  </div>
                </div>
              ))}
              {[...new Set(
                trainingCandidates
                  .filter((item) => item.status === 'approved')
                  .map((item) => item.skill_name)
              )].map((skill) => (
                <button
                  key={skill}
                  disabled={candidateBusy === `export:${skill}`}
                  onClick={() => exportSkill(skill)}
                  className="mr-2 px-3 py-1.5 text-xs bg-accent-primary text-white rounded"
                >
                  Export approved “{skill}” dataset
                </button>
              ))}
            </div>
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
