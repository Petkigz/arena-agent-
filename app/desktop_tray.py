import sys
import os
import webbrowser
import threading
import time
import httpx
from PIL import Image, ImageDraw
import pystray
from pystray import MenuItem as item

SERVER_URL = "http://localhost:8000"
LM_STUDIO_URL = "http://localhost:1234"

def create_tray_icon_image():
    """Generates a 64x64 cyberpunk icon image for the Windows System Tray."""
    image = Image.new('RGBA', (64, 64), color=(11, 15, 25, 255))
    dc = ImageDraw.Draw(image)
    # Draw cyan/blue circle icon
    dc.ellipse((8, 8, 56, 56), fill=(0, 242, 254, 255), outline=(59, 130, 246, 255), width=3)
    # Inner dark PA initials
    dc.text((20, 18), "PA", fill=(11, 15, 25, 255))
    return image

def open_dashboard():
    webbrowser.open(f"{SERVER_URL}/")

def open_lm_studio():
    webbrowser.open(LM_STUDIO_URL)

def toggle_sleep_mode(icon, item_obj):
    try:
        r = httpx.get(f"{SERVER_URL}/system/mode", timeout=2.0)
        mode = r.json().get("system_mode", "active")
        target = "active" if mode == "sleeping" else "sleeping"
        httpx.post(f"{SERVER_URL}/system/sleep", json={"mode": target}, timeout=2.0)
    except Exception as e:
        print(f"Error toggling sleep mode: {e}")

def trigger_shutdown(icon, item_obj):
    try:
        httpx.post(f"{SERVER_URL}/system/shutdown", timeout=2.0)
    except Exception:
        pass
    icon.stop()

def exit_tray(icon, item_obj):
    icon.stop()

def run_system_tray():
    image = create_tray_icon_image()
    menu = pystray.Menu(
        item("🌐 Open Visual Dashboard App", open_dashboard, default=True),
        item("💤 Toggle Sleep Mode", toggle_sleep_mode),
        item("🧠 Open LM Studio", open_lm_studio),
        pystray.Menu.SEPARATOR,
        item("🛑 Trigger Kill Switch / Shutdown", trigger_shutdown),
        item("🚪 Exit System Tray", exit_tray)
    )

    icon = pystray.Icon("PA_Local_Assistant", image, "Local Personal Assistant", menu)
    print("Windows System Tray App active in Taskbar!")
    icon.run()

if __name__ == "__main__":
    run_system_tray()
