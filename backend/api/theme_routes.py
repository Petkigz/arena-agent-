"""Theme customization."""

from typing import Dict, List, Optional
from fastapi import APIRouter
from pydantic import BaseModel
from app.utils.logger import app_logger

router = APIRouter(prefix="/api/themes", tags=["themes"])


class ThemeColor(BaseModel):
    """A theme color."""
    name: str
    value: str  # Hex color


class Theme(BaseModel):
    """A custom theme."""
    id: str
    name: str
    colors: Dict[str, str]
    font_family: str = "system-ui"
    is_builtin: bool = False


class CustomThemeRequest(BaseModel):
    """Request to create a custom theme."""
    name: str
    colors: Dict[str, str]
    font_family: str = "system-ui"


# Built-in themes
BUILTIN_THEMES: List[Theme] = [
    Theme(
        id="dark",
        name="Dark",
        colors={
            "background": "#0f172a",
            "surface": "#1e293b",
            "primary": "#3b82f6",
            "secondary": "#64748b",
            "text": "#f1f5f9",
            "accent": "#8b5cf6",
        },
        font_family="system-ui",
        is_builtin=True,
    ),
    Theme(
        id="light",
        name="Light",
        colors={
            "background": "#f8fafc",
            "surface": "#ffffff",
            "primary": "#3b82f6",
            "secondary": "#94a3b8",
            "text": "#1e293b",
            "accent": "#8b5cf6",
        },
        font_family="system-ui",
        is_builtin=True,
    ),
    Theme(
        id="ocean",
        name="Ocean",
        colors={
            "background": "#0c4a6e",
            "surface": "#075985",
            "primary": "#0ea5e9",
            "secondary": "#7dd3fc",
            "text": "#f0f9ff",
            "accent": "#06b6d4",
        },
        font_family="system-ui",
        is_builtin=True,
    ),
    Theme(
        id="forest",
        name="Forest",
        colors={
            "background": "#14532d",
            "surface": "#166534",
            "primary": "#22c55e",
            "secondary": "#86efac",
            "text": "#f0fdf4",
            "accent": "#10b981",
        },
        font_family="system-ui",
        is_builtin=True,
    ),
]

# Custom themes storage
custom_themes: Dict[str, Theme] = {}


@router.get("/", response_model=List[Theme])
async def list_themes():
    """List all available themes."""
    return BUILTIN_THEMES + list(custom_themes.values())


@router.get("/{theme_id}", response_model=Theme)
async def get_theme(theme_id: str):
    """Get a specific theme."""
    # Check built-in themes
    for theme in BUILTIN_THEMES:
        if theme.id == theme_id:
            return theme
    
    # Check custom themes
    if theme_id in custom_themes:
        return custom_themes[theme_id]
    
    # Return dark theme as default
    return BUILTIN_THEMES[0]


@router.post("/custom")
async def create_custom_theme(request: CustomThemeRequest):
    """Create a custom theme."""
    import uuid
    
    theme_id = f"theme-{uuid.uuid4().hex[:8]}"
    
    theme = Theme(
        id=theme_id,
        name=request.name,
        colors=request.colors,
        font_family=request.font_family,
        is_builtin=False,
    )
    
    custom_themes[theme_id] = theme
    
    app_logger.info(f"Created custom theme: {theme_id} ({request.name})")
    
    return {"success": True, "theme": theme}


@router.delete("/{theme_id}")
async def delete_custom_theme(theme_id: str):
    """Delete a custom theme."""
    if theme_id not in custom_themes:
        return {"success": False, "error": "Theme not found or is built-in"}
    
    del custom_themes[theme_id]
    app_logger.info(f"Deleted custom theme: {theme_id}")
    
    return {"success": True, "message": "Theme deleted"}
