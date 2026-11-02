"""Weather from Open-Meteo (free, no account or API key).

Only the city name you configure (or ask about) is sent - no microphone
audio, no IP-based location.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Callable

from . import http

GEOCODE_URL = "https://geocoding-api.open-meteo.com/v1/search"
FORECAST_URL = "https://api.open-meteo.com/v1/forecast"

# WMO weather codes -> short words
CODES = {
    0: "clear skies", 1: "mostly clear", 2: "partly cloudy", 3: "overcast", 45: "fog", 48: "freezing fog",
    51: "light drizzle", 53: "drizzle", 55: "heavy drizzle", 56: "freezing drizzle", 57: "freezing drizzle",
    61: "light rain", 63: "rain", 65: "heavy rain", 66: "freezing rain", 67: "freezing rain",
    71: "light snow", 73: "snow", 75: "heavy snow", 77: "snow grains", 80: "light showers", 81: "showers",
    82: "violent showers", 85: "snow showers", 86: "heavy snow showers", 95: "thunderstorms",
    96: "thunderstorms with hail", 99: "thunderstorms with hail",
}


class WeatherError(Exception):
    pass


@dataclass
class Place:
    name: str
    country: str
    latitude: float
    longitude: float


class Weather:
    def __init__(self, units: str = "metric", fetch: Callable = http.request) -> None:
        self.units = units
        self._fetch = fetch
        self._places: dict[str, Place] = {}

    def find_place(self, query: str) -> Place:
        key = query.strip().lower()
        if key in self._places:
            return self._places[key]
        try:
            data = self._fetch("GET", GEOCODE_URL, params={"name": query, "count": 1, "language": "en",
                                                           "format": "json"})
        except (OSError, http.HttpError) as exc:
            raise WeatherError("Weather service unreachable.") from exc
        results = (data or {}).get("results") or []
        if not results:
            raise WeatherError(f"Couldn't find a place called {query}.")
        r = results[0]
        place = Place(r["name"], r.get("country", ""), float(r["latitude"]), float(r["longitude"]))
        self._places[key] = place
        return place

    def report(self, place_query: str, day: str = "today") -> str:
        """A short spoken-style report, e.g. 'London: 14°, light rain. High 16, low 9...'"""
        place = self.find_place(place_query)
        imperial = self.units == "imperial"
        params = {
            "latitude": place.latitude, "longitude": place.longitude, "timezone": "auto", "forecast_days": 2,
            "current": "temperature_2m,apparent_temperature,weather_code,wind_speed_10m",
            "daily": "weather_code,temperature_2m_max,temperature_2m_min,precipitation_probability_max",
            "temperature_unit": "fahrenheit" if imperial else "celsius",
            "wind_speed_unit": "mph" if imperial else "kmh",
        }
        try:
            data = self._fetch("GET", FORECAST_URL, params=params)
        except (OSError, http.HttpError) as exc:
            raise WeatherError("Weather service unreachable.") from exc
        try:
            return self._phrase(place, data, day)
        except (KeyError, IndexError, TypeError) as exc:
            raise WeatherError("The weather service sent something odd.") from exc

    def _phrase(self, place: Place, data: dict, day: str) -> str:
        """Always the same facts: (now,) high, low and chance of rain - no advice."""
        daily = data["daily"]
        i = 1 if day == "tomorrow" else 0
        high, low = round(daily["temperature_2m_max"][i]), round(daily["temperature_2m_min"][i])
        rain = (daily.get("precipitation_probability_max") or [None, None])[i]
        rain_text = f"{round(rain)}% chance of rain." if rain is not None else "No rain forecast available."
        sky = CODES.get(int(daily["weather_code"][i]), "mixed weather")
        if day == "tomorrow":
            return f"Tomorrow in {place.name}: {sky}. High {high}°, low {low}°, {rain_text}"
        cur = data["current"]
        now_sky = CODES.get(int(cur["weather_code"]), sky)
        return (f"{place.name} today: {round(cur['temperature_2m'])}° now and {now_sky}. "
                f"High {high}°, low {low}°, {rain_text}")

    def will_it_rain(self, place_query: str, day: str = "today") -> str:
        place = self.find_place(place_query)
        try:
            data = self._fetch("GET", FORECAST_URL, params={
                "latitude": place.latitude, "longitude": place.longitude, "timezone": "auto", "forecast_days": 2,
                "daily": "precipitation_probability_max,weather_code"})
            chance = data["daily"]["precipitation_probability_max"][1 if day == "tomorrow" else 0] or 0
        except (OSError, http.HttpError) as exc:
            raise WeatherError("Weather service unreachable.") from exc
        except (KeyError, IndexError, TypeError) as exc:
            raise WeatherError("The weather service sent something odd.") from exc
        when = "tomorrow" if day == "tomorrow" else "today"
        return f"{round(chance)}% chance of rain in {place.name} {when}."
