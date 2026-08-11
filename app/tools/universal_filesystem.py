import os
import shutil
import zipfile
import subprocess
from pathlib import Path
from PIL import Image
from typing import Dict, Any, List, Optional
from app.config import settings
from app.policy import PolicyEvaluator
from app.utils.logger import app_logger, audit_logger

class UniversalFilesystem:
    @classmethod
    def search_filesystem(cls, query: str, root_dir: Optional[str] = None, max_results: int = 20) -> List[Dict[str, Any]]:
        """
        Searches all directories for files matching query string across filesystem.
        """
        query_lower = query.lower().strip()
        search_root = Path(root_dir) if root_dir else settings.BASE_DIR
        matched_files = []

        try:
            for root, _, files in os.walk(search_root):
                for f in files:
                    if query_lower in f.lower():
                        p = Path(root) / f
                        matched_files.append({
                            "file_name": f,
                            "file_path": str(p),
                            "size_bytes": p.stat().st_size,
                            "extension": p.suffix.lower()
                        })
                        if len(matched_files) >= max_results:
                            break
                if len(matched_files) >= max_results:
                    break
        except Exception as e:
            app_logger.warning(f"Error during filesystem search: {e}")

        return matched_files

    @classmethod
    def rename_or_move(cls, source_path_str: str, destination_path_str: str) -> Dict[str, Any]:
        """
        Renames or moves any file or folder across the filesystem.
        """
        src = Path(source_path_str)
        dst = Path(destination_path_str)

        if not src.exists():
            return {"success": False, "error": f"Source file/folder not found: '{src}'"}

        try:
            dst.parent.mkdir(parents=True, exist_ok=True)
            shutil.move(str(src), str(dst))
            audit_logger.info(f"Moved/Renamed '{src.name}' -> '{dst.name}'")
            return {
                "success": True,
                "old_path": str(src),
                "new_path": str(dst),
                "message": f"Successfully moved '{src.name}' to '{dst.name}'."
            }
        except Exception as e:
            app_logger.error(f"Error moving file: {e}")
            return {"success": False, "error": str(e)}

    @classmethod
    def compress_zip(cls, source_paths: List[str], output_zip_path_str: str) -> Dict[str, Any]:
        """
        Compresses files or folders into a ZIP archive.
        """
        zip_path = Path(output_zip_path_str)
        try:
            zip_path.parent.mkdir(parents=True, exist_ok=True)
            with zipfile.ZipFile(zip_path, 'w', zipfile.ZIP_DEFLATED) as zipf:
                for p_str in source_paths:
                    p = Path(p_str)
                    if p.is_file():
                        zipf.write(p, p.name)
                    elif p.is_dir():
                        for root, _, files in os.walk(p):
                            for f in files:
                                file_p = Path(root) / f
                                zipf.write(file_p, file_p.relative_to(p.parent))

            audit_logger.info(f"Compressed {len(source_paths)} items into ZIP archive: {zip_path.name}")
            return {
                "success": True,
                "zip_path": str(zip_path),
                "zip_name": zip_path.name,
                "size_bytes": zip_path.stat().st_size
            }
        except Exception as e:
            return {"success": False, "error": str(e)}

    @classmethod
    def resize_image(cls, image_path_str: str, target_width: int, target_height: int) -> Dict[str, Any]:
        """
        Resizes an image file (.jpg, .png, .webp) to specified width and height.
        """
        img_path = Path(image_path_str)
        if not img_path.exists():
            return {"success": False, "error": f"Image file not found: '{img_path}'"}

        try:
            img = Image.open(img_path)
            resized_img = img.resize((target_width, target_height), Image.Resampling.LANCZOS)
            output_path = img_path.parent / f"resized_{img_path.name}"
            resized_img.save(output_path)

            audit_logger.info(f"Resized image '{img_path.name}' to {target_width}x{target_height}")
            return {
                "success": True,
                "original_path": str(img_path),
                "resized_path": str(output_path),
                "new_width": target_width,
                "new_height": target_height
            }
        except Exception as e:
            return {"success": False, "error": str(e)}

    @classmethod
    def play_media_file(cls, media_path_str: str) -> Dict[str, Any]:
        """
        Launches default OS media player to play audio or video files (.mp3, .wav, .mp4, .mkv).
        """
        media_path = Path(media_path_str)
        if not media_path.exists():
            return {"success": False, "error": f"Media file not found: '{media_path}'"}

        try:
            if os.name == 'nt':
                os.startfile(str(media_path))
            elif sys.platform == 'darwin':
                subprocess.Popen(['open', str(media_path)])
            else:
                subprocess.Popen(['xdg-open', str(media_path)])

            audit_logger.info(f"Launched media playback for '{media_path.name}'")
            return {"success": True, "file_name": media_path.name, "message": f"Playing media file '{media_path.name}'."}
        except Exception as e:
            return {"success": False, "error": str(e)}
