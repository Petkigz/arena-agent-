"""Native location resolution (browser-free).

Resolves the device's geographic location without any browser geolocation API or
permission prompt:

1. Android phone location via ADB (`dumpsys location`) — the most accurate
   hardware source when a phone is connected.
2. IP-based geolocation (free, no API key) — works for a desktop on any network.

Gracefully degrades: returns an empty/unknown result when offline, never raises.
"""

import json
from typing import Dict, Any, Optional

import httpx

from app.utils.logger import app_logger, audit_logger

# Free, keyless IP geolocation endpoint (no auth required).
IP_API_URL = "http://ip-api.com/json/"


class LocationService:
    """Resolve geographic location from native sources (ADB / IP), not a browser."""

    @classmethod
    def get_phone_location(cls) -> Dict[str, Any]:
        """
        Query an attached Android device's location via ADB.

        Requires adb in PATH and a phone with location services enabled.
        """
        from app.tools.android_adb_controller import AndroidADBController

        if not AndroidADBController.is_adb_available():
            return {"success": False, "error": "ADB not available (no phone connected)."}

        try:
            res = AndroidADBController.run_adb_cmd(
                ["shell", "dumpsys", "location"],
            )
            if not res.get("success"):
                return {"success": False, "error": res.get("stderr", "dumpsys location failed.")}

            output = res.get("stdout", "")
            # `dumpsys location` prints the last known location; extract lat/long.
            lat = lon = None
            for line in output.splitlines():
                line = line.strip()
                # Common format: "last location=Location[gps 0.3476,-32.0000 ...]"
                if "Location[" in line and "," in line:
                    try:
                        coords = line.split("Location[", 1)[1].split("]", 1)[0]
                        parts = coords.split(",")
                        lon = float(parts[1].strip()) if len(parts) > 1 else None
                        lat = float(parts[0].split(" ", 1)[1].strip()) if " " in parts[0] else None
                        break
                    except Exception:
                        continue

            if lat is None or lon is None:
                return {"success": False, "error": "No location fix available on the phone."}

            return {
                "success": True,
                "source": "adb_phone_gps",
                "latitude": lat,
                "longitude": lon,
            }
        except Exception as e:
            app_logger.warning(f"Phone location query failed: {e}")
            return {"success": False, "error": str(e)}

    @classmethod
    def get_ip_location(cls) -> Dict[str, Any]:
        """Resolve approximate location from the public IP (free, keyless)."""
        try:
            r = httpx.get(IP_API_URL, timeout=5.0)
            if r.status_code != 200:
                return {"success": False, "error": f"IP API returned {r.status_code}"}
            data = r.json()
            if data.get("status") != "success":
                return {"success": False, "error": data.get("message", "IP lookup failed.")}
            return {
                "success": True,
                "source": "ip_geolocation",
                "latitude": data.get("lat"),
                "longitude": data.get("lon"),
                "city": data.get("city"),
                "region": data.get("regionName"),
                "country": data.get("country"),
                "timezone": data.get("timezone"),
            }
        except Exception as e:
            app_logger.warning(f"IP geolocation failed: {e}")
            return {"success": False, "error": str(e)}

    @classmethod
    def resolve_location(cls) -> Dict[str, Any]:
        """
        Resolve location using the best available native source.

        Prefers phone GPS (accurate) then falls back to IP geolocation (approx).
        """
        phone = cls.get_phone_location()
        if phone.get("success"):
            audit_logger.info(f"Resolved location via {phone['source']}")
            return phone

        ip = cls.get_ip_location()
        if ip.get("success"):
            audit_logger.info(f"Resolved location via {ip['source']}")
            return ip

        return {
            "success": False,
            "error": "Could not resolve location (no phone GPS and IP lookup unavailable).",
            "latitude": None,
            "longitude": None,
        }
