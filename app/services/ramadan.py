"""
Ramadan service — fetches fasting times from Aladhan API.

Uses the free Aladhan API (no API key needed) to get daily
Saharlik (Imsak) and Iftorlik (Maghrib) times for any Uzbekistan city.

Designed for future extensibility:
  - get_fasting_times() returns all data needed for notifications
  - City is passed as a parameter (stored per-user in DB)
  - Cache is per-city to support multiple users in different cities
"""
import time
from datetime import datetime, date
from dataclasses import dataclass
from typing import Optional
import aiohttp
from app.utils.logger import setup_logger
from app.constants import UZT

logger = setup_logger("ramadan")

# Aladhan API — free, no key needed
_ALADHAN_URL = "https://api.aladhan.com/v1/timingsByCity"

# Method 3 = Muslim World League (standard for Central Asia / Uzbekistan)
_CALCULATION_METHOD = 3

# Cache: city_name → (data, timestamp)
_cache: dict[str, tuple[dict, float]] = {}
_CACHE_TTL = 6 * 3600  # 6 hours


@dataclass
class FastingTimes:
    """Today's fasting times for a given city."""
    city: str
    imsak: str          # Saharlik end time (e.g. "05:37")
    fajr: str           # Fajr prayer time
    sunrise: str        # Sunrise time
    maghrib: str        # Iftorlik time (= Maghrib)
    ramadan_day: int    # Which day of Ramadan (1–30)
    hijri_date: str     # Full Hijri date string
    hijri_month: int    # Hijri month number (9 = Ramadan)
    hijri_year: str     # Hijri year


async def get_fasting_times(city: str = "Tashkent", target_date: Optional[date] = None) -> Optional[FastingTimes]:
    """
    Fetch fasting times for a city in Uzbekistan.

    Args:
        city: Aladhan API city name (e.g. "Tashkent", "Samarkand")
        target_date: Specific date to fetch. None = today (default).

    Returns FastingTimes dataclass or None on failure.
    Results are cached per city+date for 6 hours.
    """
    # Build cache key (city + date)
    date_str = target_date.strftime("%d-%m-%Y") if target_date else "today"
    cache_key = f"{city}_{date_str}"

    # Check cache
    now = time.time()
    if cache_key in _cache:
        cached_data, cached_at = _cache[cache_key]
        if now - cached_at < _CACHE_TTL:
            logger.debug(f"Cache hit for {cache_key}")
            return _parse_response(cached_data, city)

    # Build API URL — date goes in the URL path
    if target_date:
        url = f"{_ALADHAN_URL}/{target_date.strftime('%d-%m-%Y')}"
    else:
        url = _ALADHAN_URL

    params = {
        "city": city,
        "country": "Uzbekistan",
        "method": _CALCULATION_METHOD,
    }

    try:
        async with aiohttp.ClientSession() as session:
            async with session.get(
                url,
                params=params,
                timeout=aiohttp.ClientTimeout(total=10),
            ) as resp:
                if resp.status != 200:
                    logger.error(f"Aladhan API error {resp.status} for {cache_key}")
                    return _get_cached_fallback(cache_key, city)

                data = await resp.json()
                if data.get("code") != 200:
                    logger.error(f"Aladhan API returned non-200 code for {cache_key}")
                    return _get_cached_fallback(cache_key, city)

                # Cache the raw response
                _cache[cache_key] = (data, now)
                logger.info(f"Fetched fasting times for {cache_key}")
                return _parse_response(data, city)

    except (aiohttp.ClientError, Exception) as e:
        logger.error(f"Aladhan API request failed for {cache_key}: {e}")
        return _get_cached_fallback(cache_key, city)


def _get_cached_fallback(cache_key: str, city: str) -> Optional[FastingTimes]:
    """Return stale cached data if available (better than nothing)."""
    if cache_key in _cache:
        cached_data, _ = _cache[cache_key]
        logger.warning(f"Using stale cache for {cache_key}")
        return _parse_response(cached_data, city)
    return None


def _parse_response(data: dict, city: str) -> Optional[FastingTimes]:
    """Parse Aladhan API JSON response into FastingTimes."""
    try:
        timings = data["data"]["timings"]
        hijri = data["data"]["date"]["hijri"]

        return FastingTimes(
            city=city,
            imsak=timings.get("Imsak", ""),
            fajr=timings.get("Fajr", ""),
            sunrise=timings.get("Sunrise", ""),
            maghrib=timings.get("Maghrib", ""),
            ramadan_day=int(hijri.get("day", 0)),
            hijri_date=hijri.get("date", ""),
            hijri_month=hijri["month"].get("number", 0),
            hijri_year=hijri.get("year", ""),
        )
    except (KeyError, ValueError, TypeError) as e:
        logger.error(f"Failed to parse Aladhan response for {city}: {e}")
        return None


def get_iftar_countdown(maghrib_time: str) -> Optional[str]:
    """
    Calculate time remaining until iftar (Maghrib).
    Returns formatted string like "5 soat 23 daqiqa" or None if iftar has passed.

    This data can also be used by future notification features.
    """
    try:
        now = datetime.now(UZT)
        hour, minute = map(int, maghrib_time.split(":"))
        iftar = now.replace(hour=hour, minute=minute, second=0, microsecond=0)

        diff = iftar - now
        if diff.total_seconds() <= 0:
            return None  # Iftar has already passed today

        total_minutes = int(diff.total_seconds() // 60)
        hours = total_minutes // 60
        minutes = total_minutes % 60

        if hours > 0:
            return f"{hours} soat {minutes} daqiqa"
        return f"{minutes} daqiqa"
    except (ValueError, AttributeError):
        return None


def is_ramadan_active() -> bool:
    """Check if we're currently in Ramadan based on date range.

    Uses a generous date range to account for moon-sighting variations.
    The API's hijri month field provides the definitive check.
    """
    from app.constants import RAMADAN_START, RAMADAN_END
    today = datetime.now(UZT).date()
    return RAMADAN_START <= today <= RAMADAN_END
