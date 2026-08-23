import re
from typing import Dict, Any, List, Optional
from youtube_transcript_api import YouTubeTranscriptApi
from app.llm import llm_client, extract_reply, require_real_completion
from app.utils.logger import app_logger

class YouTubeLearner:
    @staticmethod
    def extract_video_id(url_or_id: str) -> Optional[str]:
        """
        Extracts the 11-character YouTube video ID from various URL formats or raw ID string.
        """
        url_or_id = url_or_id.strip()
        
        # If it's already a raw 11-character ID
        if re.match(r'^[a-zA-Z0-9_-]{11}$', url_or_id):
            return url_or_id
            
        # Match youtube.com/watch?v=... or youtube.com/embed/..., youtube.com/shorts/...
        match = re.search(r'(?:v=|\/embed\/|\/shorts\/|\/v\/|https:\/\/youtu\.be\/)([a-zA-Z0-9_-]{11})', url_or_id)
        if match:
            return match.group(1)
            
        return None

    @classmethod
    def get_transcript(cls, url_or_id: str, languages: List[str] = ['en']) -> Dict[str, Any]:
        """
        Retrieves transcript text and timestamped segments for a YouTube video.
        """
        video_id = cls.extract_video_id(url_or_id)
        if not video_id:
            return {
                "success": False,
                "error": f"Invalid YouTube URL or Video ID: '{url_or_id}'",
                "video_id": None,
                "transcript": "",
                "segments": []
            }

        try:
            # Instantiate YouTubeTranscriptApi
            api = YouTubeTranscriptApi()
            transcript_list = api.list(video_id)
            
            # Find requested language or fallback to any available transcript
            try:
                transcript_obj = transcript_list.find_transcript(languages)
            except Exception:
                # Fallback to auto-generated or first available language
                transcript_obj = transcript_list.find_generated_transcript(languages) if hasattr(transcript_list, 'find_generated_transcript') else list(transcript_list)[0]

            segments = transcript_obj.fetch()
            full_text = " ".join([seg.get('text', '') for seg in segments])
            
            return {
                "success": True,
                "video_id": video_id,
                "video_url": f"https://www.youtube.com/watch?v={video_id}",
                "transcript": full_text,
                "segments": segments,
                "language": getattr(transcript_obj, 'language', 'en')
            }
        except Exception as e:
            app_logger.warning(f"Failed to fetch YouTube transcript for {video_id}: {e}")
            return {
                "success": False,
                "error": f"Could not retrieve transcript for video '{video_id}'. Subtitles may be disabled or video is private. Error: {str(e)}",
                "video_id": video_id,
                "transcript": "",
                "segments": []
            }

    @classmethod
    def learn_from_video(
        cls, 
        url_or_id: str, 
        prompt_focus: Optional[str] = None,
        complexity: str = "main"
    ) -> Dict[str, Any]:
        """
        Retrieves YouTube transcript and uses Qwen local LLM to extract actionable 
        step-by-step skill checklists, code snippets, and knowledge notes.
        """
        transcript_data = cls.get_transcript(url_or_id)
        if not transcript_data["success"]:
            return transcript_data

        raw_transcript = transcript_data["transcript"]
        video_url = transcript_data["video_url"]
        
        # Truncate raw transcript if it exceeds context limit (~12,000 characters)
        max_chars = 12000
        truncated_transcript = raw_transcript[:max_chars]
        if len(raw_transcript) > max_chars:
            truncated_transcript += " ... [Transcript truncated for local context window]"

        focus_instruction = f" Focus specifically on: '{prompt_focus}'." if prompt_focus else ""

        system_prompt = (
            "You are an expert AI skill extractor and technical summarizer. "
            "Your job is to read the provided video transcript and extract clear, "
            "actionable technical knowledge and a step-by-step skill checklist."
        )

        user_prompt = f"""
Analyze the following YouTube video transcript (Source URL: {video_url}).{focus_instruction}

Transcript Text:
\"\"\"
{truncated_transcript}
\"\"\"

Please extract and structure the knowledge as follows:
1. **Video Title & Topic Overview**: A 2-sentence summary of what this video teaches.
2. **Key Concepts & Technical Rules**: Core rules, settings, or ideas explained.
3. **Step-by-Step Actionable Skill Checklist**: Numbered steps to reproduce or apply this skill.
4. **Code, Commands, or Key Tool Settings**: Any explicit commands, settings, code snippets, or configuration parameters mentioned.
"""

        messages = [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt}
        ]

        try:
            llm_res = llm_client.generate_chat_completion(
                messages=messages,
                complexity=complexity,
                max_tokens=1024
            )
            
            ai_summary = require_real_completion(llm_res)

            return {
                "success": True,
                "video_id": transcript_data["video_id"],
                "video_url": video_url,
                "ai_summary": ai_summary,
                "raw_transcript_snippet": raw_transcript[:500] + "...",
                "full_transcript_length": len(raw_transcript)
            }
        except Exception as e:
            app_logger.error(f"Error in learn_from_video: {e}")
            return {
                "success": False,
                "error": f"Failed to generate AI summary from transcript: {str(e)}",
                "video_id": transcript_data["video_id"],
                "video_url": video_url,
                "ai_summary": "",
                "raw_transcript_snippet": raw_transcript[:500] + "..."
            }
