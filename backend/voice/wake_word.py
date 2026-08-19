"""Wake word detection using openWakeWord."""

import asyncio
import numpy as np
from typing import Optional, Callable
from app.utils.logger import app_logger

try:
    from openwakeword.model import Model as OWWModel
    from openwakeword.utils import download_models
except ImportError:
    app_logger.warning("openWakeWord not installed. Wake word detection disabled.")
    OWWModel = None
    download_models = None


class WakeWordDetector:
    """Detects wake word in audio stream."""

    def __init__(
        self,
        wake_word: str = "hey_jarvis",
        sensitivity: float = 0.5,
        sample_rate: int = 16000,
    ):
        self.wake_word = wake_word
        self.sensitivity = sensitivity
        self.sample_rate = sample_rate

        self.model: Optional[OWWModel] = None
        self.is_running = False

        # Callback
        self.on_wake_word_detected: Optional[Callable[[str], None]] = None

    def start(self):
        """Start wake word detection."""
        if self.is_running:
            return

        if OWWModel is None:
            app_logger.warning("Cannot start wake word detector: openWakeWord not installed")
            return

        try:
            # Download models if needed (non-blocking check)
            try:
                download_models()
            except Exception as e:
                app_logger.warning(f"Could not download wake word models: {e}")

            # Map wake word names to openWakeWord model names
            # openWakeWord has: hey_jarvis, hey_mycroft, alexa, etc.
            model_name = self.wake_word
            if "jarvis" in model_name.lower():
                model_name = "hey_jarvis"
            elif "mycroft" in model_name.lower():
                model_name = "hey_mycroft"
            elif "alexa" in model_name.lower():
                model_name = "alexa"
            else:
                # Default to hey_jarvis if unknown
                model_name = "hey_jarvis"

            # Initialize model
            self.model = OWWModel(
                wakeword_models=[model_name],
                inference_framework="onnx",
            )

            self.is_running = True
            app_logger.info(f"Wake word detector started (model: {model_name})")

        except Exception as e:
            app_logger.error(f"Failed to start wake word detector: {e}")
            raise

    def stop(self):
        """Stop wake word detection."""
        self.is_running = False
        self.model = None
        app_logger.info("Wake word detector stopped")

    def process_audio(self, audio_chunk: np.ndarray) -> bool:
        """Process audio chunk and detect wake word.

        Args:
            audio_chunk: Audio samples as float32 numpy array

        Returns:
            True if wake word detected, False otherwise
        """
        if not self.is_running or self.model is None:
            return False

        try:
            # Convert float32 to int16 for openWakeWord
            audio_int16 = (audio_chunk * 32767).astype(np.int16)

            # Run inference
            prediction = self.model.predict(audio_int16)

            # Check if any wake word exceeded threshold
            for wake_word, score in prediction.items():
                if score > self.sensitivity:
                    app_logger.info(f"Wake word detected: {wake_word} (score: {score:.3f})")

                    # Reset model to prevent repeated detections
                    self.model.reset()

                    # Notify callback
                    if self.on_wake_word_detected:
                        self.on_wake_word_detected(wake_word)

                    return True

            return False

        except Exception as e:
            app_logger.error(f"Wake word detection error: {e}")
            return False
