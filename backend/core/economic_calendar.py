"""
Economic Calendar and News Blackout Engine.
Synchronizes directly with official Forex Factory (Fair Economy) real macro-economic feeds.
Filters high, medium, and low impact macro-economic announcements
(CPI, NFP, FOMC, Interest Rates, GDP, Retail Sales, PMI, Unemployment)
and blocks automated orders during user-configured pre-news and post-news blackout windows.
"""

import os
import io
import csv
import json
import time
import urllib.request
from typing import List, Dict, Any, Optional, Tuple, Set
from datetime import datetime, timedelta, timezone

from backend.storage.db import log_audit

FF_CSV_URL = "https://nfs.faireconomy.media/ff_calendar_thisweek.csv"
FF_JSON_URL = "https://nfs.faireconomy.media/ff_calendar_thisweek.json"

STORAGE_DIR = os.path.join(os.path.dirname(os.path.dirname(__file__)), "storage")
CACHE_FILE = os.path.join(STORAGE_DIR, "calendar_cache.json")

# Fallback institutional macro events for offline baseline
FALLBACK_MACRO_EVENTS = [
    {
        "Title": "Core CPI m/m",
        "Country": "USD",
        "Date": "11-18-2026",
        "Time": "8:30am",
        "Impact": "High",
        "Forecast": "0.3%",
        "Previous": "0.3%",
        "URL": "https://www.forexfactory.com/calendar"
    },
    {
        "Title": "Non-Farm Employment Change (NFP)",
        "Country": "USD",
        "Date": "11-20-2026",
        "Time": "8:30am",
        "Impact": "High",
        "Forecast": "185K",
        "Previous": "216K",
        "URL": "https://www.forexfactory.com/calendar"
    },
    {
        "Title": "Federal Funds Rate & FOMC Statement",
        "Country": "USD",
        "Date": "11-18-2026",
        "Time": "2:00pm",
        "Impact": "High",
        "Forecast": "5.25%",
        "Previous": "5.25%",
        "URL": "https://www.forexfactory.com/calendar"
    },
    {
        "Title": "ECB Main Refinancing Rate Decision",
        "Country": "EUR",
        "Date": "11-19-2026",
        "Time": "8:15am",
        "Impact": "High",
        "Forecast": "4.25%",
        "Previous": "4.25%",
        "URL": "https://www.forexfactory.com/calendar"
    },
    {
        "Title": "Bank of England Official Bank Rate",
        "Country": "GBP",
        "Date": "11-19-2026",
        "Time": "7:00am",
        "Impact": "High",
        "Forecast": "5.00%",
        "Previous": "5.00%",
        "URL": "https://www.forexfactory.com/calendar"
    },
    {
        "Title": "Flash Manufacturing PMI",
        "Country": "EUR",
        "Date": "11-20-2026",
        "Time": "4:00am",
        "Impact": "Medium",
        "Forecast": "46.2",
        "Previous": "45.8",
        "URL": "https://www.forexfactory.com/calendar"
    },
    {
        "Title": "Unemployment Claims",
        "Country": "USD",
        "Date": "11-19-2026",
        "Time": "8:30am",
        "Impact": "High",
        "Forecast": "220K",
        "Previous": "217K",
        "URL": "https://www.forexfactory.com/calendar"
    }
]

class EconomicCalendar:
    def __init__(self):
        self.pre_news_buffer_minutes = 30
        self.post_news_buffer_minutes = 30
        self.block_high_impact = True
        self.block_medium_impact = False
        self.last_sync_time: float = 0.0
        self.sync_ttl_seconds: int = 7200  # Sync with Forex Factory every 2 hours
        self.raw_events: List[Dict[str, Any]] = []
        self._load_cached_or_fallback()

    def configure(self, pre_mins: int = 30, post_mins: int = 30, block_high: bool = True, block_med: bool = False):
        self.pre_news_buffer_minutes = pre_mins
        self.post_news_buffer_minutes = post_mins
        self.block_high_impact = block_high
        self.block_medium_impact = block_med

    def _load_cached_or_fallback(self):
        """Loads events from disk cache or built-in fallback."""
        if os.path.exists(CACHE_FILE):
            try:
                with open(CACHE_FILE, "r", encoding="utf-8") as f:
                    self.raw_events = json.load(f)
                if self.raw_events:
                    return
            except Exception as e:
                print(f"[Calendar] Cache read error: {e}")
        self.raw_events = list(FALLBACK_MACRO_EVENTS)

    def sync_live_forex_factory_feed(self, force: bool = False) -> bool:
        """
        Pulls the latest real-world weekly economic calendar from Forex Factory / Fair Economy.
        Uses CSV as primary (includes direct URLs) and JSON as secondary fallback.
        """
        if os.environ.get("TRADING_BOT_ONLINE") != "1" and not force:
            return False

        now_ts = time.time()
        if not force and (now_ts - self.last_sync_time < self.sync_ttl_seconds) and self.raw_events:
            return True

        # Check online flag if set or try fetching
        try:
            req = urllib.request.Request(
                FF_CSV_URL,
                headers={"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"}
            )
            with urllib.request.urlopen(req, timeout=6) as resp:
                text = resp.read().decode("utf-8")
                reader = csv.DictReader(io.StringIO(text))
                rows = list(reader)
                if rows:
                    self.raw_events = rows
                    self.last_sync_time = now_ts
                    os.makedirs(STORAGE_DIR, exist_ok=True)
                    with open(CACHE_FILE, "w", encoding="utf-8") as f:
                        json.dump(rows, f, indent=2)
                    log_audit("FOREX_FACTORY_SYNC", "INFO", f"Synced {len(rows)} live events from Forex Factory CSV feed.")
                    return True
        except Exception as csv_err:
            # Try JSON fallback
            try:
                req = urllib.request.Request(
                    FF_JSON_URL,
                    headers={"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"}
                )
                with urllib.request.urlopen(req, timeout=6) as resp:
                    json_data = json.loads(resp.read().decode("utf-8"))
                    if json_data:
                        self.raw_events = json_data
                        self.last_sync_time = now_ts
                        os.makedirs(STORAGE_DIR, exist_ok=True)
                        with open(CACHE_FILE, "w", encoding="utf-8") as f:
                            json.dump(json_data, f, indent=2)
                        log_audit("FOREX_FACTORY_SYNC", "INFO", f"Synced {len(json_data)} live events from Forex Factory JSON feed.")
                        return True
            except Exception as json_err:
                pass  # Fall back to existing cached events

        if not self.raw_events:
            self._load_cached_or_fallback()
        return False

    def _parse_event_datetime(self, item: Dict[str, Any]) -> Optional[datetime]:
        """
        Parses Forex Factory date and time into UTC datetime.
        Forex Factory export is in US/Eastern time (UTC-5 in winter, UTC-4 in summer).
        """
        # Case A: JSON format with ISO date: "2026-11-18T08:30:00-05:00"
        iso_date = item.get("date")
        if iso_date and "T" in str(iso_date):
            try:
                dt = datetime.fromisoformat(str(iso_date))
                return dt.astimezone(timezone.utc)
            except Exception:
                pass

        # Case B: CSV format with Date: "11-18-2026" and Time: "8:30am"
        date_str = item.get("Date") or item.get("date")
        time_str = item.get("Time") or item.get("time")
        if not date_str:
            return None

        try:
            # Parse MM-DD-YYYY
            d = datetime.strptime(date_str.strip(), "%m-%d-%Y").date()
        except Exception:
            return None

        # Parse Time
        hour = 0
        minute = 0
        if time_str and any(c.isdigit() for c in time_str):
            clean_time = time_str.strip().lower()
            try:
                t = datetime.strptime(clean_time, "%I:%M%p").time()
                hour = t.hour
                minute = t.minute
            except Exception:
                try:
                    t = datetime.strptime(clean_time, "%H:%M").time()
                    hour = t.hour
                    minute = t.minute
                except Exception:
                    hour = 12
                    minute = 0

        # Forex Factory official feed publishes times in UTC (GMT)
        dt_utc = datetime(d.year, d.month, d.day, hour, minute, tzinfo=timezone.utc)
        return dt_utc

    def get_upcoming_events(
        self,
        base_currency: Optional[str] = None,
        quote_currency: Optional[str] = None,
        min_impact: Optional[str] = None
    ) -> List[Dict[str, Any]]:
        """
        Returns parsed Forex Factory news items sorted chronologically with live blackout calculations.
        """
        # Ensure fresh data if possible
        if not self.raw_events:
            self._load_cached_or_fallback()

        now_utc = datetime.now(timezone.utc)
        parsed_list: List[Dict[str, Any]] = []

        for item in self.raw_events:
            title = item.get("Title") or item.get("title") or "Macro News"
            country = (item.get("Country") or item.get("country") or "USD").upper()
            impact_raw = (item.get("Impact") or item.get("impact") or "Low").strip().capitalize()
            impact = "HIGH" if impact_raw == "High" else ("MEDIUM" if impact_raw == "Medium" else ("LOW" if impact_raw == "Low" else "HOLIDAY"))
            forecast = item.get("Forecast") or item.get("forecast") or "―"
            previous = item.get("Previous") or item.get("previous") or "―"
            url = item.get("URL") or item.get("url") or f"https://www.forexfactory.com/calendar"

            dt_utc = self._parse_event_datetime(item)
            if not dt_utc:
                continue

            diff_mins = (dt_utc - now_utc).total_seconds() / 60.0

            # Determine news blackout status
            is_blackout_candidate = (impact == "HIGH" and self.block_high_impact) or \
                                   (impact == "MEDIUM" and self.block_medium_impact)

            if is_blackout_candidate and (-self.post_news_buffer_minutes <= diff_mins <= self.pre_news_buffer_minutes):
                status = "ACTIVE_BLACKOUT"
            elif diff_mins < -self.post_news_buffer_minutes:
                status = "COMPLETED"
            else:
                status = "UPCOMING"

            # Human readable time display
            if status == "ACTIVE_BLACKOUT":
                if diff_mins > 0:
                    time_display = f"🔴 BLACKOUT (In {int(diff_mins)}m)"
                else:
                    time_display = f"🔴 BLACKOUT (Released {abs(int(diff_mins))}m ago)"
            elif diff_mins > 0:
                if diff_mins < 60:
                    time_display = f"⏱️ In {int(diff_mins)} mins"
                elif diff_mins < 1440:
                    hours = int(diff_mins // 60)
                    mins = int(diff_mins % 60)
                    time_display = f"⏱️ In {hours}h {mins}m"
                else:
                    days = int(diff_mins // 1440)
                    time_display = f"📅 In {days} day{'s' if days > 1 else ''}"
            else:
                mins_ago = abs(int(diff_mins))
                if mins_ago < 60:
                    time_display = f"✓ Released {mins_ago}m ago"
                elif mins_ago < 1440:
                    time_display = f"✓ Released {mins_ago // 60}h ago"
                else:
                    time_display = "✓ Completed"

            # Indian Standard Time (IST = UTC + 5:30)
            ist_tz = timezone(timedelta(hours=5, minutes=30))
            dt_ist = dt_utc.astimezone(ist_tz)
            # US Eastern Time (ET = UTC - 5:00)
            eastern_tz = timezone(timedelta(hours=-5))
            dt_eastern = dt_utc.astimezone(eastern_tz)

            parsed_list.append({
                "id": f"ff_{country}_{dt_utc.strftime('%Y%m%d_%H%M')}_{abs(hash(title)) % 10000}",
                "title": title,
                "currency": country,
                "impact": impact,
                "datetime_utc": dt_utc.strftime("%Y-%m-%dT%H:%M:%SZ"),
                "date_formatted": dt_utc.strftime("%a, %b %d"),
                "time_utc": dt_utc.strftime("%H:%M"),
                "time_local_est": dt_eastern.strftime("%I:%M %p"),
                "time_ist": dt_ist.strftime("%I:%M %p"),
                "date_ist": dt_ist.strftime("%a, %b %d"),
                "datetime_ist": dt_ist.strftime("%a, %b %d • %I:%M %p IST"),
                "minutes_until": round(diff_mins, 1),
                "time_display": time_display,
                "status": status,
                "forecast": forecast if forecast else "―",
                "previous": previous if previous else "―",
                "url": url,
                "source": "Forex Factory"
            })

        # Sort chronologically
        parsed_list.sort(key=lambda x: x["datetime_utc"])

        # Filter by currency if requested
        if base_currency or quote_currency:
            targets = {c.upper() for c in [base_currency, quote_currency] if c}
            parsed_list = [e for e in parsed_list if e["currency"] in targets]

        # Filter by impact if requested
        if min_impact:
            min_imp = min_impact.upper()
            if min_imp == "HIGH":
                parsed_list = [e for e in parsed_list if e["impact"] == "HIGH"]
            elif min_imp == "MEDIUM":
                parsed_list = [e for e in parsed_list if e["impact"] in ("HIGH", "MEDIUM")]

        return parsed_list

    def is_in_news_blackout(self, symbol: str) -> Tuple[bool, str]:
        """
        Evaluates whether a symbol is currently inside a Forex Factory high-impact news blackout window.
        """
        currencies: Set[str] = set()
        sym = symbol.upper()
        if sym.startswith("XAU") or sym.startswith("BTC") or sym.startswith("US30") or sym.startswith("NAS100"):
            currencies.add("USD")
        elif len(sym) >= 6:
            currencies.add(sym[:3])
            currencies.add(sym[3:6])
        else:
            currencies.add("USD")

        upcoming = self.get_upcoming_events()
        for ev in upcoming:
            if ev["currency"] in currencies:
                is_impacted = (ev["impact"] == "HIGH" and self.block_high_impact) or \
                              (ev["impact"] == "MEDIUM" and self.block_medium_impact)
                if is_impacted:
                    mins = ev["minutes_until"]
                    if -self.post_news_buffer_minutes <= mins <= self.pre_news_buffer_minutes:
                        if mins > 0:
                            reason = f"Forex Factory News Blackout: {ev['currency']} '{ev['title']}' releasing in {int(mins)}m ({self.pre_news_buffer_minutes}m pre-news buffer)."
                        else:
                            reason = f"Forex Factory News Blackout: {ev['currency']} '{ev['title']}' released {abs(int(mins))}m ago ({self.post_news_buffer_minutes}m post-news buffer)."
                        return True, reason

        return False, "Clear of high-impact news."
