"""Widgets package — modularized from monolithic app.py."""

from desktop.widgets.orb import PresenceOrbWidget
from desktop.widgets.sidebar import LeftSidebar
from desktop.widgets.context import ContextPanel

__all__ = ["PresenceOrbWidget", "LeftSidebar", "ContextPanel"]
