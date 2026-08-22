import { useState, useRef, useEffect } from 'react';
import { Image as ImageIcon, Monitor, Camera, Upload, Loader2, ScanText, Eye, User } from 'lucide-react';
import { Button } from '../../components/ui/Button';
import {
  captureScreen,
  captureAndAnalyzeScreen,
  analyzeImage,
  uploadImageForVision,
  resolveStaticUrl,
  detectObjects,
  listGroundings,
  type VisionResult,
} from '../../services/api';

/**
 * Images / Vision — desktop sight (native screen capture) + OCR + image analysis,
 * mirroring the desktop (Qt) and Android (Compose) Vision pages. The "Capture &
 * analyze" button asks the backend (running on the same PC) to grab and understand
 * its own screen via /vision/capture-and-analyze; "Choose image" uploads a local
 * file via /mobile/camera and analyses it via /vision/analyze.
 *
 * P1-1 AGI: Now also shows grounded object detections (perception→grounding loop)
 * so words like "person", "chair", "face" are grounded to real visual features.
 */
export function ImagesPage() {
  const [promptFocus, setPromptFocus] = useState('');
  const [busy, setBusy] = useState(false);
  const [busyLabel, setBusyLabel] = useState('');
  const [error, setError] = useState<string | null>(null);
  const [previewUrl, setPreviewUrl] = useState<string | null>(null);
  const [ocrText, setOcrText] = useState('');
  const [analysisText, setAnalysisText] = useState('');
  const [detections, setDetections] = useState<Array<{ label: string; confidence: number; bbox?: { x: number; y: number; width: number; height: number } }>>([]);
  const [groundings, setGroundings] = useState<Array<{ symbol: string; modality: string; confidence: number }>>([]);
  const [engine, setEngine] = useState<string>('');
  const fileInputRef = useRef<HTMLInputElement>(null);
  // Track the local blob: URL so we can revoke it (avoid leaking object URLs).
  const localPreviewUrlRef = useRef<string | null>(null);

  // Revoke any local blob URL on unmount.
  useEffect(() => {
    return () => {
      if (localPreviewUrlRef.current) {
        URL.revokeObjectURL(localPreviewUrlRef.current);
        localPreviewUrlRef.current = null;
      }
    };
  }, []);

  const applyResult = (res: VisionResult & { detections?: typeof detections; groundings_created?: string[]; detection_engine?: string; engine?: string }) => {
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
    // B9 fix: if we had a blob URL and now have a backend URL, revoke the blob
    const url = res.image_url || res.file_url;
    if (url) {
      const absUrl = resolveStaticUrl(url);
      if (localPreviewUrlRef.current && absUrl !== localPreviewUrlRef.current) {
        URL.revokeObjectURL(localPreviewUrlRef.current);
        localPreviewUrlRef.current = null;
      }
      setPreviewUrl(absUrl);
    }
    if (res.detections) {
      setDetections(res.detections as any);
      setEngine((res as any).detection_engine || (res as any).engine || '');
    }
    // Refresh grounding list (shows how words are grounded to vision)
    listGroundings().then((g) => {
      if (g) setGroundings(g.groundings.slice(0, 20) as any);
    });
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
    setDetections([]);
    try {
      applyResult(await captureAndAnalyzeScreen(promptFocus));
    } catch (e) {
      setBusy(false);
      setBusyLabel('');
      setError(String(e));
    }
  };

  const handleDetectObjects = async () => {
    if (!previewUrl) {
      setError('No image to detect — capture or upload first');
      return;
    }
    setBusy(true);
    setBusyLabel('Detecting objects + grounding symbols…');
    setError(null);
    try {
      // For backend-hosted images we need the file_path, not the http URL
      // The last analysis result's file_path is stored in the backend, but we
      // can re-upload or use the previewUrl's path. Simplest: if previewUrl is
      // blob, upload; else try to detect via latest screenshot.
      // Here we call detectObjects on the last known file — for demo we use
      // the backend's /vision/detect-objects with a placeholder that will be
      // resolved to latest screenshot if needed.
      // For uploaded images, we have the file_path from upload step — to keep
      // it simple, we detect on the previewUrl if it's backend URL by extracting path.
      let imagePath = '';
      if (previewUrl.startsWith('blob:')) {
        setError('Upload an image first to detect objects (blob URLs are local only)');
        setBusy(false);
        setBusyLabel('');
        return;
      } else {
        // previewUrl is like http://localhost:8000/static/workspace/screenshots/xxx.png
        // Extract the file system path part
        const u = new URL(previewUrl);
        const staticPart = u.pathname.replace('/static/', '');
        imagePath = staticPart;
      }
      const res = await detectObjects(imagePath);
      applyResult(res as any);
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
    setDetections([]);
    // Show a local preview immediately (revoke the previous blob URL first).
    if (localPreviewUrlRef.current) {
      URL.revokeObjectURL(localPreviewUrlRef.current);
    }
    localPreviewUrlRef.current = URL.createObjectURL(file);
    setPreviewUrl(localPreviewUrlRef.current);
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
      applyResult({ ...result, image_url: backendUrl || result.image_url } as any);
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
          Desktop sight, OCR, and grounded object detection — perception→grounding loop (P1-1 AGI). Vision uses OCR + Qwen text analysis + object detection (YOLO/SSD/face) due to RX 580 VRAM limits, not a full VLM — honest.
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
            <Button variant="secondary" onClick={handleDetectObjects} disabled={busy}>
              <Eye className="w-4 h-4 mr-2" />
              Detect + ground
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

        {/* Detections (grounded) */}
        <section>
          <h3 className="text-sm font-medium text-text-muted mb-2 flex items-center gap-2">
            <Eye className="w-4 h-4" /> Grounded detections {engine ? `(engine: ${engine})` : ''}
          </h3>
          <div className="rounded-lg bg-background-secondary border border-background-surface p-4 text-sm text-text-primary min-h-[48px]">
            {detections.length ? (
              <ul className="space-y-1">
                {detections.map((d, i) => (
                  <li key={i} className="flex items-center gap-2">
                    {d.label === 'face' ? <User className="w-4 h-4 text-accent-primary" /> : <Eye className="w-4 h-4 text-text-muted" />}
                    <span className="font-medium">{d.label}</span>
                    <span className="text-text-muted">conf {d.confidence.toFixed(2)}</span>
                    {d.bbox ? <span className="text-text-muted">bbox [{d.bbox.x},{d.bbox.y},{d.bbox.width}x{d.bbox.height}]</span> : null}
                  </li>
                ))}
              </ul>
            ) : (
              '(no detections yet — press Detect + ground)'
            )}
          </div>
        </section>

        {/* Groundings */}
        <section>
          <h3 className="text-sm font-medium text-text-muted mb-2">Language groundings (how words connect to vision)</h3>
          <div className="rounded-lg bg-background-secondary border border-background-surface p-4 text-sm text-text-primary min-h-[48px]">
            {groundings.length ? (
              <ul className="space-y-1">
                {groundings.map((g, i) => (
                  <li key={i}>
                    <span className="font-medium">{g.symbol}</span> → {g.modality} (conf {g.confidence.toFixed(2)})
                  </li>
                ))}
              </ul>
            ) : (
              '(no groundings yet — detections auto-create them)'
            )}
          </div>
        </section>

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
