import os
import shutil
import zipfile
import subprocess
from pathlib import Path
from typing import Dict, Any, List, Optional
from app.config import settings
from app.policy import PolicyEvaluator
from app.utils.logger import app_logger, audit_logger

class UniversalFilesystem:
    @staticmethod
    def _sha256(path: Path) -> str:
        import hashlib
        digest=hashlib.sha256()
        with path.open('rb') as handle:
            for chunk in iter(lambda:handle.read(1024*1024),b''):digest.update(chunk)
        return digest.hexdigest()

    @classmethod
    def copy_file_verified(cls, source_path: str, destination_path: str) -> Dict[str, Any]:
        src,dst=Path(source_path),Path(destination_path)
        if not src.is_file():return {"success":False,"error":"Source file not found"}
        if dst.exists():return {"success":False,"error":"Destination already exists; refusing overwrite"}
        before=cls._sha256(src)
        try:dst.parent.mkdir(parents=True,exist_ok=True);shutil.copy2(src,dst)
        except Exception as exc:return {"success":False,"error":str(exc)}
        after=cls._sha256(dst) if dst.is_file() else None;verified=before==after
        return {"success":verified,"source_path":str(src),"destination_path":str(dst),"source_sha256":before,"destination_sha256":after,"environment_verified":verified,"side_effects":dst.exists(),"rollback_path":str(dst),"rollback_sha256":after}

    @classmethod
    def remove_verified_copy(cls, file_path: str, expected_sha256: str) -> Dict[str, Any]:
        path=Path(file_path)
        if not path.is_file():return {"success":False,"error":"Rollback target is missing"}
        actual=cls._sha256(path)
        if actual!=expected_sha256:return {"success":False,"error":"Rollback target hash changed; refusing deletion","actual_sha256":actual}
        path.unlink();verified=not path.exists()
        return {"success":verified,"removed_path":str(path),"expected_sha256":expected_sha256,"environment_verified":verified,"side_effects":verified,"rollback_supported":False}

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
        if dst.exists():
            return {"success": False, "error": f"Destination already exists; refusing overwrite: '{dst}'"}

        try:
            import hashlib
            source_sha256 = hashlib.sha256(src.read_bytes()).hexdigest() if src.is_file() else None
            dst.parent.mkdir(parents=True, exist_ok=True)
            shutil.move(str(src), str(dst))
            verified = dst.exists() and not src.exists()
            destination_sha256 = hashlib.sha256(dst.read_bytes()).hexdigest() if dst.is_file() else None
            if source_sha256 and destination_sha256 != source_sha256:
                return {"success": False, "error": "Move completed but content hash verification failed", "side_effects": True}
            audit_logger.info(f"Moved/Renamed '{src.name}' -> '{dst.name}'")
            return {
                "success": verified,
                "old_path": str(src),
                "new_path": str(dst),
                "source_sha256": source_sha256,
                "destination_sha256": destination_sha256,
                "environment_verified": verified,
                "side_effects": verified,
                "rollback_source": str(dst),
                "rollback_destination": str(src),
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
        sources=[Path(item) for item in (source_paths or [])]
        if not sources:return {"success":False,"error":"At least one source path is required"}
        missing=[str(path) for path in sources if not path.exists()]
        if missing:return {"success":False,"error":"One or more sources are missing","missing":missing}
        if zip_path.exists():return {"success":False,"error":"Output archive already exists; refusing overwrite"}
        manifest=[]
        try:
            zip_path.parent.mkdir(parents=True, exist_ok=True)
            with zipfile.ZipFile(zip_path, 'w', zipfile.ZIP_DEFLATED) as zipf:
                for p in sources:
                    if p.is_file():
                        zipf.write(p, p.name);manifest.append({"path":str(p),"sha256":cls._sha256(p)})
                    elif p.is_dir():
                        for root, _, files in os.walk(p):
                            for f in files:
                                file_p = Path(root) / f
                                zipf.write(file_p, file_p.relative_to(p.parent));manifest.append({"path":str(file_p),"sha256":cls._sha256(file_p)})
            with zipfile.ZipFile(zip_path,'r') as archive:bad=archive.testzip()
            archive_hash=cls._sha256(zip_path);verified=bad is None and bool(manifest)
            audit_logger.info(f"Compressed {len(source_paths)} items into ZIP archive: {zip_path.name}")
            return {
                "success": verified,"zip_path": str(zip_path),"zip_name": zip_path.name,
                "size_bytes": zip_path.stat().st_size,"archive_sha256":archive_hash,
                "source_manifest":manifest,"environment_verified":verified,"side_effects":True,
                "rollback_path":str(zip_path),"rollback_sha256":archive_hash
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
            from PIL import Image
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
