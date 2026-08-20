"""Text-to-Speech using Piper."""

import asyncio
import subprocess
import tempfile
import numpy as np
from pathlib import Path
from typing import Optional, Callable
from app.utils.logger import app_logger

try:
    import soundfile as sf
except ImportError:
    sf = None
    app_logger.warning("soundfile not installed. TTS unavailable.")


class TextToSpeechService:
    """
    Text-to-Speech service using Piper.
    
    Synthesizes speech from text with streaming support.
    """
    
    def __init__(
        self,
        voice: str = "en_US-lessac-medium",
        speed: float = 1.0,
        piper_path: str = "piper",
    ):
        self.voice = voice
        self.speed = speed
        self.piper_path = piper_path
        
        self.is_running = False
        self.model_path: Optional[Path] = None
        
        # Callbacks
        self.on_audio_ready: Optional[Callable[[np.ndarray], None]] = None
        
        self._find_model()
        
    def _find_model(self):
        """Find Piper voice model."""
        # Common Piper model locations
        model_dirs = [
            Path.home() / ".local/share/piper",
            Path("/usr/share/piper"),
            Path.home() / "piper_models",
        ]
        
        voice_filename = f"{self.voice}.onnx"
        
        for model_dir in model_dirs:
            model_path = model_dir / voice_filename
            if model_path.exists():
                self.model_path = model_path
                app_logger.info(f"Found Piper model: {model_path}")
                return
        
        app_logger.warning(
            f"Piper model '{self.voice}' not found. "
            f"TTS will not work until model is installed."
        )
    
    def start(self):
        """Start TTS service."""
        if self.is_running:
            return
            
        if not self.model_path:
            app_logger.error("TTS service cannot start: model not found")
            return
            
        self.is_running = True
        app_logger.info(f"TTS service started: voice={self.voice}, speed={self.speed}")
    
    def stop(self):
        """Stop TTS service."""
        self.is_running = False
        app_logger.info("TTS service stopped")
    
    def synthesize(self, text: str) -> Optional[np.ndarray]:
        """
        Synthesize speech from text.
        
        Returns audio as numpy array (float32, normalized to [-1, 1]).
        """
        if not self.is_running or not self.model_path:
            return None
            
        try:
            # Create temporary file for output
            with tempfile.NamedTemporaryFile(suffix=".wav", delete=False) as tmp_file:
                tmp_path = tmp_file.name
            
            # Run Piper TTS
            cmd = [
                self.piper_path,
                "--model", str(self.model_path),
                "--output_file", tmp_path,
                "--length_scale", str(1.0 / self.speed),  # Piper uses length_scale (inverse of speed)
            ]
            
            # Pipe text to Piper
            process = subprocess.run(
                cmd,
                input=text,
                capture_output=True,
                text=True,
                timeout=10.0,
            )
            
            if process.returncode != 0:
                app_logger.error(f"Piper TTS error: {process.stderr}")
                return None
            
            # Read audio file
            audio, sample_rate = sf.read(tmp_path, dtype='float32')
            
            # Clean up temporary file
            Path(tmp_path).unlink(missing_ok=True)
            
            app_logger.info(f"TTS complete: {len(text)} chars -> {len(audio)} samples")
            
            # Trigger callback
            if self.on_audio_ready:
                try:
                    self.on_audio_ready(audio)
                except Exception as e:
                    app_logger.error(f"TTS audio callback error: {e}")
            
            return audio
            
        except subprocess.TimeoutExpired:
            app_logger.error("Piper TTS timeout")
            return None
        except Exception as e:
            app_logger.error(f"TTS synthesis error: {e}")
            return None
    
    async def synthesize_async(self, text: str) -> Optional[np.ndarray]:
        """Async wrapper for synthesize."""
        loop = asyncio.get_event_loop()
        return await loop.run_in_executor(None, self.synthesize, text)
    
    def set_voice(self, voice: str):
        """Change TTS voice."""
        self.voice = voice
        self._find_model()
        app_logger.info(f"TTS voice changed to: {voice}")
    
    def set_speed(self, speed: float):
        """Change TTS speed."""
        self.speed = max(0.5, min(2.0, speed))  # Clamp to [0.5, 2.0]
        app_logger.info(f"TTS speed changed to: {speed}")
