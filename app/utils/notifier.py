from typing import Dict, Any
from app.utils.logger import app_logger

class SystemNotifier:
    @classmethod
    def send_notification(cls, title: str, message: str) -> Dict[str, Any]:
        """
        Sends native desktop notification toast on Windows/Linux via plyer.
        """
        try:
            from plyer import notification
            notification.notify(
                title=title,
                message=message,
                app_name="Local Personal Assistant",
                timeout=5
            )
            app_logger.info(f"Desktop notification sent: [{title}] {message}")
            return {"success": True, "title": title, "message": message}
        except Exception as e:
            app_logger.warning(f"Could not send native desktop toast notification: {e}")
            return {"success": False, "error": str(e), "title": title, "message": message}
