import { useState, useRef, useEffect, useCallback } from 'react';
import type { Screenshot } from '../../stores/screenshotStore';
import { Button } from './Button';
import { Square, Circle, ArrowRight, Type, Trash2, Check } from 'lucide-react';

interface ScreenshotAnnotatorProps {
  screenshot: Screenshot;
  onSave: (annotations: Screenshot['annotations']) => void;
  onCancel: () => void;
}

type AnnotationType = 'rect' | 'circle' | 'arrow' | 'text';

interface Annotation {
  type: AnnotationType;
  x: number;
  y: number;
  width?: number;
  height?: number;
  color: string;
  text?: string;
}

function drawSingleAnnotation(ctx: CanvasRenderingContext2D, annotation: Annotation): void {
  ctx.strokeStyle = annotation.color;
  ctx.lineWidth = 3;
  ctx.fillStyle = annotation.color;

  if (annotation.type === 'rect') {
    ctx.strokeRect(annotation.x, annotation.y, annotation.width || 0, annotation.height || 0);
  } else if (annotation.type === 'circle') {
    ctx.beginPath();
    ctx.arc(annotation.x, annotation.y, annotation.width || 0, 0, 2 * Math.PI);
    ctx.stroke();
  } else if (annotation.type === 'arrow') {
    const w = annotation.width || 0;
    const h = annotation.height || 0;
    ctx.beginPath();
    ctx.moveTo(annotation.x, annotation.y);
    ctx.lineTo(annotation.x + w, annotation.y + h);
    ctx.stroke();

    // Draw arrowhead
    const angle = Math.atan2(h, w);
    const arrowLength = 15;
    ctx.beginPath();
    ctx.moveTo(annotation.x + w, annotation.y + h);
    ctx.lineTo(
      annotation.x + w - arrowLength * Math.cos(angle - Math.PI / 6),
      annotation.y + h - arrowLength * Math.sin(angle - Math.PI / 6)
    );
    ctx.moveTo(annotation.x + w, annotation.y + h);
    ctx.lineTo(
      annotation.x + w - arrowLength * Math.cos(angle + Math.PI / 6),
      annotation.y + h - arrowLength * Math.sin(angle + Math.PI / 6)
    );
    ctx.stroke();
  } else if (annotation.type === 'text' && annotation.text) {
    ctx.font = '16px Arial';
    ctx.fillText(annotation.text, annotation.x, annotation.y);
  }
}

function drawAllAnnotations(ctx: CanvasRenderingContext2D, annots: Annotation[]): void {
  annots.forEach((annotation) => drawSingleAnnotation(ctx, annotation));
}

export function ScreenshotAnnotator({ screenshot, onSave, onCancel }: ScreenshotAnnotatorProps) {
  const [annotations, setAnnotations] = useState<Annotation[]>(
    (screenshot.annotations as Annotation[]) || []
  );
  const [selectedTool, setSelectedTool] = useState<AnnotationType>('rect');
  const [selectedColor, setSelectedColor] = useState('#ef4444');
  const [isDrawing, setIsDrawing] = useState(false);
  const [startPos, setStartPos] = useState<{ x: number; y: number } | null>(null);
  const [currentAnnotation, setCurrentAnnotation] = useState<Annotation | null>(null);

  const canvasRef = useRef<HTMLCanvasElement>(null);

  const colors = ['#ef4444', '#f59e0b', '#10b981', '#3b82f6', '#8b5cf6', '#ec4899'];

  useEffect(() => {
    if (!canvasRef.current) return;

    const canvas = canvasRef.current;
    const ctx = canvas.getContext('2d');
    if (!ctx) return;

    // Load image
    const img = new Image();
    img.onload = () => {
      canvas.width = img.width;
      canvas.height = img.height;

      // Draw image
      ctx.drawImage(img, 0, 0);

      // Draw annotations
      drawAllAnnotations(ctx, annotations);

      // Draw current annotation if drawing
      if (currentAnnotation) {
        drawSingleAnnotation(ctx, currentAnnotation);
      }
    };

    img.src = `data:image/${screenshot.format};base64,${screenshot.image}`;
  }, [screenshot, annotations, currentAnnotation]);

  const getCanvasPosition = useCallback((e: React.MouseEvent<HTMLCanvasElement>) => {
    const canvas = canvasRef.current;
    if (!canvas) return { x: 0, y: 0 };

    const rect = canvas.getBoundingClientRect();
    const scaleX = canvas.width / rect.width;
    const scaleY = canvas.height / rect.height;

    return {
      x: (e.clientX - rect.left) * scaleX,
      y: (e.clientY - rect.top) * scaleY,
    };
  }, []);

  const handleMouseDown = useCallback((e: React.MouseEvent<HTMLCanvasElement>) => {
    const pos = getCanvasPosition(e);
    setIsDrawing(true);
    setStartPos(pos);

    if (selectedTool === 'text') {
      const text = prompt('Enter text:');
      if (text) {
        const newAnnotation: Annotation = {
          type: 'text',
          x: pos.x,
          y: pos.y,
          color: selectedColor,
          text,
        };
        setAnnotations((prev) => [...prev, newAnnotation]);
      }
      setIsDrawing(false);
    }
  }, [getCanvasPosition, selectedTool, selectedColor]);

  const handleMouseMove = useCallback((e: React.MouseEvent<HTMLCanvasElement>) => {
    if (!isDrawing || !startPos || selectedTool === 'text') return;

    const pos = getCanvasPosition(e);
    const width = pos.x - startPos.x;
    const height = pos.y - startPos.y;

    if (selectedTool === 'rect') {
      setCurrentAnnotation({
        type: 'rect',
        x: startPos.x,
        y: startPos.y,
        width,
        height,
        color: selectedColor,
      });
    } else if (selectedTool === 'circle') {
      const radius = Math.sqrt(width * width + height * height);
      setCurrentAnnotation({
        type: 'circle',
        x: startPos.x,
        y: startPos.y,
        width: radius,
        color: selectedColor,
      });
    } else if (selectedTool === 'arrow') {
      setCurrentAnnotation({
        type: 'arrow',
        x: startPos.x,
        y: startPos.y,
        width,
        height,
        color: selectedColor,
      });
    }
  }, [isDrawing, startPos, selectedTool, selectedColor, getCanvasPosition]);

  const handleMouseUp = useCallback(() => {
    if (!isDrawing || !currentAnnotation) {
      setIsDrawing(false);
      return;
    }

    setAnnotations((prev) => [...prev, currentAnnotation]);
    setCurrentAnnotation(null);
    setIsDrawing(false);
    setStartPos(null);
  }, [isDrawing, currentAnnotation]);

  const handleDeleteLast = useCallback(() => {
    setAnnotations((prev) => prev.slice(0, -1));
  }, []);

  const handleSave = useCallback(() => {
    onSave(annotations);
  }, [onSave, annotations]);

  return (
    <div className="space-y-4">
      {/* Toolbar */}
      <div className="flex items-center justify-between">
        <div className="flex items-center gap-2">
          <Button
            onClick={() => setSelectedTool('rect')}
            variant={selectedTool === 'rect' ? 'primary' : 'secondary'}
            size="sm"
          >
            <Square className="w-4 h-4" />
          </Button>
          <Button
            onClick={() => setSelectedTool('circle')}
            variant={selectedTool === 'circle' ? 'primary' : 'secondary'}
            size="sm"
          >
            <Circle className="w-4 h-4" />
          </Button>
          <Button
            onClick={() => setSelectedTool('arrow')}
            variant={selectedTool === 'arrow' ? 'primary' : 'secondary'}
            size="sm"
          >
            <ArrowRight className="w-4 h-4" />
          </Button>
          <Button
            onClick={() => setSelectedTool('text')}
            variant={selectedTool === 'text' ? 'primary' : 'secondary'}
            size="sm"
          >
            <Type className="w-4 h-4" />
          </Button>

          <div className="w-px h-6 bg-border mx-2" />

          {colors.map((color) => (
            <button
              key={color}
              onClick={() => setSelectedColor(color)}
              className={`w-6 h-6 rounded-full border-2 transition-all ${
                selectedColor === color ? 'border-white scale-110' : 'border-transparent'
              }`}
              style={{ backgroundColor: color }}
              aria-label={`Select color ${color}`}
            />
          ))}

          <div className="w-px h-6 bg-border mx-2" />

          <Button onClick={handleDeleteLast} variant="secondary" size="sm" disabled={annotations.length === 0}>
            <Trash2 className="w-4 h-4 mr-2" />
            Undo
          </Button>
        </div>

        <div className="flex items-center gap-2">
          <Button onClick={onCancel} variant="secondary" size="sm">
            Cancel
          </Button>
          <Button onClick={handleSave} variant="primary" size="sm">
            <Check className="w-4 h-4 mr-2" />
            Save
          </Button>
        </div>
      </div>

      {/* Canvas */}
      <div className="bg-background-surface rounded-lg overflow-hidden">
        <canvas
          ref={canvasRef}
          className="w-full h-auto cursor-crosshair"
          onMouseDown={handleMouseDown}
          onMouseMove={handleMouseMove}
          onMouseUp={handleMouseUp}
          onMouseLeave={handleMouseUp}
        />
      </div>

      {/* Info */}
      <div className="text-sm text-text-secondary">
        <p>Click and drag to draw annotations. Use the toolbar to select tools and colors.</p>
      </div>
    </div>
  );
}
