import os
from pathlib import Path
from PIL import Image, ImageDraw, ImageFont
from typing import Dict, Any, Optional
from app.config import settings
from app.llm import llm_client, extract_reply
from app.utils.logger import app_logger, audit_logger

class MediaStudioTool:
    MEDIA_DIR = settings.DATA_DIR / "workspace" / "media"

    @classmethod
    def ensure_dir(cls):
        cls.MEDIA_DIR.mkdir(parents=True, exist_ok=True)

    @classmethod
    def generate_svg_graphic(cls, description: str, filename: Optional[str] = None) -> Dict[str, Any]:
        """
        Uses Qwen local LLM to generate clean, scalable SVG vector graphics, diagrams, or logos.
        """
        cls.ensure_dir()
        if not filename:
            filename = f"graphic_{description.lower().replace(' ', '_')[:20]}.svg"

        file_path = cls.MEDIA_DIR / filename

        system_prompt = (
            "You are an expert SVG Vector Designer. Generate clean, valid, standalone "
            "XML SVG graphic code without markdown backticks or explanations."
        )

        user_prompt = f"Generate standalone SVG code for: '{description}'. Ensure viewBox='0 0 800 600' and dark-mode styling."

        messages = [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt}
        ]

        try:
            llm_res = llm_client.generate_chat_completion(
                messages=messages,
                complexity="main",
                max_tokens=1000
            )

            raw_svg = extract_reply(llm_res, fallback="")
            clean_svg = raw_svg.replace("```xml", "").replace("```svg", "").replace("```", "").strip()

            if "<svg" not in clean_svg or "</svg>" not in clean_svg:
                return {
                    "success": False,
                    "available": not str(raw_svg).startswith("[Simulated Response"),
                    "error": "The model did not produce a valid SVG artifact; no fallback graphic was fabricated.",
                    "file_path": "",
                }

            with open(file_path, "w", encoding="utf-8") as f:
                f.write(clean_svg)

            audit_logger.info(f"Generated SVG graphic '{filename}' at {file_path}")

            return {
                "success": True,
                "description": description,
                "file_name": filename,
                "file_path": str(file_path),
                "svg_code": clean_svg,
                "file_url": f"/static/workspace/media/{filename}"
            }
        except Exception as e:
            app_logger.error(f"Error generating SVG graphic: {e}")
            return {"success": False, "error": str(e)}

    @classmethod
    def apply_image_watermark(cls, image_path_str: str, watermark_text: str = "CONFIDENTIAL") -> Dict[str, Any]:
        """
        Applies a subtle text watermark to an image using Pillow.
        """
        img_path = Path(image_path_str)
        if not img_path.is_absolute():
            img_path = settings.BASE_DIR / img_path

        if not img_path.exists():
            return {"success": False, "error": f"Image file not found: '{img_path}'"}

        try:
            img = Image.open(img_path).convert("RGBA")
            txt_img = Image.new("RGBA", img.size, (255, 255, 255, 0))
            draw = ImageDraw.Draw(txt_img)

            # Draw watermark
            w, h = img.size
            draw.text((w - 200, h - 50), watermark_text, fill=(0, 242, 254, 180))

            watermarked = Image.alpha_composite(img, txt_img)
            out_path = img_path.parent / f"watermarked_{img_path.name}"
            watermarked.convert("RGB").save(out_path)

            audit_logger.info(f"Watermarked image '{img_path.name}'")

            return {
                "success": True,
                "original_path": str(img_path),
                "watermarked_path": str(out_path),
                "watermark_text": watermark_text
            }
        except Exception as e:
            return {"success": False, "error": str(e)}
