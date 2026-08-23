from pathlib import Path
from typing import Dict, Any, Optional
from app.config import settings
from app.llm import llm_client, extract_reply, require_real_completion
from app.tools.ocr_reader import OCRReaderTool
from app.tools.screen_capture import ScreenCaptureTool
from app.tools.knowledge_indexer import KnowledgeIndexer
from app.utils.logger import app_logger

class VisionAnalyzerTool:
    @classmethod
    def analyze_screen_image(
        cls, 
        image_path_str: str, 
        prompt_focus: Optional[str] = None,
        complexity: str = "main",
        auto_save_memory: bool = True,
        skip_delta_check: bool = False,
    ) -> Dict[str, Any]:
        """
        Combines Tesseract OCR text extraction, object detection (YOLO/SSD/face),
        and Qwen local LLM analysis to understand active application windows,
        error messages, code UI, charts, or open forms.

        P1-1 AGI: Now also runs object detection + face detection and auto-creates
        language groundings so words like 'person', 'chair', 'face' become grounded
        to real visual features (perception→grounding loop).

        `skip_delta_check=True` analyzes the given image unconditionally (used for
        user-uploaded images via /vision/analyze). When False (the screen-observation
        path, /vision/capture-and-analyze), a screen-delta check first deduplicates
        identical frames to save VRAM.
        """
        image_path = Path(image_path_str)
        if not image_path.is_absolute():
            image_path = settings.BASE_DIR / image_path

        # Step 1: (screen-observation only) dedupe identical frames before spending
        # VRAM on a redundant inference. This must NOT run when analyzing an explicit
        # user-supplied image — the delta is computed against a fresh screen capture,
        # which is unrelated to the image being analyzed.
        if not skip_delta_check:
            cap_delta = ScreenCaptureTool.capture_screen_delta()
            if not cap_delta.get("screen_changed", True):
                app_logger.info("Screen unchanged (<5% delta); returning cached visual observation to save VRAM.")
                return {
                    "success": True,
                    "screen_changed": False,
                    "image_name": image_path.name,
                    "file_path": str(image_path),
                    "ai_analysis": "Desktop screen state is unchanged from previous observation frame. VLM inference skipped to conserve RX 580 VRAM.",
                    "note": "Skipped redundant VLM run on identical screen frame."
                }

        # Step 2: Try true VLM first (Moondream2 / Llava-Phi) if available — true visual understanding
        # If not available, degrade to OCR+LLM (existing behavior). This is P2 VLM integration that is safe.
        vlm_res = None
        try:
            from app.tools.vlm_analyzer import VlmAnalyzerTool
            if VlmAnalyzerTool.is_available():
                vlm_prompt = prompt_focus or "Describe this image in detail, including objects, text, UI elements, and what the user should do next."
                vlm_res = VlmAnalyzerTool.analyze_image(str(image_path), prompt=vlm_prompt)
                if vlm_res.get("success"):
                    # Also run object detection for grounding (even with VLM)
                    detections = []
                    groundings_created = []
                    detection_engine = vlm_res.get("engine", "vlm")
                    try:
                        from app.tools.object_detector import ObjectDetectorTool
                        det_res = ObjectDetectorTool.analyze_image_grounded(str(image_path), auto_create_groundings=True)
                        if det_res.get("success"):
                            detections = det_res.get("detections", [])
                            groundings_created = det_res.get("groundings_created", [])
                    except Exception:
                        pass

                    res = {
                        "success": True,
                        "image_name": image_path.name,
                        "file_path": str(image_path),
                        "ocr_text": vlm_res.get("ocr_text", ""),
                        "detections": detections,
                        "detection_engine": detection_engine,
                        "groundings_created": groundings_created,
                        "ai_analysis": vlm_res.get("vlm_analysis", ""),
                        "vlm_analysis": vlm_res.get("vlm_analysis", ""),
                        "engine": vlm_res.get("engine", "vlm"),
                    }
                    if auto_save_memory and res.get("ai_analysis"):
                        from app.tools.knowledge_indexer import KnowledgeIndexer
                        mem_content = f"👁️ [VLM VISION :: {image_path.name}]\n\n{res['ai_analysis']}\n\nDetections: {detections}"
                        mem_id = KnowledgeIndexer.index_doc_knowledge(
                            {"success": True, "file_name": image_path.name, "file_path": str(image_path)},
                            mem_content,
                            category="desktop_vision"
                        )
                        res["memory_id"] = mem_id
                    return res
                else:
                    app_logger.info(f"VLM degraded: {vlm_res.get('error')} — falling back to OCR+LLM")
        except Exception as e:
            app_logger.warning(f"VLM integration failed (best-effort, falling back to OCR+LLM): {e}")

        # Step 2 fallback: Run OCR Text Extraction (existing behavior)
        ocr_res = OCRReaderTool.extract_text_from_image(str(image_path))
        extracted_text = ocr_res.get("extracted_text", "")

        # Step 2b: P1-1 — Object + face detection + auto-grounding (closes perception→grounding loop)
        detections = []
        groundings_created = []
        detection_engine = "none"
        try:
            from app.tools.object_detector import ObjectDetectorTool
            det_res = ObjectDetectorTool.analyze_image_grounded(str(image_path), auto_create_groundings=True)
            if det_res.get("success"):
                detections = det_res.get("detections", [])
                groundings_created = det_res.get("groundings_created", [])
                detection_engine = det_res.get("engine", "unknown")
            else:
                app_logger.info(f"Object detection degraded: {det_res.get('error')}")
        except Exception as e:
            app_logger.warning(f"Object detection integration failed (best-effort): {e}")

        focus_str = f" Focus specifically on: '{prompt_focus}'." if prompt_focus else ""

        # Build detection summary for LLM
        det_summary = ""
        if detections:
            det_lines = [f"- {d.get('label')} (conf {d.get('confidence',0):.2f}) at {d.get('bbox')}" for d in detections[:20]]
            det_summary = "\nDetected objects (grounded to vision):\n" + "\n".join(det_lines) + "\n"

        system_prompt = (
            "You are an AI desktop vision analyst. Your job is to analyze desktop "
            "screenshots, active application states, UI controls, and error messages. "
            "You have access to grounded object detections (real visual features, not hallucinated)."
        )

        user_prompt = f"""
Analyze the following desktop screen observation (Image: {image_path.name}).{focus_str}

Extracted OCR Screen Text:
\"\"\"
{extracted_text if extracted_text else '[No OCR text extracted directly from image - analyze general screen context]' }
\"\"\"
{det_summary}
Please provide:
1. **Active Application & Window Overview**: What application or window is open?
2. **Key Visible Information / Error Messages**: Core text, code, or dialog messages visible.
3. **Detected Objects**: What objects/faces were grounded (from detection, not hallucinated)?
4. **Actionable Assistant Next Step**: What action should the user or assistant take based on this screen state?
"""

        messages = [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt}
        ]

        try:
            llm_res = llm_client.generate_chat_completion(
                messages=messages,
                complexity=complexity,
                max_tokens=600
            )

            ai_analysis = require_real_completion(llm_res)

            res = {
                "success": True,
                "image_name": image_path.name,
                "file_path": str(image_path),
                "ocr_text": extracted_text,
                "detections": detections,
                "detection_engine": detection_engine,
                "groundings_created": groundings_created,
                "ai_analysis": ai_analysis
            }

            if auto_save_memory and ai_analysis:
                mem_content = f"👁️ [DESKTOP VISION OBSERVATION :: {image_path.name}]\n\n{ai_analysis}\n\nDetections: {detections}"
                mem_id = KnowledgeIndexer.index_doc_knowledge(
                    {"success": True, "file_name": image_path.name, "file_path": str(image_path)},
                    mem_content,
                    category="desktop_vision"
                )
                res["memory_id"] = mem_id

            return res
        except Exception as e:
            app_logger.error(f"Error in vision analysis: {e}")
            return {
                "success": False,
                "error": f"Vision analysis error: {str(e)}",
                "image_name": image_path.name,
                "file_path": str(image_path),
                "ocr_text": extracted_text,
                "detections": detections,
                "ai_analysis": ""
            }
