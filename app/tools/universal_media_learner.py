import os
import re
import uuid
from typing import Dict, Any, List, Optional
import httpx
from bs4 import BeautifulSoup
from app.config import settings
from app.database import db
from app.utils.logger import app_logger
from app.perception.speech_to_text import LocalSpeechToText
from app.tools.ocr_reader import OCRReaderTool
from app.tools.youtube_learner import YouTubeLearner
from app.llm import llm_client, extract_reply
from app.cognition.execution_control import (
    ExecutionCancelled,
    run_cancellable_blocking_call,
)

class UniversalMediaLearner:
    """
    Universal Video, Media & Ad Analyzer Engine.
    Processes video links (YouTube, Vimeo, Twitch, news, MP4/WEBM direct URLs),
    embedded web video ads, local video files, and video banner graphics across all platforms.
    """

    @staticmethod
    def _extract_video_urls_from_webpage(url: str) -> Dict[str, Any]:
        """
        Scrapes a web page to extract embedded HTML5 <video>, <source>, <iframe> video tags, or ad media.
        """
        try:
            resp = run_cancellable_blocking_call(
                lambda: httpx.get(
                    url,
                    timeout=10.0,
                    follow_redirects=True,
                    headers={"User-Agent": "Mozilla/5.0"},
                ),
                description="media page HTTP request",
            )
            soup = BeautifulSoup(resp.text, "html.parser")

            video_sources = []
            iframe_sources = []
            ad_elements = []

            # Extract <video> and <source> tags
            for v in soup.find_all("video"):
                src = v.get("src")
                if src:
                    video_sources.append(src)
                for s in v.find_all("source"):
                    if s.get("src"):
                        video_sources.append(s.get("src"))

            # Extract video iframes (Vimeo, YouTube embeds, custom players)
            for iframe in soup.find_all("iframe"):
                src = iframe.get("src", "")
                if any(k in src for k in ["youtube", "vimeo", "twitch", "player", "video", "embed"]):
                    iframe_sources.append(src)

            # Extract ad container texts/links
            for ad in soup.find_all(class_=re.compile(r"ad|banner|sponsor|promo", re.I)):
                ad_elements.append(ad.get_text(strip=True)[:200])

            page_title = soup.title.string.strip() if soup.title else "Web Media Page"

            return {
                "success": True,
                "title": page_title,
                "video_sources": list(set(video_sources)),
                "iframe_sources": list(set(iframe_sources)),
                "ad_elements": list(set(ad_elements))[:5],
                "page_text_snippet": soup.get_text(separator=" ", strip=True)[:1500]
            }
        except ExecutionCancelled:
            raise
        except Exception as e:
            app_logger.error(f"Error scraping webpage media: {e}")
            return {"success": False, "error": str(e)}

    @staticmethod
    def analyze_media_target(
        target_url_or_path: str,
        prompt_focus: Optional[str] = None
    ) -> Dict[str, Any]:
        """
        Universal entry point to analyze YouTube links, external video platforms, HTML5 web videos,
        embedded ads, or local video media files.
        """
        target = target_url_or_path.strip()

        # 1. Handle YouTube URLs using YouTubeLearner
        if "youtube.com" in target or "youtu.be" in target:
            app_logger.info(f"Delegating to YouTubeLearner for target: {target}")
            yt_res = YouTubeLearner.learn_from_video(target, prompt_focus=prompt_focus)
            yt_res["platform_type"] = "YouTube"
            return yt_res

        # 2. Handle Local Video / Media File Paths (.mp4, .mkv, .webm, .avi, .wav)
        if os.path.exists(target) and os.path.isfile(target):
            app_logger.info(f"Processing local media file: {target}")
            stt_res = LocalSpeechToText.transcribe_file(target)
            transcript_text = stt_res.get("text", "")

            summary_prompt = (
                f"Analyze this local video transcript ({os.path.basename(target)}):\n\n"
                f"{transcript_text[:6000]}\n\n"
                f"Provide: 1) Executive Takeaways, 2) Step-by-Step Checklist, 3) Key Terms & Concepts."
            )
            if prompt_focus:
                summary_prompt += f"\nSpecial Focus: {prompt_focus}"

            llm_res = llm_client.generate_chat_completion(
                messages=[{"role": "user", "content": summary_prompt}],
                complexity="main",
                max_tokens=600
            )
            analysis = extract_reply(llm_res, fallback="Media transcript analyzed.")

            db.create_audit_log("analyze_media_target", "success", f"Analyzed local media file: {os.path.basename(target)}", level=0)

            return {
                "success": True,
                "platform_type": "Local Video/Audio File",
                "title": os.path.basename(target),
                "transcript_snippet": transcript_text[:500],
                "ai_analysis": analysis,
                "file_path": target
            }

        # 3. Handle External Web Page / Video Ad / Web Player
        app_logger.info(f"Analyzing external web media page / ad target: {target}")
        web_media = UniversalMediaLearner._extract_video_urls_from_webpage(target)

        analysis_prompt = (
            f"Analyze this web page, video player, and video ad content from target URL: {target}\n"
            f"Page Title: {web_media.get('title', 'Unknown')}\n"
            f"Embedded Videos Found: {web_media.get('video_sources', [])}\n"
            f"Video Iframes Found: {web_media.get('iframe_sources', [])}\n"
            f"Ad Elements Found: {web_media.get('ad_elements', [])}\n\n"
            f"Page Text Content:\n{web_media.get('page_text_snippet', '')[:4000]}\n\n"
            f"Extract key concepts, marketing/ad strategy, video key points, and actionable takeaways."
        )
        if prompt_focus:
            analysis_prompt += f"\nFocus area: {prompt_focus}"

        llm_res = llm_client.generate_chat_completion(
            messages=[{"role": "user", "content": analysis_prompt}],
            complexity="main",
            max_tokens=700
        )
        ai_summary = extract_reply(llm_res, fallback="Web media analyzed.")

        db.create_memory({
            "content": f"Universal Media Analysis ({web_media.get('title')}): {ai_summary[:300]}",
            "category": "video_media_knowledge",
            "source": "universal_media_learner",
            "confidence": 0.95
        })

        db.create_audit_log("analyze_media_target", "success", f"Analyzed web media / ad target: {target}", level=0)

        return {
            "success": True,
            "platform_type": "Web Video / Ad / Embedded Media",
            "url": target,
            "title": web_media.get("title"),
            "video_sources": web_media.get("video_sources"),
            "iframe_sources": web_media.get("iframe_sources"),
            "ad_elements": web_media.get("ad_elements"),
            "ai_analysis": ai_summary
        }
