"""Weather lookup — free, keyless (Open-Meteo), browser-free.

No API key required. Fetches current weather + a short forecast for a city.
Gracefully returns an error dict when offline.
"""

from __future__ import annotations

from typing import Dict, Any, Optional

import httpx

from app.utils.logger import app_logger

# Open-Meteo geocoding + forecast (free, no key).
GEO_URL = "https://geocoding-api.open-meteo.com/v1/search"
FORECAST_URL = "https://api.open-meteo.com/v1/forecast"

WMO_CODES = {
    0: "clear", 1: "mainly clear", 2: "partly cloudy", 3: "overcast",
    45: "fog", 48: "rime fog", 51: "light drizzle", 53: "drizzle", 55: "heavy drizzle",
    61: "light rain", 63: "rain", 65: "heavy rain", 71: "light snow", 73: "snow", 75: "heavy snow",
    80: "light showers", 81: "showers", 82: "heavy showers", 95: "thunderstorm",
}


class WeatherService:
    @classmethod
    def _geocode(cls, city: str) -> Optional[Dict[str, Any]]:
        r = httpx.get(GEO_URL, params={"name": city, "count": 1, "language": "en"}, timeout=8.0)
        r.raise_for_status()
        results = r.json().get("results") or []
        return results[0] if results else None

    @classmethod
    def get_weather(cls, city: str) -> Dict[str, Any]:
        """Current weather + today's high/low for a city name."""
        try:
            loc = cls._geocode(city)
            if loc is None:
                return {"success": False, "error": f"City '{city}' not found."}

            r = httpx.get(FORECAST_URL, params={
                "latitude": loc["latitude"],
                "longitude": loc["longitude"],
                "current_weather": "true",
                "daily": "temperature_2m_max,temperature_2m_min",
                "timezone": "auto",
            }, timeout=8.0)
            r.raise_for_status()
            data = r.json()

            cur = data.get("current_weather", {})
            code = cur.get("weathercode", 0)
            daily = data.get("daily", {})
            high = daily.get("temperature_2m_max", [None])[0]
            low = daily.get("temperature_2m_min", [None])[0]

            return {
                "success": True,
                "city": loc.get("name", city),
                "country": loc.get("country"),
                "temperature_c": cur.get("temperature"),
                "windspeed_kmh": cur.get("windspeed"),
                "condition": WMO_CODES.get(code, "unknown"),
                "high_c": high,
                "low_c": low,
            }
        except Exception as e:
            app_logger.warning(f"Weather lookup failed: {e}")
            return {"success": False, "error": f"Weather unavailable: {e}"}
