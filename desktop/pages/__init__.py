"""Pages package — modularized from monolithic app.py."""

from desktop.pages.beanie import BeaniePage
from desktop.pages.files import FilesPage
from desktop.pages.pansophy import PansophyPage
from desktop.pages.projects import ProjectsPage
from desktop.pages.settings import SettingsPage
from desktop.pages.code import CodePage
from desktop.pages.vision import VisionPage
from desktop.pages.tools import ToolsPage
from desktop.pages.chat import ChatPage
from desktop.pages.message_bubble import MessageBubble

__all__ = [
    "BeaniePage",
    "FilesPage",
    "PansophyPage",
    "ProjectsPage",
    "SettingsPage",
    "CodePage",
    "VisionPage",
    "ToolsPage",
    "ChatPage",
    "MessageBubble",
]
