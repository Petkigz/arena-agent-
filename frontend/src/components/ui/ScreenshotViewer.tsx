import { useState, useRef, useEffect } from 'react';
import { useScreenshotStore, type Screenshot } from '../../stores/screenshotStore';
import { Button } from './Button';
import { ZoomIn, ZoomOut, RotateCcw, Download, Trash2, Edit } from 'lucide-react';

interface ScreenshotViewerProps {
  screenshot?: Screenshot;
  onClose?: () => void;
  onAnnotate?: (screenshot: Screenshot) => void;
  onDelete?: (screenshotId: string) => void;
}

export function ScreenshotViewer({ screenshot, onClose, onAnnotate, onDelete }: ScreenshotViewerProps) {
  const { currentScreenshot, screenshots, setCurrentScreenshot } = useScreenshotStore();
  const [zoom, setZoom] = useState(1);
  const [rotation, setRotation] = useState(0);
  const canvasRef = useRef<HTMLCanvasElement>(null);

  const activeScreenshot = screenshot || currentScreenshot;

  useEffect(() => {
    if (!activeScreenshot || !canvasRef.current) return;

    const canvas = canvasRef.current;
    const ctx = canvas.getContext('2d');
    if (!ctx) return;

    // Load image
    const img = new Image();
    img.onload = () => {
      // Set canvas size
      canvas.width = img.width * zoom;
      canvas.height = img.height * zoom;

      // Clear canvas
      ctx.clearRect(0, 0, canvas.width, canvas.height);

      // Apply rotation
      ctx.save();
      ctx.translate(canvas.width / 2, canvas.height / 2);
      ctx.rotate((rotation * Math.PI) / 180);
      ctx.translate(-canvas.width / 2, -canvas.height / 2);

      // Draw image
      ctx.drawImage(img, 0, 0, canvas.width, canvas.height);

      // Draw annotations
      if (activeScreenshot.annotations && activeScreenshot.annotations.length > 0) {
        activeScreenshot.annotations.forEach((annotation) => {
          ctx.strokeStyle = annotation.color;
          ctx.lineWidth = 3;
          ctx.fillStyle = annotation.color;

          if (annotation.type === 'rect') {
            ctx.strokeRect(
              annotation.x * zoom,
              annotation.y * zoom,
              (annotation.width || 0) * zoom,
              (annotation.height || 0) * zoom
            );
          } else if (annotation.type === 'circle') {
            ctx.beginPath();
            ctx.arc(
              annotation.x * zoom,
              annotation.y * zoom,
              (annotation.width || 50) * zoom,
              0,
              2 * Math.PI
            );
            ctx.stroke();
          } else if (annotation.type === 'arrow') {
            ctx.beginPath();
            ctx.moveTo(annotation.x * zoom, annotation.y * zoom);
            ctx.lineTo(
              (annotation.x + (annotation.width || 100)) * zoom,
              (annotation.y + (annotation.height || 0)) * zoom
            );
            ctx.stroke();
          } else if (annotation.type === 'text' && annotation.text) {
            ctx.font = `${16 * zoom}px Arial`;
            ctx.fillText(annotation.text, annotation.x * zoom, annotation.y * zoom);
          }
        });
      }

      ctx.restore();
    };

    img.src = `data:image/${activeScreenshot.format};base64,${activeScreenshot.image}`;
  }, [activeScreenshot, zoom, rotation]);

  const handleZoomIn = () => setZoom((z) => Math.min(z + 0.25, 3));
  const handleZoomOut = () => setZoom((z) => Math.max(z - 0.25, 0.5));
  const handleReset = () => {
    setZoom(1);
    setRotation(0);
  };

  const handleDownload = () => {
    if (!activeScreenshot) return;

    const link = document.createElement('a');
    link.href = `data:image/${activeScreenshot.format};base64,${activeScreenshot.image}`;
    link.download = `screenshot-${activeScreenshot.id}.${activeScreenshot.format}`;
    link.click();
  };

  const handleDelete = () => {
    if (!activeScreenshot || !onDelete) return;
    if (confirm('Are you sure you want to delete this screenshot?')) {
      onDelete(activeScreenshot.id);
    }
  };

  if (!activeScreenshot) {
    return (
      <div className="flex items-center justify-center h-64 text-text-muted">
        No screenshot selected
      </div>
    );
  }

  return (
    <div className="space-y-4">
      {/* Toolbar */}
      <div className="flex items-center justify-between">
        <div className="flex items-center gap-2">
          <Button onClick={handleZoomOut} variant="secondary" size="sm">
            <ZoomOut className="w-4 h-4" />
          </Button>
          <span className="text-sm text-text-secondary">{Math.round(zoom * 100)}%</span>
          <Button onClick={handleZoomIn} variant="secondary" size="sm">
            <ZoomIn className="w-4 h-4" />
          </Button>
          <Button onClick={handleReset} variant="secondary" size="sm">
            <RotateCcw className="w-4 h-4" />
          </Button>
        </div>

        <div className="flex items-center gap-2">
          {onAnnotate && (
            <Button onClick={() => onAnnotate(activeScreenshot)} variant="secondary" size="sm">
              <Edit className="w-4 h-4 mr-2" />
              Annotate
            </Button>
          )}
          <Button onClick={handleDownload} variant="secondary" size="sm">
            <Download className="w-4 h-4 mr-2" />
            Download
          </Button>
          {onDelete && (
            <Button onClick={handleDelete} variant="secondary" size="sm">
              <Trash2 className="w-4 h-4 mr-2" />
              Delete
            </Button>
          )}
          {onClose && (
            <Button onClick={onClose} variant="secondary" size="sm">
              Close
            </Button>
          )}
        </div>
      </div>

      {/* Canvas */}
      <div className="bg-background-surface rounded-lg overflow-hidden">
        <canvas ref={canvasRef} className="w-full h-auto" />
      </div>

      {/* Info */}
      <div className="flex items-center gap-4 text-sm text-text-secondary">
        <span>{activeScreenshot.width} × {activeScreenshot.height}</span>
        <span>•</span>
        <span>{activeScreenshot.format.toUpperCase()}</span>
        <span>•</span>
        <span>{new Date(activeScreenshot.timestamp).toLocaleString()}</span>
      </div>

      {/* Analysis */}
      {activeScreenshot.analysis && (
        <div className="p-4 bg-background-surface rounded-lg">
          <h4 className="font-medium text-text-primary mb-2">Analysis</h4>
          <p className="text-sm text-text-secondary">{activeScreenshot.analysis.content}</p>
          {activeScreenshot.analysis.prompt_focus && (
            <p className="text-xs text-text-muted mt-2">
              Focus: {activeScreenshot.analysis.prompt_focus}
            </p>
          )}
        </div>
      )}

      {/* Screenshot list */}
      {screenshots.length > 1 && (
        <div className="space-y-2">
          <h4 className="font-medium text-text-primary">Recent Screenshots</h4>
          <div className="grid grid-cols-4 gap-2">
            {screenshots.slice(0, 8).map((ss) => (
              <button
                key={ss.id}
                onClick={() => setCurrentScreenshot(ss)}
                className={`relative aspect-video rounded-lg overflow-hidden border-2 transition-colors ${
                  ss.id === activeScreenshot.id
                    ? 'border-accent-primary'
                    : 'border-transparent hover:border-accent-primary/50'
                }`}
              >
                <img
                  src={`data:image/${ss.format};base64,${ss.image}`}
                  alt={`Screenshot ${ss.id}`}
                  className="w-full h-full object-cover"
                />
              </button>
            ))}
          </div>
        </div>
      )}
    </div>
  );
}
