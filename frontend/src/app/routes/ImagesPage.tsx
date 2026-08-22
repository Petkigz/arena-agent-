import { useState, useRef } from 'react';
import { Image as ImageIcon, Monitor, Camera, Upload, Loader2, ScanText } from 'lucide-react';
import { Button } from '../../components/ui/Button';
import {
  captureScreen,
  captureAndAnalyzeScreen,
  analyzeImage,
  uploadImageForVision,
  resolveStaticUrl,
  type VisionResult,
} from '../../services/api';

/**
 * Images / Vision — desktop sight (native screen capture) + OCR + image analysis,
 * mirroring the desktop (Qt) and Android (Compose) Vision pages. The "Capture &
 * analyze" button asks the backend (running on the same PC) to grab and understand
 * its own screen via /vision/capture-and-analyze; "Choose image" uploads a local
 * file via /mobile/camera and analyses it via /vision/analyze.
 */
export function ImagesPage() {
  const [promptFocus, setPromptFocus] = useState('');
  const [busy, setBusy] = useState(false);
  const [busyLabel, setBusyLabel] = useState('');
  const [error, setError] = useState<string | null>(null);
  const [previewUrl, setPreviewUrl] = useState<string | null>(null);
  const [ocrText, setOcrText] = useState('');
  const [analysisText, setAnalysisText] = useState('');
  const fileInputRef = useRef<HTMLInputElement>(null);

  const applyResult = (res: VisionResult) => {
    setBusy(false);
    setBusyLabel('');
    if (!res.success) {
      setError(res.error || 'Analysis failed');
      return;
    }
    setError(null);
    setOcrText(res.ocr_text || res.extracted_text || '(no OCR text)');
    if (res.screen_changed === false && res.note) {
      setAnalysisText(res.note);
    } else {
      setAnalysisText(res.ai_analysis || res.analysis || '(no analysis)');
    }
    const url = res.image_url || res.file_url;
    if (url) {
      setPreviewUrl(resolveStaticUrl(url));
    }
  };

  const handleCapture = async () => {
    setBusy(true);
    setBusyLabel('Capturing the desktop screen…');
    setError(null);
    try {
      const res = await captureScreen();
      if (!res.success) {
        setBusy(false);
        setBusyLabel('');
        setError(res.error || 'Capture failed');
        return;
      }
      setOcrText('');
      setAnalysisText('Captured — press "Capture & analyze" to read it.');
      const url = res.image_url || res.file_url;
      if (url) setPreviewUrl(resolveStaticUrl(url));
      setBusy(false);
      setBusyLabel('');
    } catch (e) {
      setBusy(false);
      setBusyLabel('');
      setError(String(e));
    }
  };

  const handleCaptureAndAnalyze = async () => {
    setBusy(true);
    setBusyLabel('Beanie is looking at the desktop screen…');
    setError(null);
    setOcrText('');
    setAnalysisText('');
    try {
      applyResult(await captureAndAnalyzeScreen(promptFocus));
    } catch (e) {
      setBusy(false);
      setBusyLabel('');
      setError(String(e));
    }
  };

  const handleFileChosen = async (file: File | null) => {
    if (!file) return;
    setBusy(true);
    setBusyLabel('Uploading and analysing…');
    setError(null);
    setOcrText('');
    setAnalysisText('');
    // Show a local preview immediately.
    setPreviewUrl(URL.createObjectURL(file));
    try {
      const upload = await uploadImageForVision(file);
      if (!upload.success || !upload.file_path) {
        setBusy(false);
        setBusyLabel('');
        setError(upload.error || 'Upload failed — is the backend online?');
        return;
      }
      const result = await analyzeImage(upload.file_path, promptFocus);
      // Prefer the backend's own file URL for the preview so it persists.
      const backendUrl = upload.file_url || result.image_url || result.file_url;
      applyResult({ ...result, image_url: backendUrl || result.image_url });
    } catch (e) {
      setBusy(false);
      setBusyLabel('');
      setError(String(e));
    }
  };

  return (
    <div className="h-full flex flex-col bg-background-primary">
      {/* Header */}
      <div className="flex-shrink-0 px-6 py-4 border-b border-border">
        <h1 className="text-2xl font-bold text-text-primary">Images / Vision</h1>
        <p className="text-text-secondary mt-1">
          Desktop sight, OCR, and image analysis — powered by the backend&apos;s vision pipeline.
        </p>
      </div>

      {/* Content */}
      <div className="flex-1 overflow-y-auto px-6 py-6 space-y-6">
        {/* Desktop sight */}
        <section>
          <h2 className="text-lg font-semibold text-text-primary mb-3 flex items-center gap-2">
            <Monitor className="w-5 h-5 text-text-muted" /> Desktop sight
          </h2>

          <input
            type="text"
            value={promptFocus}
            onChange={(e) => setPromptFocus(e.target.value)}
            placeholder='What should I focus on? (optional, e.g. "the error dialog")'
            className="w-full mb-3 px-3 py-2 rounded-lg bg-background-surface text-text-primary border border-background-surface focus:outline-none focus:ring-2 focus:ring-accent-primary"
          />

          <div className="flex flex-wrap items-center gap-3">
            <Button variant="secondary" onClick={handleCapture} disabled={busy}>
              <Camera className="w-4 h-4 mr-2" />
              Capture screen
            </Button>
            <Button variant="primary" onClick={handleCaptureAndAnalyze} disabled={busy}>
              <ScanText className="w-4 h-4 mr-2" />
              Capture &amp; analyze
            </Button>
          </div>
        </section>

        {/* Image preview */}
        <section>
          <div className="min-h-[200px] rounded-lg bg-background-secondary border border-background-surface flex items-center justify-center overflow-hidden">
            {previewUrl ? (
              <img
                src={previewUrl}
                alt="Captured or uploaded preview"
                className="max-w-full max-h-[360px] object-contain"
              />
            ) : (
              <div className="text-text-muted text-sm flex flex-col items-center gap-2 py-10">
                <ImageIcon className="w-10 h-10" />
                <span>No image captured yet</span>
              </div>
            )}
          </div>
        </section>

        {/* Analyze an image file */}
        <section>
          <h2 className="text-lg font-semibold text-text-primary mb-3 flex items-center gap-2">
            <Upload className="w-5 h-5 text-text-muted" /> Analyze an image file
          </h2>
          <input
            ref={fileInputRef}
            type="file"
            accept="image/*"
            className="hidden"
            onChange={(e) => {
              const file = e.target.files?.[0] ?? null;
              handleFileChosen(file);
              e.target.value = '';
            }}
          />
          <Button variant="secondary" onClick={() => fileInputRef.current?.click()} disabled={busy}>
            <Upload className="w-4 h-4 mr-2" />
            Choose image…
          </Button>
        </section>

        {/* Busy / error */}
        {busy && (
          <div className="flex items-center gap-2 text-text-secondary text-sm">
            <Loader2 className="w-4 h-4 animate-spin" />
            <span>{busyLabel}</span>
          </div>
        )}
        {error && (
          <div className="p-4 bg-accent-error/10 border border-accent-error rounded">
            <p className="text-sm text-accent-error">⚠ {error}</p>
          </div>
        )}

        {/* OCR text */}
        <section>
          <h3 className="text-sm font-medium text-text-muted mb-2">OCR text</h3>
          <pre className="whitespace-pre-wrap rounded-lg bg-background-secondary border border-background-surface p-4 text-sm text-text-primary min-h-[48px]">
            {ocrText || '(nothing yet)'}
          </pre>
        </section>

        {/* AI analysis */}
        <section>
          <h3 className="text-sm font-medium text-text-muted mb-2">AI analysis</h3>
          <pre className="whitespace-pre-wrap rounded-lg bg-background-secondary border border-background-surface p-4 text-sm text-text-primary min-h-[48px]">
            {analysisText || '(nothing yet)'}
          </pre>
        </section>
      </div>
    </div>
  );
}
