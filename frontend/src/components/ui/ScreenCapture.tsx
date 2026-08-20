import { logger } from '../../services/logger';
import { useState, useRef, useEffect } from 'react';
import { useScreenshotStore, type Screenshot } from '../../stores/screenshotStore';
import { Button } from './Button';
import { Monitor, StopCircle, Camera, Maximize2 } from 'lucide-react';

interface ScreenCaptureProps {
  conversationId: string;
  onCapture?: (screenshot: Screenshot) => void;
}

export function ScreenCapture({ conversationId, onCapture }: ScreenCaptureProps) {
  const {
    isCapturing,
    isStreaming,
    startCapture,
    stopCapture,
    startStreaming,
    stopStreaming,
    sendScreenshot,
  } = useScreenshotStore();

  const [stream, setStream] = useState<MediaStream | null>(null);
  const [previewUrl, setPreviewUrl] = useState<string | null>(null);
  const videoRef = useRef<HTMLVideoElement>(null);
  const canvasRef = useRef<HTMLCanvasElement>(null);
  const captureIntervalRef = useRef<number | null>(null);

  const startScreenCapture = async () => {
    try {
      // Request screen capture
      const mediaStream = await navigator.mediaDevices.getDisplayMedia({
        video: {
          width: 1920,
          height: 1080,
          frameRate: 30,
        },
        audio: false,
      });

      setStream(mediaStream);
      startCapture();
      startStreaming(conversationId);

      // Display preview
      if (videoRef.current) {
        videoRef.current.srcObject = mediaStream;
        videoRef.current.play();
      }

      // Handle stream end
      mediaStream.getVideoTracks()[0].onended = () => {
        stopScreenCapture();
      };

      // Start periodic captures
      captureIntervalRef.current = setInterval(() => {
        captureScreenshot();
      }, 2000); // Capture every 2 seconds
    } catch (error) {
      logger.error('Failed to start screen capture:', error);
    }
  };

  const stopScreenCapture = () => {
    if (stream) {
      stream.getTracks().forEach((track) => track.stop());
      setStream(null);
    }

    if (previewUrl) {
      URL.revokeObjectURL(previewUrl);
      setPreviewUrl(null);
    }

    if (captureIntervalRef.current) {
      clearInterval(captureIntervalRef.current);
      captureIntervalRef.current = null;
    }

    stopCapture();
    stopStreaming();
  };

  const captureScreenshot = () => {
    if (!videoRef.current || !canvasRef.current) return;

    const video = videoRef.current;
    const canvas = canvasRef.current;
    const ctx = canvas.getContext('2d');

    if (!ctx) return;

    // Set canvas size to match video
    canvas.width = video.videoWidth;
    canvas.height = video.videoHeight;

    // Draw video frame to canvas
    ctx.drawImage(video, 0, 0, canvas.width, canvas.height);

    // Convert to base64
    const imageData = canvas.toDataURL('image/png');
    const base64Image = imageData.split(',')[1];

    const screenshot = {
      id: `ss-${Date.now()}`,
      timestamp: new Date().toISOString(),
      image: base64Image,
      width: canvas.width,
      height: canvas.height,
      format: 'png',
      annotations: [],
    };

    // Send to backend
    sendScreenshot(screenshot);

    // Notify parent
    if (onCapture) {
      onCapture(screenshot);
    }
  };

  const captureManual = () => {
    captureScreenshot();
  };

  useEffect(() => {
    return () => {
      stopScreenCapture();
    };
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  return (
    <div className="space-y-4">
      {/* Controls */}
      <div className="flex items-center gap-3">
        {!isCapturing ? (
          <Button onClick={startScreenCapture} variant="primary">
            <Monitor className="w-4 h-4 mr-2" />
            Start Screen Capture
          </Button>
        ) : (
          <>
            <Button onClick={stopScreenCapture} variant="danger">
              <StopCircle className="w-4 h-4 mr-2" />
              Stop Capture
            </Button>
            <Button onClick={captureManual} variant="secondary">
              <Camera className="w-4 h-4 mr-2" />
              Capture Now
            </Button>
          </>
        )}

        {isStreaming && (
          <div className="flex items-center gap-2 text-sm text-green-500">
            <div className="w-2 h-2 bg-green-500 rounded-full animate-pulse" />
            <span>Streaming</span>
          </div>
        )}
      </div>

      {/* Video preview */}
      {isCapturing && (
        <div className="relative bg-background-surface rounded-lg overflow-hidden">
          <video
            ref={videoRef}
            className="w-full h-auto"
            muted
            playsInline
          />
          <canvas ref={canvasRef} className="hidden" />

          {/* Overlay */}
          <div className="absolute top-2 right-2 flex items-center gap-2">
            <div className="px-2 py-1 bg-black/50 text-white text-xs rounded">
              {isStreaming ? 'Live' : 'Preview'}
            </div>
          </div>
        </div>
      )}

      {/* Info */}
      {!isCapturing && (
        <div className="p-4 bg-background-surface rounded-lg">
          <div className="flex items-start gap-3">
            <Maximize2 className="w-5 h-5 text-text-muted flex-shrink-0 mt-0.5" />
            <div>
              <h4 className="font-medium text-text-primary mb-1">Screen Capture</h4>
              <p className="text-sm text-text-secondary">
                Capture your screen and stream it to Arena for real-time analysis. 
                Screenshots are captured every 2 seconds and can be annotated.
              </p>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
