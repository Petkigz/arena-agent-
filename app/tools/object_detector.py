"""Object detection + face detection — deterministic, local, degradable.

This closes the perception → grounding loop (P1-1 of AGI human audit):
human intelligence grounds words like "chair" to what it sees. Previously
language_grounding stored groundings but never created them from live perception.

Now:
- Face detection via OpenCV Haar cascades (always available offline, no model download)
- General object detection via YOLO (ultralytics) if installed, else MobileNet SSD via OpenCV DNN if model files exist in data/models, else graceful degradation (face-only)

Every method returns typed {success: bool, ...} dict, never raises.
"""

from __future__ import annotations

import os
from pathlib import Path
from typing import Any, Dict, List, Optional

from app.config import settings
from app.utils.logger import app_logger

try:
    import cv2
    CV2_AVAILABLE = True
except ImportError:
    cv2 = None
    CV2_AVAILABLE = False

# YOLO via ultralytics is optional — may not be installed on low-spec hardware
try:
    from ultralytics import YOLO  # type: ignore
    YOLO_AVAILABLE = True
except ImportError:
    YOLO = None
    YOLO_AVAILABLE = False


class ObjectDetectorTool:
    """Deterministic local object + face detector."""

    # Face cascade — ships with opencv-python
    _face_cascade: Optional[Any] = None
    _yolo_model: Optional[Any] = None
    _ssd_net: Optional[Any] = None
    _ssd_labels: List[str] = []

    @classmethod
    def _ensure_face_cascade(cls):
        if not CV2_AVAILABLE:
            return None
        if cls._face_cascade is not None:
            return cls._face_cascade
        try:
            # Try common locations for haarcascade
            candidates = [
                Path(cv2.data.haarcascades) / "haarcascade_frontalface_default.xml" if hasattr(cv2, "data") else None,
                Path("/usr/share/opencv4/haarcascades/haarcascade_frontalface_default.xml"),
                Path("/usr/share/opencv/haarcascades/haarcascade_frontalface_default.xml"),
            ]
            for p in candidates:
                if p and p.exists():
                    cascade = cv2.CascadeClassifier(str(p))
                    if not cascade.empty():
                        cls._face_cascade = cascade
                        app_logger.info(f"Face cascade loaded from {p}")
                        return cascade
            # Fallback: let OpenCV try to load by name (may work if data path set)
            cascade = cv2.CascadeClassifier("haarcascade_frontalface_default.xml")
            if not cascade.empty():
                cls._face_cascade = cascade
                return cascade
            app_logger.warning("Face cascade not found — face detection unavailable")
            return None
        except Exception as e:
            app_logger.warning(f"Could not load face cascade: {e}")
            return None

    @classmethod
    def _ensure_yolo(cls):
        if not YOLO_AVAILABLE:
            return None
        if cls._yolo_model is not None:
            return cls._yolo_model
        try:
            # Try to load yolov8n or yolov5n from data/models or cache
            model_paths = [
                settings.DATA_DIR / "models" / "yolov8n.pt",
                settings.DATA_DIR / "models" / "yolov5n.pt",
                Path("yolov8n.pt"),
                Path("yolov5n.pt"),
            ]
            for mp in model_paths:
                if mp.exists():
                    model = YOLO(str(mp))
                    cls._yolo_model = model
                    app_logger.info(f"YOLO model loaded from {mp}")
                    return model
            # Try to load by name (ultralytics will download if internet available, else fail gracefully)
            # We attempt but catch download failure — offline should not crash
            try:
                model = YOLO("yolov8n.pt")
                cls._yolo_model = model
                app_logger.info("YOLO yolov8n.pt loaded (may have downloaded)")
                return model
            except Exception:
                app_logger.info("YOLO model not found locally and download unavailable — using face-only fallback")
                return None
        except Exception as e:
            app_logger.warning(f"Could not load YOLO model: {e}")
            return None

    @classmethod
    def _ensure_ssd(cls):
        if not CV2_AVAILABLE:
            return None
        if cls._ssd_net is not None:
            return cls._ssd_net
        try:
            # MobileNet SSD Caffe model — optional, lives in data/models if owner downloaded
            model_dir = settings.DATA_DIR / "models"
            prototxt_candidates = [
                model_dir / "MobileNetSSD_deploy.prototxt",
                Path("models/MobileNetSSD_deploy.prototxt"),
            ]
            caffemodel_candidates = [
                model_dir / "MobileNetSSD_deploy.caffemodel",
                Path("models/MobileNetSSD_deploy.caffemodel"),
            ]
            prototxt = next((p for p in prototxt_candidates if p.exists()), None)
            caffemodel = next((p for p in caffemodel_candidates if p.exists()), None)
            if not prototxt or not caffemodel:
                return None
            net = cv2.dnn.readNetFromCaffe(str(prototxt), str(caffemodel))
            cls._ssd_net = net
            cls._ssd_labels = [
                "background", "aeroplane", "bicycle", "bird", "boat", "bottle", "bus", "car", "cat",
                "chair", "cow", "diningtable", "dog", "horse", "motorbike", "person", "pottedplant",
                "sheep", "sofa", "train", "tvmonitor"
            ]
            app_logger.info(f"MobileNet SSD loaded from {prototxt} + {caffemodel}")
            return net
        except Exception as e:
            app_logger.warning(f"Could not load SSD model: {e}")
            return None

    @classmethod
    def detect_faces(cls, image_path_str: str) -> Dict[str, Any]:
        """Detect faces via Haar cascade."""
        if not CV2_AVAILABLE:
            return {"success": False, "error": "OpenCV not installed", "faces": []}

        image_path = Path(image_path_str)
        if not image_path.is_absolute():
            image_path = settings.BASE_DIR / image_path

        if not image_path.exists():
            return {"success": False, "error": f"Image not found: {image_path}", "faces": []}

        cascade = cls._ensure_face_cascade()
        if cascade is None:
            return {"success": False, "error": "Face cascade unavailable", "faces": []}

        try:
            img = cv2.imread(str(image_path))
            if img is None:
                return {"success": False, "error": f"Could not read image: {image_path}", "faces": []}

            gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
            faces = cascade.detectMultiScale(gray, scaleFactor=1.1, minNeighbors=5, minSize=(30, 30))

            detections = []
            for (x, y, w, h) in faces:
                detections.append({
                    "label": "face",
                    "confidence": 0.9,
                    "bbox": {"x": int(x), "y": int(y), "width": int(w), "height": int(h)},
                    "center": {"x": int(x + w/2), "y": int(y + h/2)},
                })

            return {
                "success": True,
                "image_path": str(image_path),
                "faces": detections,
                "count": len(detections),
            }
        except Exception as e:
            app_logger.error(f"Face detection error: {e}")
            return {"success": False, "error": f"Face detection error: {e}", "faces": []}

    @classmethod
    def detect_objects(cls, image_path_str: str, conf_threshold: float = 0.5) -> Dict[str, Any]:
        """Detect general objects via YOLO > SSD > face-only fallback."""
        if not CV2_AVAILABLE:
            return {"success": False, "error": "OpenCV not installed", "detections": []}

        image_path = Path(image_path_str)
        if not image_path.is_absolute():
            image_path = settings.BASE_DIR / image_path

        if not image_path.exists():
            return {"success": False, "error": f"Image not found: {image_path}", "detections": []}

        # Try YOLO first
        yolo = cls._ensure_yolo()
        if yolo is not None:
            try:
                results = yolo(str(image_path), verbose=False)
                detections = []
                for r in results:
                    boxes = r.boxes
                    if boxes is None:
                        continue
                    for box in boxes:
                        conf = float(box.conf[0]) if hasattr(box, "conf") else 0.0
                        if conf < conf_threshold:
                            continue
                        cls_id = int(box.cls[0]) if hasattr(box, "cls") else 0
                        label = r.names.get(cls_id, f"class_{cls_id}") if hasattr(r, "names") else f"class_{cls_id}"
                        xyxy = box.xyxy[0].tolist() if hasattr(box, "xyxy") else [0, 0, 0, 0]
                        x1, y1, x2, y2 = map(int, xyxy)
                        detections.append({
                            "label": str(label),
                            "confidence": conf,
                            "bbox": {"x": x1, "y": y1, "width": x2 - x1, "height": y2 - y1},
                            "center": {"x": (x1 + x2)//2, "y": (y1 + y2)//2},
                        })
                # Also add faces
                face_res = cls.detect_faces(str(image_path))
                if face_res.get("success"):
                    detections.extend(face_res.get("faces", []))

                return {
                    "success": True,
                    "image_path": str(image_path),
                    "detections": detections,
                    "count": len(detections),
                    "engine": "yolo",
                }
            except Exception as e:
                app_logger.warning(f"YOLO detection failed, falling back: {e}")

        # Try MobileNet SSD
        ssd = cls._ensure_ssd()
        if ssd is not None:
            try:
                img = cv2.imread(str(image_path))
                if img is None:
                    return {"success": False, "error": f"Could not read image: {image_path}", "detections": []}

                h, w = img.shape[:2]
                blob = cv2.dnn.blobFromImage(cv2.resize(img, (300, 300)), 0.007843, (300, 300), 127.5)
                ssd.setInput(blob)
                detections_raw = ssd.forward()

                detections = []
                for i in range(detections_raw.shape[2]):
                    conf = float(detections_raw[0, 0, i, 2])
                    if conf < conf_threshold:
                        continue
                    cls_id = int(detections_raw[0, 0, i, 1])
                    label = cls._ssd_labels[cls_id] if cls_id < len(cls._ssd_labels) else f"class_{cls_id}"
                    box = detections_raw[0, 0, i, 3:7] * [w, h, w, h]
                    x1, y1, x2, y2 = map(int, box)
                    detections.append({
                        "label": str(label),
                        "confidence": conf,
                        "bbox": {"x": x1, "y": y1, "width": x2 - x1, "height": y2 - y1},
                        "center": {"x": (x1 + x2)//2, "y": (y1 + y2)//2},
                    })

                face_res = cls.detect_faces(str(image_path))
                if face_res.get("success"):
                    detections.extend(face_res.get("faces", []))

                return {
                    "success": True,
                    "image_path": str(image_path),
                    "detections": detections,
                    "count": len(detections),
                    "engine": "mobilenet_ssd",
                }
            except Exception as e:
                app_logger.warning(f"SSD detection failed, falling back to face-only: {e}")

        # Fallback: face-only (always works offline)
        face_res = cls.detect_faces(str(image_path))
        if face_res.get("success"):
            return {
                "success": True,
                "image_path": str(image_path),
                "detections": face_res.get("faces", []),
                "count": face_res.get("count", 0),
                "engine": "face_only",
                "note": "General object model not found — face-only detection. Download YOLOv8n.pt or MobileNetSSD to data/models/ for full detection.",
            }

        return {
            "success": False,
            "error": "No detection engine available (OpenCV missing cascade)",
            "detections": [],
            "engine": "none",
        }

    @classmethod
    def analyze_image_grounded(cls, image_path_str: str, auto_create_groundings: bool = True) -> Dict[str, Any]:
        """Detect objects + optionally create language groundings (closes perception→grounding loop).

        This is the AGI P1-1 integration: every detected label automatically creates
        a PerceptualGrounding so words like 'chair' become grounded to real visual features.
        """
        det_res = cls.detect_objects(image_path_str)
        if not det_res.get("success"):
            return det_res

        detections = det_res.get("detections", [])
        groundings_created = []

        if auto_create_groundings and detections:
            try:
                from app.cognition.runtime import CognitiveRuntime
                from app.cognition.language_grounding import SymbolType

                runtime = CognitiveRuntime.get_instance()
                lg = runtime.language_grounding

                for det in detections:
                    label = det.get("label", "unknown")
                    conf = det.get("confidence", 0.5)
                    bbox = det.get("bbox", {})
                    try:
                        # Create perceptual grounding for each detected label
                        grounding = lg.create_perceptual_grounding(
                            symbol=label,
                            modality="vision",
                            perceptual_features={
                                "confidence": conf,
                                "bbox_x": float(bbox.get("x", 0)),
                                "bbox_y": float(bbox.get("y", 0)),
                                "bbox_w": float(bbox.get("width", 0)),
                                "bbox_h": float(bbox.get("height", 0)),
                                "center_x": float(det.get("center", {}).get("x", 0)),
                                "center_y": float(det.get("center", {}).get("y", 0)),
                            },
                            sensory_experience=f"Saw {label} at ({bbox.get('x')},{bbox.get('y')}) size {bbox.get('width')}x{bbox.get('height')} in {image_path_str}",
                            symbol_type=SymbolType.WORD,
                            confidence=conf,
                            examples=[image_path_str],
                        )
                        groundings_created.append(grounding.grounding_id)

                        # If face detected, also feed social cognition with emotion hint
                        if label == "face":
                            try:
                                from app.cognition.social_cognition import Emotion
                                # Simple heuristic: face present → neutral with low intensity, unless other cues
                                runtime.social_cognition.recognize_emotion(
                                    agent_id="observed_person",
                                    primary_emotion=Emotion.NEUTRAL,
                                    intensity=0.3,
                                    triggers=[f"face detected in {image_path_str}"],
                                )
                            except Exception:
                                pass

                    except Exception as e:
                        app_logger.warning(f"Could not create grounding for {label}: {e}")

            except Exception as e:
                app_logger.warning(f"Grounding creation failed (best-effort): {e}")

        det_res["groundings_created"] = groundings_created
        det_res["groundings_count"] = len(groundings_created)
        return det_res
