"""Multi-language support and translation."""

from typing import Dict, List, Optional
from fastapi import APIRouter
from pydantic import BaseModel
from app.utils.logger import app_logger

router = APIRouter(prefix="/api/language", tags=["language"])


class Language(BaseModel):
    """A supported language."""
    code: str  # ISO 639-1 code (e.g., "en", "sw")
    name: str  # Native name (e.g., "English", "Kiswahili")
    english_name: str
    is_supported: bool = True
    has_tts: bool = False
    has_stt: bool = False


class LanguageSettings(BaseModel):
    """Language settings."""
    ui_language: str = "en"
    tts_language: str = "en"
    stt_language: str = "en"
    auto_detect: bool = True


# Supported languages
SUPPORTED_LANGUAGES: List[Language] = [
    Language(
        code="en",
        name="English",
        english_name="English",
        is_supported=True,
        has_tts=True,
        has_stt=True,
    ),
    Language(
        code="sw",
        name="Kiswahili",
        english_name="Swahili",
        is_supported=True,
        has_tts=True,
        has_stt=True,
    ),
    Language(
        code="es",
        name="Español",
        english_name="Spanish",
        is_supported=True,
        has_tts=False,
        has_stt=True,
    ),
    Language(
        code="fr",
        name="Français",
        english_name="French",
        is_supported=True,
        has_tts=False,
        has_stt=True,
    ),
]

# UI translations
UI_TRANSLATIONS: Dict[str, Dict[str, str]] = {
    "en": {
        "welcome": "Welcome to Arena",
        "settings": "Settings",
        "chat": "Chat",
        "files": "Files",
        "projects": "Projects",
        "knowledge": "Knowledge",
        "send": "Send",
        "cancel": "Cancel",
        "save": "Save",
        "delete": "Delete",
        "loading": "Loading...",
    },
    "sw": {
        "welcome": "Karibu Arena",
        "settings": "Mipangilio",
        "chat": "Mazungumzo",
        "files": "Faili",
        "projects": "Miradi",
        "knowledge": "Maarifa",
        "send": "Tuma",
        "cancel": "Ghairi",
        "save": "Hifadhi",
        "delete": "Futa",
        "loading": "Inapakia...",
    },
}


@router.get("/languages", response_model=List[Language])
async def get_supported_languages():
    """Get list of supported languages."""
    return SUPPORTED_LANGUAGES


@router.get("/translations/{language_code}")
async def get_translations(language_code: str):
    """Get UI translations for a language."""
    translations = UI_TRANSLATIONS.get(language_code)
    if not translations:
        # Fall back to English
        translations = UI_TRANSLATIONS.get("en", {})
    
    return {"language": language_code, "translations": translations}


@router.post("/detect")
async def detect_language(text: str):
    """Detect the language of text."""
    # In production, this would use a language detection library
    # For now, simple heuristic
    swahili_words = ["habari", "ndio", "hapana", "asante", "karibu"]
    text_lower = text.lower()
    
    if any(word in text_lower for word in swahili_words):
        return {"language": "sw", "confidence": 0.8}
    
    return {"language": "en", "confidence": 0.9}


@router.get("/tts-voices/{language_code}")
async def get_tts_voices(language_code: str):
    """Get available TTS voices for a language."""
    # In production, this would query available Piper voices
    voices = {
        "en": [
            {"id": "en_US-lessac-medium", "name": "Lessac (US English)", "gender": "female"},
            {"id": "en_US-ryan-medium", "name": "Ryan (US English)", "gender": "male"},
        ],
        "sw": [
            {"id": "sw_KE-lanfrica-medium", "name": "Lanfrica (Kenyan Swahili)", "gender": "female"},
        ],
    }
    
    return voices.get(language_code, [])
