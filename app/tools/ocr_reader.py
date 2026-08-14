import pytesseract
from PIL import Image
from pathlib import Path
from typing import Dict, Any, Optional
from app.config import settings
from app.utils.logger import app_logger

class OCRReaderTool:
    @classmethod
    def extract_text_from_image(cls, image_path_str: str) -> Dict[str, Any]:
        """
        Uses PIL and Tesseract OCR to extract text, error messages, labels, and code from any image.
        """
        image_path = Path(image_path_str)
        if not image_path.is_absolute():
            image_path = settings.BASE_DIR / image_path

        if not image_path.exists():
            return {
                "success": False,
                "error": f"Image file not found: '{image_path}'",
                "extracted_text": "",
                "word_count": 0
            }

        try:
            img = Image.open(image_path)
            extracted_text = pytesseract.image_to_string(img)
            clean_text = extracted_text.strip()

            return {
                "success": True,
                "image_name": image_path.name,
                "file_path": str(image_path),
                "extracted_text": clean_text,
                "word_count": len(clean_text.split())
            }
        except Exception as e:
            app_logger.warning(f"Tesseract OCR error on image '{image_path.name}': {e}")
            # Fallback when Tesseract binary is not installed on system path
            return {
                "success": False,
                "error": f"OCR extraction notice: Tesseract OCR binary not found on system PATH. Install Tesseract OCR on PC or use Vision LLM. Error: {str(e)}",
                "extracted_text": "",
                "word_count": 0
            }
