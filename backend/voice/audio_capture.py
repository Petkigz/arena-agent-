"""Audio capture service using PyAudio.

Gracefully degrades if PyAudio is not installed — the backend will
still start and text chat will work, but voice features will be unavailable.
"""

import asyncio
import queue
import numpy as np
from typing import Optional, Callable
from app.utils.logger import app_logger

try:
    import pyaudio
    PYAUDIO_AVAILABLE = True
except ImportError:
    pyaudio = None
    PYAUDIO_AVAILABLE = False
    app_logger.warning(
        "PyAudio not installed. Voice features unavailable. "
        "Install with: pip install pyaudio"
    )


class AudioCaptureService:
    """
    Continuous audio capture service with circular buffer.
    
    Captures audio from microphone and provides it to:
    - Wake word detector (always listening)
    - Voice activity detector (when wake word detected)
    - Speech-to-text (when speech detected)
    """
    
    def __init__(
        self,
        sample_rate: int = 16000,
        channels: int = 1,
        chunk_size: int = 1024,
        buffer_size: int = 16000,  # 1 second buffer
    ):
        self.sample_rate = sample_rate
        self.channels = channels
        self.chunk_size = chunk_size
        self.buffer_size = buffer_size
        
        self.audio_queue: queue.Queue = queue.Queue(maxsize=100)
        self.is_running = False
        self.stream = None
        self.pyaudio_instance = None
        
        # Callbacks
        self.on_audio_chunk: Optional[Callable[[np.ndarray], None]] = None
        
    def start(self):
        """Start audio capture."""
        if not PYAUDIO_AVAILABLE:
            app_logger.warning("Cannot start audio capture: PyAudio not installed")
            return

        if self.is_running:
            return
            
        try:
            self.pyaudio_instance = pyaudio.PyAudio()
            
            self.stream = self.pyaudio_instance.open(
                format=pyaudio.paInt16,
                channels=self.channels,
                rate=self.sample_rate,
                input=True,
                frames_per_buffer=self.chunk_size,
                stream_callback=self._audio_callback,
            )
            
            self.is_running = True
            self.stream.start_stream()
            app_logger.info(f"Audio capture started: {self.sample_rate}Hz, {self.channels}ch")
            
        except Exception as e:
            app_logger.error(f"Failed to start audio capture: {e}")
            raise
    
    def stop(self):
        """Stop audio capture."""
        if not self.is_running:
            return
            
        self.is_running = False
        
        if self.stream:
            self.stream.stop_stream()
            self.stream.close()
            self.stream = None
            
        if self.pyaudio_instance:
            self.pyaudio_instance.terminate()
            self.pyaudio_instance = None
            
        app_logger.info("Audio capture stopped")
    
    def _audio_callback(self, in_data, frame_count, time_info, status):
        """PyAudio callback for audio chunks."""
        if not self.is_running:
            return (None, pyaudio.paComplete)
            
        # Convert bytes to numpy array
        audio_data = np.frombuffer(in_data, dtype=np.int16)
        
        # Normalize to float32 [-1, 1]
        audio_float = audio_data.astype(np.float32) / 32768.0
        
        # Put in queue (non-blocking)
        try:
            self.audio_queue.put_nowait(audio_float)
        except queue.Full:
            # Drop oldest chunk if queue is full
            try:
                self.audio_queue.get_nowait()
                self.audio_queue.put_nowait(audio_float)
            except queue.Empty:
                pass
        
        # Call callback if registered
        if self.on_audio_chunk:
            try:
                self.on_audio_chunk(audio_float)
            except Exception as e:
                app_logger.error(f"Audio chunk callback error: {e}")
        
        return (None, pyaudio.paContinue)
    
    def get_audio_chunk(self, timeout: float = 0.1) -> Optional[np.ndarray]:
        """Get next audio chunk from queue."""
        try:
            return self.audio_queue.get(timeout=timeout)
        except queue.Empty:
            return None
    
    def get_buffer(self, duration_seconds: float) -> np.ndarray:
        """Get audio buffer of specified duration."""
        num_samples = int(self.sample_rate * duration_seconds)
        chunks = []
        total_samples = 0
        
        while total_samples < num_samples:
            chunk = self.get_audio_chunk(timeout=0.1)
            if chunk is not None:
                chunks.append(chunk)
                total_samples += len(chunk)
                
        if not chunks:
            return np.zeros(num_samples, dtype=np.float32)
            
        buffer = np.concatenate(chunks)
        return buffer[:num_samples]
