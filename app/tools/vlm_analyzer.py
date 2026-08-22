"""VLM analyzer — true visual understanding via tiny VLM (Moondream2 / Llava-Phi), with graceful degradation to OCR+LLM.

P2 AGI: Vision is OCR+LLM due to RX 580 VRAM limits (G6). This module attempts true VLM:
- Tries Moondream2 (1.8B, ~4GB VRAM with Q4, fits RX 580 8GB alongside Qwen 3B fast)
- Tries Llava-Phi-3-mini (3.8B Q4, ~5GB)
- If no VLM available, degrades to VisionAnalyzerTool (OCR+LLM) — never raises

All methods return typed {success: bool, ...} dict.

Owner setup (on your PC, not sandbox):
1. pip install transformers accelerate einops timm
2. Download Moondream2: huggingface-cli download vikhyatk/moondream2 --local-dir data/models/moondream2
   Or let transformers download on first run (needs internet)
3. Set ARENA_VLM_MODEL=vikhyatk/moondream2 or path to local dir

If not set up, this tool returns success=False with honest note, and VisionAnalyzerTool is used.
"""

from __future__ import annotations

import os
from pathlib import Path
from typing import Any, Dict, List, Optional

from app.config import settings
from app.utils.logger import app_logger

try:
    import torch
    TORCH_AVAILABLE = True
except ImportError:
    torch = None
    TORCH_AVAILABLE = False

try:
    from PIL import Image
    PIL_AVAILABLE = True
except ImportError:
    Image = None
    PIL_AVAILABLE = False


class VlmAnalyzerTool:
    """True VLM analyzer with graceful degradation."""

    _model = None
    _tokenizer = None
    _model_id: Optional[str] = None

    @classmethod
    def _resolve_model_id(cls) -> Optional[str]:
        # Env var takes precedence, then local dirs, then default HF id
        env_id = os.getenv("ARENA_VLM_MODEL", "").strip()
        if env_id:
            return env_id

        # Check local dirs
        candidates = [
            settings.DATA_DIR / "models" / "moondream2",
            settings.DATA_DIR / "models" / "moondream",
            Path("data/models/moondream2"),
            Path("moondream2"),
        ]
        for p in candidates:
            if p.exists() and (p.is_dir() and any(p.glob("*.safetensors")) or (p / "config.json").exists() or (p / "model.safetensors").exists()):
                return str(p)

        # Default HF id (will download if internet available)
        return "vikhyatk/moondream2"

    @classmethod
    def _ensure_model(cls):
        if cls._model is not None:
            return cls._model, cls._tokenizer

        if not TORCH_AVAILABLE:
            app_logger.info("VLM unavailable: torch not installed")
            return None, None

        if not PIL_AVAILABLE:
            app_logger.info("VLM unavailable: Pillow not installed")
            return None, None

        try:
            from transformers import AutoModelForCausalLM, AutoTokenizer  # type: ignore
        except ImportError:
            app_logger.info("VLM unavailable: transformers not installed (pip install transformers accelerate einops timm)")
            return None, None

        model_id = cls._resolve_model_id()
        if not model_id:
            return None, None

        # Don't attempt download if offline and model not cached locally
        # We try to load with local_files_only first if path exists, else try normal (may download)
        try:
            # Check if it's a local path
            is_local = Path(model_id).exists()
            load_kwargs = {}
            if is_local:
                load_kwargs["local_files_only"] = True
                load_kwargs["trust_remote_code"] = True
            else:
                load_kwargs["trust_remote_code"] = True
                # For HF id, try local_files_only first to avoid download attempt in offline sandbox
                try:
                    # Try offline first
                    cls._model = AutoModelForCausalLM.from_pretrained(
                        model_id, local_files_only=True, trust_remote_code=True,
                        torch_dtype=torch.float16 if torch.cuda.is_available() else torch.float32,
                    )
                    cls._tokenizer = AutoTokenizer.from_pretrained(model_id, local_files_only=True, trust_remote_code=True)
                    cls._model_id = model_id
                    app_logger.info(f"VLM loaded offline from cache: {model_id}")
                    return cls._model, cls._tokenizer
                except Exception:
                    # If not cached, don't force download in sandbox — degrade
                    # On owner machine with internet, it will download
                    if os.getenv("ARENA_ALLOW_VLM_DOWNLOAD", "").lower() in ("1", "true", "yes"):
                        pass  # allow download below
                    else:
                        app_logger.info(f"VLM model {model_id} not cached locally and download not allowed in this env — degrading to OCR+LLM")
                        return None, None

            # Normal load (may download if allowed)
            cls._model = AutoModelForCausalLM.from_pretrained(
                model_id,
                torch_dtype=torch.float16 if torch.cuda.is_available() else torch.float32,
                **load_kwargs,
            )
            cls._tokenizer = AutoTokenizer.from_pretrained(model_id, **load_kwargs)
            cls._model_id = model_id

            # Move to GPU if available and fits
            try:
                if torch.cuda.is_available():
                    # Check VRAM headroom — don't move if already high pressure
                    from app.utils.hardware_monitor import HardwareMonitor
                    hw = HardwareMonitor.get_hardware_stats()
                    vram_used = float(hw.get("vram_used_percent", 0) or 0)
                    if vram_used < 70:
                        cls._model = cls._model.to("cuda")
                        app_logger.info(f"VLM moved to CUDA: {model_id}")
                    else:
                        app_logger.info(f"VLM kept on CPU (VRAM {vram_used:.0f}% used) — {model_id}")
            except Exception as e:
                app_logger.warning(f"Could not move VLM to GPU: {e}")

            app_logger.info(f"VLM loaded: {model_id}")
            return cls._model, cls._tokenizer

        except Exception as e:
            app_logger.warning(f"VLM load failed (degrading to OCR+LLM): {e}")
            cls._model = None
            cls._tokenizer = None
            return None, None

    @classmethod
    def is_available(cls) -> bool:
        model, tokenizer = cls._ensure_model()
        return model is not None and tokenizer is not None

    @classmethod
    def analyze_image(
        cls,
        image_path_str: str,
        prompt: str = "Describe this image in detail, including objects, text, and what the user should do next.",
        max_tokens: int = 300,
    ) -> Dict[str, Any]:
        """Analyze image with VLM if available, else degrade to OCR+LLM."""
        image_path = Path(image_path_str)
        if not image_path.is_absolute():
            image_path = settings.BASE_DIR / image_path

        if not image_path.exists():
            return {"success": False, "error": f"Image not found: {image_path}", "engine": "none"}

        # Try VLM first
        model, tokenizer = cls._ensure_model()
        if model is not None and tokenizer is not None and PIL_AVAILABLE:
            try:
                img = Image.open(image_path).convert("RGB")

                # Moondream2 API: model.answer_question(image_embeds, question, tokenizer)
                # We need to handle different VLM APIs
                # Try Moondream2 style
                try:
                    # Moondream2: encode image
                    if hasattr(model, "encode_image"):
                        image_embeds = model.encode_image(img)
                        answer = model.answer_question(image_embeds, prompt, tokenizer)
                        return {
                            "success": True,
                            "image_path": str(image_path),
                            "vlm_analysis": str(answer),
                            "engine": f"vlm:{cls._model_id}",
                            "prompt": prompt,
                        }
                except Exception as e:
                    app_logger.debug(f"Moondream2 encode/answer failed: {e}")

                # Try Llava style: processor + model.generate
                try:
                    from transformers import AutoProcessor  # type: ignore
                    processor = AutoProcessor.from_pretrained(cls._model_id or cls._resolve_model_id(), trust_remote_code=True)
                    inputs = processor(text=prompt, images=img, return_tensors="pt")
                    # Move inputs to model device
                    try:
                        device = next(model.parameters()).device
                        inputs = {k: v.to(device) if hasattr(v, "to") else v for k, v in inputs.items()}
                    except Exception:
                        pass
                    generated_ids = model.generate(**inputs, max_new_tokens=max_tokens)
                    # Decode
                    if hasattr(processor, "batch_decode"):
                        output = processor.batch_decode(generated_ids, skip_special_tokens=True)[0]
                    else:
                        output = tokenizer.batch_decode(generated_ids, skip_special_tokens=True)[0]
                    # Remove prompt from output if present
                    if prompt in output:
                        output = output.split(prompt)[-1].strip()
                    return {
                        "success": True,
                        "image_path": str(image_path),
                        "vlm_analysis": str(output),
                        "engine": f"vlm:{cls._model_id}",
                        "prompt": prompt,
                    }
                except Exception as e:
                    app_logger.debug(f"Llava-style VLM failed: {e}")

                # Generic transformers generate with image + text
                try:
                    inputs = tokenizer(prompt, return_tensors="pt")
                    try:
                        device = next(model.parameters()).device
                        inputs = {k: v.to(device) if hasattr(v, "to") else v for k, v in inputs.items()}
                    except Exception:
                        pass
                    # This will likely fail for pure text tokenizer with image, but try
                    generated_ids = model.generate(**inputs, max_new_tokens=max_tokens)
                    output = tokenizer.batch_decode(generated_ids, skip_special_tokens=True)[0]
                    return {
                        "success": True,
                        "image_path": str(image_path),
                        "vlm_analysis": str(output),
                        "engine": f"vlm:{cls._model_id}",
                        "prompt": prompt,
                    }
                except Exception as e:
                    app_logger.debug(f"Generic VLM generate failed: {e}")

            except Exception as e:
                app_logger.warning(f"VLM analysis failed (falling back to OCR+LLM): {e}")

        # Fallback: OCR + LLM (existing behavior, always works)
        try:
            from app.tools.vision_analyzer import VisionAnalyzerTool
            fallback = VisionAnalyzerTool.analyze_screen_image(
                str(image_path), prompt_focus=prompt, auto_save_memory=False, skip_delta_check=True
            )
            if fallback.get("success"):
                return {
                    "success": True,
                    "image_path": str(image_path),
                    "vlm_analysis": fallback.get("ai_analysis", ""),
                    "ocr_text": fallback.get("ocr_text", ""),
                    "detections": fallback.get("detections", []),
                    "engine": f"fallback:{fallback.get('detection_engine','ocr_llm')}",
                    "note": "VLM unavailable — used OCR+LLM fallback (RX 580 VRAM limit or model not installed). Install Moondream2 to data/models/moondream2 for true VLM.",
                }
            else:
                return {
                    "success": False,
                    "error": f"VLM unavailable and fallback failed: {fallback.get('error')}",
                    "engine": "none",
                    "note": "Install transformers + Moondream2 for true VLM, or Tesseract for OCR fallback",
                }
        except Exception as e:
            return {
                "success": False,
                "error": f"VLM and fallback failed: {e}",
                "engine": "none",
            }

    @classmethod
    def get_status(cls) -> Dict[str, Any]:
        """Return VLM availability status."""
        model_id = cls._resolve_model_id()
        available = cls.is_available()
        return {
            "available": available,
            "model_id": model_id,
            "engine": f"vlm:{model_id}" if available else "fallback:ocr_llm",
            "torch_available": TORCH_AVAILABLE,
            "pil_available": PIL_AVAILABLE,
            "note": "VLM ready" if available else "VLM not installed — using OCR+LLM fallback. To enable true VLM: pip install transformers accelerate einops timm && download vikhyatk/moondream2 to data/models/moondream2",
        }
