from pathlib import Path
from typing import Dict, Any, Optional
from app.config import settings
from app.llm import llm_client
from app.tools.ocr_reader import OCRReaderTool
from app.tools.knowledge_indexer import KnowledgeIndexer
from app.utils.logger import app_logger

class VisionAnalyzerTool:
    @classmethod
    def analyze_screen_image(
        cls, 
        image_path_str: str, 
        prompt_focus: Optional[str] = None,
        complexity: str = "main",
        auto_save_memory: bool = True
    ) -> Dict[str, Any]:
        """
        Combines Tesseract OCR text extraction and Qwen local LLM analysis to understand
        active application windows, error messages, code UI, charts, or open forms.
        """
        image_path = Path(image_path_str)
        if not image_path.is_absolute():
            image_path = settings.BASE_DIR / image_path

        # Step 1: Run OCR Text Extraction
        ocr_res = OCRReaderTool.extract_text_from_image(str(image_path))
        extracted_text = ocr_res.get("extracted_text", "")

        focus_str = f" Focus specifically on: '{prompt_focus}'." if prompt_focus else ""

        system_prompt = (
            "You are an AI desktop vision analyst. Your job is to analyze desktop "
            "screenshots, active application states, UI controls, and error messages."
        )

        user_prompt = f"""
Analyze the following desktop screen observation (Image: {image_path.name}).{focus_str}

Extracted OCR Screen Text:
\"\"\"
{extracted_text if extracted_text else '[No OCR text extracted directly from image - analyze general screen context]' }
\"\"\"

Please provide:
1. **Active Application & Window Overview**: What application or window is open?
2. **Key Visible Information / Error Messages**: Core text, code, or dialog messages visible.
3. **Actionable Assistant Next Step**: What action should the user or assistant take based on this screen state?
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

            ai_analysis = "No visual analysis generated."
            if llm_res.get("choices") and len(llm_res["choices"]) > 0:
                ai_analysis = llm_res["choices"][0]["message"]["content"]

            res = {
                "success": True,
                "image_name": image_path.name,
                "file_path": str(image_path),
                "ocr_text": extracted_text,
                "ai_analysis": ai_analysis
            }

            if auto_save_memory and ai_analysis:
                mem_content = f"👁️ [DESKTOP VISION OBSERVATION :: {image_path.name}]\n\n{ai_analysis}"
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
                "ai_analysis": ""
            }
