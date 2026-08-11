import sys
import os
import subprocess
import webbrowser
import threading
import time
import httpx
from PIL import Image, ImageDraw
import pystray
from pystray import MenuItem as item

SERVER_URL = "http://localhost:8000"
LM_STUDIO_URL = "http://localhost:1234"
SERVER_PROCESS = None

def start_server_subprocess():
    """
    Checks if FastAPI server is running. If not, automatically launches uvicorn server in background.
    """
    global SERVER_PROCESS
    try:
        r = httpx.get(f"{SERVER_URL}/api/status", timeout=1.5)
        if r.status_code == 200:
            print("FastAPI server is already running on http://localhost:8000")
            return
    except Exception:
        pass

    base_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    print("Launching Local Personal Assistant FastAPI server on http://0.0.0.0:8000 ...")
    
    cmd = [sys.executable, "-m", "uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
    SERVER_PROCESS = subprocess.Popen(cmd, cwd=base_dir)

    # Wait for server startup
    for _ in range(15):
        time.sleep(1)
        try:
            r = httpx.get(f"{SERVER_URL}/api/status", timeout=1.0)
            if r.status_code == 200:
                print("FastAPI server initialized successfully!")
                break
        except Exception:
            pass

def create_tray_icon_image():
    """Generates a 64x64 cyberpunk icon image for the Windows System Tray."""
    image = Image.new('RGBA', (64, 64), color=(11, 15, 25, 255))
    dc = ImageDraw.Draw(image)
    # Draw cyan/blue circle icon
    dc.ellipse((8, 8, 56, 56), fill=(0, 242, 254, 255), outline=(59, 130, 246, 255), width=3)
    # Inner dark PA initials
    dc.text((20, 18), "PA", fill=(11, 15, 25, 255))
    return image

# Command Shortcut Callbacks
def open_dashboard():
    webbrowser.open(f"{SERVER_URL}/")

def open_voice_chat():
    webbrowser.open(f"{SERVER_URL}/")

def open_learner():
    webbrowser.open(f"{SERVER_URL}/")

def open_tasks():
    webbrowser.open(f"{SERVER_URL}/")

def open_models():
    webbrowser.open(f"{SERVER_URL}/")

def open_manual():
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

def trigger_kill_switch(icon, item_obj):
    try:
        httpx.post(f"{SERVER_URL}/system/shutdown", timeout=2.0)
    except Exception:
        pass
    cleanup_and_exit(icon)

def cleanup_and_exit(icon):
    global SERVER_PROCESS
    if SERVER_PROCESS:
        try:
            SERVER_PROCESS.terminate()
            SERVER_PROCESS.wait(timeout=3)
        except Exception:
            pass
    print("Exiting Windows System Tray App cleanly.")
    icon.stop()

def run_system_tray():
    # 1. Start background server first
    server_thread = threading.Thread(target=start_server_subprocess, daemon=True)
    server_thread.start()

    image = create_tray_icon_image()
    
    # Taskbar Menu with Shortcuts
    menu = pystray.Menu(
        item("🚀 Launch Visual Dashboard (Default)", open_dashboard, default=True),
        pystray.Menu.SEPARATOR,
        item("💬 Quick Voice & Chat", open_voice_chat),
        item("🌐 Web & YouTube Learner", open_learner),
        item("📋 Persistent Tasks Board", open_tasks),
        item("⚙️ Manage AI Brains & Custom Voices", open_models),
        item("📖 Edit Rules & Operating Manual", open_manual),
        item("🧠 Open LM Studio", open_lm_studio),
        pystray.Menu.SEPARATOR,
        item("💤 Toggle Sleep / Active Mode", toggle_sleep_mode),
        item("🛑 Trigger Kill Switch / Server Shutdown", trigger_kill_switch),
        pystray.Menu.SEPARATOR,
        item("🚪 Exit System Tray & Stop Server", cleanup_and_exit)
    )

    icon = pystray.Icon("PA_Local_Assistant", image, "Local Personal Assistant (Running)", menu)
    
    # Auto-open dashboard in browser on first launch
    def auto_open_browser():
        time.sleep(2)
        open_dashboard()

    threading.Thread(target=auto_open_browser, daemon=True).start()

    print("Windows System Tray App is permanently active in Taskbar until you click 'Exit System Tray'!")
    icon.run()

if __name__ == "__main__":
    run_system_tray()
