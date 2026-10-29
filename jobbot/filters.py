"""Decide which jobs are worth sending."""
from __future__ import annotations

import re
from datetime import datetime

from .config import Settings
from .models import Job
from .sources.common import years_required

# Phrases in a title that mean "you must live there".
_TITLE_REGION_LOCK = re.compile(
    r"\b(u\.?s\.?a?|united states|uk|u\.k\.|canada|eu|europe|latam|germany|australia)"
    r"[\s-]*(based|only|residents?|citizens?)\b", re.I)

_REMOTE_WORDS = re.compile(r"\b(remote|fully remote|100% remote|work from home|wfh)\b", re.I)


def _has_word(text: str, word: str) -> bool:
    """Whole-word match, so 'sr' doesn't hit 'Developers' and 'lead' doesn't hit 'leader'... mostly."""
    word = word.strip().lower()
    if not word:
        return False
    return re.search(rf"(?<![a-z0-9]){re.escape(word)}(?![a-z0-9])", text.lower()) is not None


def title_excluded(title: str, s: Settings) -> str | None:
    for w in s.exclude_title_words:
        if _has_word(title, w):
            return w
    return None


def title_match(title: str, s: Settings) -> str | None:
    for t in s.match_terms:
        if _has_word(title, t):
            return t
    return None


_LEVELS = [("intern", "internship"), ("entry", "entry"), ("junior", "entry"), ("associate", "associate"),
           ("mid", "mid_senior"), ("senior", "mid_senior"), ("director", "director"),
           ("executive", "executive")]


def seniority_key(text: str) -> str | None:
    """'Mid-Senior level' -> 'mid_senior'. Unknown/blank -> None (don't filter)."""
    t = (text or "").lower()
    for word, key in _LEVELS:
        if word in t:
            return key
    return None


def region_ok(location: str, s: Settings) -> bool:
    """Remote jobs often say 'Remote - US only'. Keep worldwide / India / Asia / unspecified."""
    if not s.region_filter:
        return True
    loc = (location or "").strip().lower()
    if not loc:
        return True
    stripped = _REMOTE_WORDS.sub("", loc)
    if not re.sub(r"[^a-z]", "", stripped):     # just "Remote" with no country
        return True
    return any(_has_word(loc, r) for r in s.allowed_regions if r != "remote")


def work_mode_ok(job: Job, s: Settings) -> bool:
    mode = job.work_mode or ("remote" if job.remote else "onsite")
    if s.work_mode == "any":
        return True
    if s.work_mode == "remote":
        return mode == "remote"
    if s.work_mode == "hybrid":
        return mode == "hybrid"
    return mode in ("remote", "hybrid")          # remote_hybrid


def reject_reason(job: Job, s: Settings, now: datetime) -> str | None:
    """None means keep. Otherwise a short reason, used in logs and tests."""
    if any(job.company.strip().lower() == m.lower() for m in s.muted_companies):
        return "muted company"
    age = job.age_minutes(now)
    limit = s.linkedin_max_age_min if job.source == "linkedin" else s.board_max_age_min
    if age is None and job.source != "linkedin":
        return "no date"
    if age is not None and age > limit:
        return f"too old ({age:.0f}m > {limit}m)"
    if not work_mode_ok(job, s):
        return f"work mode {job.work_mode}"
    bad = title_excluded(job.title, s)
    if bad:
        return f"excluded word '{bad}'"
    if s.max_years_experience >= 0:
        yrs = max(x for x in (job.min_years, years_required(job.title), -1) if x is not None)
        if yrs > s.max_years_experience:
            return f"asks {yrs}+ years"
    lvl = seniority_key(job.seniority)
    if lvl and s.experience and lvl not in s.experience:
        return f"level {job.seniority}"
    if job.source != "linkedin" or s.linkedin_title_match:   # LinkedIn's search is loose
        hit = title_match(job.title, s)
        if not hit:
            return "title not relevant"
        job.matched = job.matched or hit
    if job.source != "linkedin":
        if not region_ok(job.location, s):
            return f"region '{job.location}'"
    if s.region_filter and _TITLE_REGION_LOCK.search(job.title):
        return "region-locked title"
    return None
