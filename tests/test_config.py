import os
from pathlib import Path
from app.config import settings

def test_settings_initialization():
    assert settings.APP_NAME == "Local Personal Assistant"
    assert settings.DEBUG is True
    assert isinstance(settings.BASE_DIR, Path)
    assert settings.DATA_DIR.exists()
    assert settings.USER_MANUAL_PATH.parent.exists()
