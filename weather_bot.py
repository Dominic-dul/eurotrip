#!/usr/bin/env python3
"""
Dry-spell weather bot.

Checks the daily rain probability for a set of regions in Lithuania, Latvia and
Poland over a target date window (default: 2026-06-13 .. 2026-06-21), ranks them
from driest to wettest, and posts the result to a Telegram chat.

Data source: Open-Meteo forecast API (no API key required).
Delivery:   Telegram Bot API (sendMessage).

Environment variables:
    TELEGRAM_BOT_TOKEN   Bot token from @BotFather            (required to send)
    TELEGRAM_CHAT_ID     Target chat id                       (required to send)
    START_DATE           ISO date, default 2026-06-13
    END_DATE             ISO date, default 2026-06-21

Run locally without sending:
    python weather_bot.py --dry-run
"""

from __future__ import annotations

import argparse
import datetime as dt
import os
import sys
import time
from dataclasses import dataclass
from typing import Optional

import requests

OPEN_METEO_URL = "https://api.open-meteo.com/v1/forecast"
TELEGRAM_API = "https://api.telegram.org/bot{token}/sendMessage"

DEFAULT_START = "2026-06-13"
DEFAULT_END = "2026-06-21"

# Open-Meteo forecasts reach ~16 days out. If the target window is further away
# than that, the API has no data for it yet and the bot says so rather than lying.
FORECAST_HORIZON_DAYS = 16


@dataclass(frozen=True)
class Region:
    name: str
    country: str
    lat: float
    lon: float

    @property
    def label(self) -> str:
        return f"{self.name}, {self.country}"


# A spread of cities across the three countries. Add/remove freely.
REGIONS: list[Region] = [
    # Lithuania
    Region("Vilnius", "LT", 54.6872, 25.2797),     # southeast
    Region("Kaunas", "LT", 54.8985, 23.9036),      # center
    Region("Klaipeda", "LT", 55.7033, 21.1443),    # west coast
    Region("Siauliai", "LT", 55.9333, 23.3167),    # north
    Region("Panevezys", "LT", 55.7333, 24.3500),   # north-central
    Region("Alytus", "LT", 54.3964, 24.0458),      # south
    Region("Utena", "LT", 55.4975, 25.6036),       # east
    # Latvia
    Region("Riga", "LV", 56.9496, 24.1052),        # center
    Region("Ventspils", "LV", 57.3894, 21.5606),   # northwest coast
    Region("Liepaja", "LV", 56.5047, 21.0108),     # southwest coast
    Region("Jelgava", "LV", 56.6500, 23.7128),     # south-central
    Region("Daugavpils", "LV", 55.8714, 26.5161),  # southeast
    Region("Rezekne", "LV", 56.5100, 27.3331),     # east
    Region("Valmiera", "LV", 57.5385, 25.4267),    # northeast
    # Poland
    Region("Warsaw", "PL", 52.2297, 21.0122),      # central-east
    Region("Lodz", "PL", 51.7592, 19.4560),        # center
    Region("Gdansk", "PL", 54.3520, 18.6466),      # north coast
    Region("Szczecin", "PL", 53.4285, 14.5528),    # northwest
    Region("Olsztyn", "PL", 53.7784, 20.4801),     # north
    Region("Bialystok", "PL", 53.1325, 23.1688),   # northeast
    Region("Poznan", "PL", 52.4064, 16.9252),      # west
    Region("Lublin", "PL", 51.2465, 22.5684),      # east
    Region("Wroclaw", "PL", 51.1079, 17.0385),     # southwest
    Region("Krakow", "PL", 50.0647, 19.9450),      # south
    Region("Rzeszow", "PL", 50.0413, 21.9990),     # southeast
]


@dataclass
class RegionForecast:
    region: Region
    dates: list[str]
    rain_prob: list[Optional[float]]   # daily max precipitation probability, %
    precip_sum: list[Optional[float]]  # daily precipitation total, mm
    temp_max: list[Optional[float]]    # daily max 2m temperature, C
    temp_min: list[Optional[float]]    # daily min 2m temperature, C

    @property
    def avg_rain_prob(self) -> float:
        vals = [v for v in self.rain_prob if v is not None]
        return sum(vals) / len(vals) if vals else float("inf")

    @property
    def total_precip(self) -> float:
        vals = [v for v in self.precip_sum if v is not None]
        return sum(vals) if vals else float("inf")

    @property
    def max_rain_prob(self) -> float:
        vals = [v for v in self.rain_prob if v is not None]
        return max(vals) if vals else float("inf")


def fetch_region(region: Region, start: str, end: str,
                 session: requests.Session, retries: int = 3) -> RegionForecast:
    """Fetch the daily forecast for one region from Open-Meteo."""
    params = {
        "latitude": region.lat,
        "longitude": region.lon,
        "daily": ("precipitation_probability_max,precipitation_sum,"
                  "temperature_2m_max,temperature_2m_min"),
        "timezone": "auto",
        "start_date": start,
        "end_date": end,
    }
    last_err: Optional[Exception] = None
    for attempt in range(1, retries + 1):
        try:
            resp = session.get(OPEN_METEO_URL, params=params, timeout=20)
            resp.raise_for_status()
            data = resp.json()
            daily = data.get("daily", {})
            return RegionForecast(
                region=region,
                dates=daily.get("time", []),
                rain_prob=daily.get("precipitation_probability_max", []),
                precip_sum=daily.get("precipitation_sum", []),
                temp_max=daily.get("temperature_2m_max", []),
                temp_min=daily.get("temperature_2m_min", []),
            )
        except (requests.RequestException, ValueError) as exc:
            last_err = exc
            if attempt < retries:
                time.sleep(1.5 * attempt)
    raise RuntimeError(f"Failed to fetch {region.label}: {last_err}")


def rank(forecasts: list[RegionForecast]) -> list[RegionForecast]:
    """Driest first. Primary key = avg rain probability, tiebreak = total precip."""
    return sorted(forecasts, key=lambda f: (f.avg_rain_prob, f.total_precip))


@dataclass
class DayPick:
    region: Region
    rain_prob: Optional[float]
    precip: Optional[float]
    temp_max: Optional[float]
    temp_min: Optional[float]


def daily_rankings(forecasts: list[RegionForecast]) -> list[tuple[str, list[DayPick]]]:
    """Pivot region-by-day into day-by-region.

    Returns, for each date in the window (sorted), a list of DayPick sorted
    driest first. A city with no data for a given day is skipped for that day.
    """
    by_date: dict[str, list[DayPick]] = {}
    for f in forecasts:
        for i, date in enumerate(f.dates):
            prob = f.rain_prob[i] if i < len(f.rain_prob) else None
            precip = f.precip_sum[i] if i < len(f.precip_sum) else None
            tmax = f.temp_max[i] if i < len(f.temp_max) else None
            tmin = f.temp_min[i] if i < len(f.temp_min) else None
            if prob is None:
                continue  # can't rank a day we have no probability for
            by_date.setdefault(date, []).append(
                DayPick(f.region, prob, precip, tmax, tmin))

    result: list[tuple[str, list[DayPick]]] = []
    for date in sorted(by_date):
        picks = sorted(
            by_date[date],
            key=lambda p: (p.rain_prob, p.precip if p.precip is not None else 0.0),
        )
        result.append((date, picks))
    return result


def window_is_in_range(start: str, today: Optional[dt.date] = None) -> bool:
    today = today or dt.date.today()
    start_date = dt.date.fromisoformat(start)
    return (start_date - today).days <= FORECAST_HORIZON_DAYS


def build_message(ranked: list[RegionForecast], start: str, end: str) -> str:
    """Compose a Telegram-friendly (Markdown) day-by-day routing message."""
    if not ranked:
        return "No forecast data available."

    days = daily_rankings(ranked)
    if not days:
        return "No daily forecast data available for the window."

    lines = [
        f"*Driest route {start} -> {end}*",
        "",
        "Where to head each day for the lowest rain chance:",
        "",
    ]
    for date, picks in days:
        day = dt.date.fromisoformat(date).strftime("%a %d %b")
        best = picks[0]
        line = f"*{day}*  ->  {best.region.label}  _{best.rain_prob:.0f}%_"
        if best.precip is not None:
            line += f", {best.precip:.1f} mm"
        if best.temp_max is not None and best.temp_min is not None:
            line += f", {best.temp_min:.0f}-{best.temp_max:.0f}C"
        elif best.temp_max is not None:
            line += f", {best.temp_max:.0f}C"
        lines.append(line)
        if len(picks) > 1:
            alt = picks[1]
            lines.append(f"    backup: {alt.region.label} ({alt.rain_prob:.0f}%)")

    # Overall driest single base, in case you'd rather not move every day.
    overall = ranked[0]
    lines += [
        "",
        f"If you'd rather stay put: *{overall.region.label}* is the driest single "
        f"base overall ({overall.avg_rain_prob:.0f}% avg).",
        "",
        "_Source: Open-Meteo. Probabilities are forecasts, not promises._",
    ]
    return "\n".join(lines)


def send_telegram(text: str, token: str, chat_id: str) -> None:
    url = TELEGRAM_API.format(token=token)
    resp = requests.post(
        url,
        json={
            "chat_id": chat_id,
            "text": text,
            "parse_mode": "Markdown",
            "disable_web_page_preview": True,
        },
        timeout=20,
    )
    if resp.status_code != 200:
        raise RuntimeError(f"Telegram error {resp.status_code}: {resp.text}")


def main() -> int:
    parser = argparse.ArgumentParser(description="Driest-region Telegram bot")
    parser.add_argument("--dry-run", action="store_true",
                        help="print the message instead of sending to Telegram")
    args = parser.parse_args()

    start = os.environ.get("START_DATE", DEFAULT_START)
    end = os.environ.get("END_DATE", DEFAULT_END)

    if not window_is_in_range(start):
        msg = (f"Target window starts {start}, which is more than "
               f"{FORECAST_HORIZON_DAYS} days out. Open-Meteo has no forecast "
               f"that far ahead yet; nothing to report.")
        print(msg, file=sys.stderr)
        # Not an error: just too early to forecast. Exit cleanly.
        return 0

    session = requests.Session()
    forecasts: list[RegionForecast] = []
    errors: list[str] = []
    for region in REGIONS:
        try:
            forecasts.append(fetch_region(region, start, end, session))
        except RuntimeError as exc:
            errors.append(str(exc))

    if not forecasts:
        print("All region fetches failed:\n" + "\n".join(errors), file=sys.stderr)
        return 1
    if errors:
        print("Some regions failed (continuing):\n" + "\n".join(errors),
              file=sys.stderr)

    ranked = rank(forecasts)
    message = build_message(ranked, start, end)

    if args.dry_run:
        print(message)
        return 0

    token = os.environ.get("TELEGRAM_BOT_TOKEN")
    chat_id = os.environ.get("TELEGRAM_CHAT_ID")
    if not token or not chat_id:
        print("TELEGRAM_BOT_TOKEN and TELEGRAM_CHAT_ID must be set "
              "(or use --dry-run).", file=sys.stderr)
        return 1

    send_telegram(message, token, chat_id)
    print(f"Sent. Driest: {ranked[0].region.label} "
          f"({ranked[0].avg_rain_prob:.0f}% avg).")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
