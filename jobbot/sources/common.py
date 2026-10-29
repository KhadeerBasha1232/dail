"""Shared helpers for sources."""
from __future__ import annotations

import html
import re
from datetime import datetime, timedelta, timezone
from email.utils import parsedate_to_datetime

UA = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/130.0.0.0 Safari/537.36"
)
HEADERS = {"User-Agent": UA, "Accept-Language": "en-US,en;q=0.9"}


def parse_date(value) -> datetime | None:
    """Accepts ISO strings, unix seconds/ms, or RFC-822 (RSS). Returns aware UTC."""
    if value in (None, "", 0):
        return None
    try:
        if isinstance(value, (int, float)) or (isinstance(value, str) and value.isdigit()):
            v = float(value)
            if v > 1e12:          # milliseconds
                v /= 1000
            return datetime.fromtimestamp(v, tz=timezone.utc)
        value = str(value).strip()
        try:
            dt = datetime.fromisoformat(value.replace("Z", "+00:00"))
        except ValueError:
            dt = parsedate_to_datetime(value)
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return dt.astimezone(timezone.utc)
    except (ValueError, TypeError, OverflowError):
        return None


_REL = re.compile(r"(\d+)\s*(second|minute|min|hour|hr|day|week|month)", re.I)
_MINUTES = {"second": 1 / 60, "minute": 1, "min": 1, "hour": 60, "hr": 60,
            "day": 1440, "week": 10080, "month": 43200}


def relative_minutes(text: str) -> float | None:
    """'14 minutes ago' -> 14, 'Just now' -> 0."""
    t = (text or "").lower()
    if "just now" in t or "moments ago" in t:
        return 0
    m = _REL.search(t)
    if not m:
        return None
    return int(m.group(1)) * _MINUTES[m.group(2).lower()]


def ago(minutes: float, now: datetime) -> datetime:
    return now - timedelta(minutes=minutes)


def clean(text) -> str:
    return re.sub(r"\s+", " ", html.unescape(str(text or ""))).strip()


def fmt_money(lo, hi, currency: str = "USD", period: str = "") -> str:
    def k(v):
        v = float(v)
        return f"{v / 1000:.0f}k" if v >= 1000 else f"{v:.0f}"
    sym = {"USD": "$", "EUR": "€", "GBP": "£", "INR": "₹"}.get((currency or "USD").upper(), "")
    lo = lo or 0
    hi = hi or 0
    if not lo and not hi:
        return ""
    rng = f"{sym}{k(lo)}–{sym}{k(hi)}" if lo and hi and lo != hi else f"{sym}{k(lo or hi)}"
    if not sym and currency:
        rng += f" {currency}"
    per = {"annual": "/yr", "year": "/yr", "yearly": "/yr", "month": "/mo", "hour": "/hr"}.get(
        (period or "").lower(), "")
    return rng + per


_YEARS = re.compile(
    r"(\d{1,2})\s*(?:\+|plus)?\s*(?:(?:-|–|to)\s*\d{1,2}\s*)?\+?\s*(?:years?|yrs?)\b", re.I)


def years_required(text: str) -> int | None:
    """Smallest 'N+ years' / 'N-M years' figure found in a job description."""
    nums = [int(m.group(1)) for m in _YEARS.finditer(text or "")]
    nums = [n for n in nums if 0 <= n <= 20]
    return min(nums) if nums else None


def remote_mode(text: str, default: str = "onsite") -> str:
    t = (text or "").lower()
    if "hybrid" in t:
        return "hybrid"
    if "remote" in t or "anywhere" in t or "work from home" in t:
        return "remote"
    return default
