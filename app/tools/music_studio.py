from typing import Dict, Any, List, Optional
from app.llm import llm_client, extract_reply, require_real_completion
from app.utils.logger import app_logger

class MusicStudioTool:
    VOCAL_EQ_GUIDE = {
        "sub_bass": "High Pass Filter at 80Hz - 90Hz to clear mud and room rumble.",
        "boxy_mud": "Dip 250Hz - 400Hz gently (-2dB to -4dB) to remove boxy room resonance.",
        "nasal_harshness": "Cut 1kHz - 2.5kHz if vocal sounds honky or nasal.",
        "presence_clarity": "Slight boost at 3kHz - 5kHz for vocal clarity and articulation.",
        "sibilance_control": "De-esser dynamically notched at 5kHz - 8kHz for harsh 'S' sounds.",
        "air_shimmer": "High Shelf boost at 10kHz - 12kHz (+2dB) for expensive, silky high-end air."
    }

    @classmethod
    def generate_vocal_chain_guide(
        cls, 
        genre: str = "hiphop", 
        vocal_type: str = "male_rap",
        daw_name: str = "FL Studio / Logic / Pro Tools"
    ) -> Dict[str, Any]:
        """
        Generates tailored vocal chain mixing parameters (EQ, Compression, De-Essing, Reverb/Delay) for DAW production.
        """
        if not genre or not genre.strip():
            return {"success": False, "error": "A genre is required.", "quick_frequency_cheatsheet": cls.VOCAL_EQ_GUIDE}
        genre = genre.strip()
        vocal_type = (vocal_type or "male_rap").strip()
        daw_name = (daw_name or "FL Studio / Logic / Pro Tools").strip()

        system_prompt = (
            "You are a professional audio mixing engineer. Generate precise, "
            "actionable vocal mixing chain parameter guidelines for music production."
        )

        user_prompt = f"""
Generate a professional vocal mixing chain guide for:
- Genre: {genre}
- Vocal Style: {vocal_type}
- DAW: {daw_name}

Provide exact recommended parameter settings for:
1. **High Pass & Sub Clean**: HPF cut frequency.
2. **Surgical & Tone EQ**: Frequencies to dip and boost.
3. **Compression Settings**: Ratio, Attack time, Release time, and Target gain reduction (dB).
4. **De-Essing**: Frequency threshold for sibilance control.
5. **Spatial Effects**: Reverb, Ping-Pong Delay, and Parallel Saturation settings.
"""

        messages = [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt}
        ]

        try:
            llm_res = llm_client.generate_chat_completion(
                messages=messages,
                complexity="main",
                max_tokens=800
            )

            chain_guide = require_real_completion(llm_res)

            return {
                "success": True,
                "genre": genre,
                "vocal_type": vocal_type,
                "daw_name": daw_name,
                "vocal_chain_guide": chain_guide,
                "quick_frequency_cheatsheet": cls.VOCAL_EQ_GUIDE
            }
        except Exception as e:
            app_logger.error(f"Error generating vocal chain guide: {e}")
            return {
                "success": False,
                "error": f"Failed to generate vocal guide: {str(e)}",
                "quick_frequency_cheatsheet": cls.VOCAL_EQ_GUIDE
            }
