"""Turns a Job into a Telegram HTML message + inline buttons."""
from __future__ import annotations

import re
from datetime import datetime
from html import escape

from .models import Job, utcnow

SOURCE_NAMES = {
    "linkedin": "LinkedIn", "remotive": "Remotive", "remoteok": "RemoteOK",
    "himalayas": "Himalayas", "jobicy": "Jobicy", "workingnomads": "Working Nomads",
    "weworkremotely": "We Work Remotely", "arbeitnow": "Arbeitnow",
    "greenhouse": "Greenhouse", "lever": "Lever", "ashby": "Ashby",
}
MODE_LABEL = {"remote": "🌍 Remote", "hybrid": "🏙 Hybrid", "onsite": "🏢 On-site"}


def freshness(minutes: float | None) -> tuple[str, str]:
    """(badge, label) for the header line."""
    if minutes is None:
        return "🆕", "New"
    if minutes <= 5:
        return "🔥", "Just posted"
    if minutes <= 15:
        return "⚡", "Fresh"
    if minutes <= 60:
        return "🟢", "New"
    if minutes <= 360:
        return "🕐", "Today"
    return "📅", "Recent"


def human_age(minutes: float | None) -> str:
    if minutes is None:
        return "recently"
    if minutes < 1:
        return "just now"
    if minutes < 60:
        return f"{minutes:.0f} min ago"
    if minutes < 1440:
        h = minutes / 60
        return f"{h:.0f} hr ago" if h >= 1.5 else "1 hr ago"
    return f"{minutes / 1440:.0f}d ago"


def _hashtag(tag: str) -> str:
    t = re.sub(r"[^\w]+", "_", tag.strip().lower()).strip("_")
    return f"#{t}" if t and not t[0].isdigit() else ""


def applicants_line(text: str) -> str:
    t = text.lower()
    if not t:
        return ""
    m = re.search(r"first (\d+)", t)
    if m:
        return f"🟢 Be among the first {m.group(1)} applicants"
    m = re.search(r"(\d+)", t.replace(",", ""))
    if m:
        n = int(m.group(1))
        dot = "🟢" if n < 25 else ("🟡" if n < 100 else "🔴")
        return f"{dot} {escape(text)}"
    return f"👥 {escape(text)}"


def job_card(job: Job, now: datetime | None = None, style: str = "card") -> str:
    now = now or utcnow()
    age = job.age_minutes(now)
    badge, label = freshness(age)
    src = SOURCE_NAMES.get(job.source, job.source.title())
    title = escape(job.title)
    company = escape(job.company or "Unknown company")

    if style == "compact":
        return (f"{badge} <a href=\"{escape(job.url, quote=True)}\"><b>{title}</b></a>\n"
                f"{company} · {human_age(age)} · {src}")

    lines = [f"{badge} <b>{label.upper()}</b> · {human_age(age)}", "", f"💼 <b>{title}</b>",
             f"🏢 {company}"]
    where = MODE_LABEL.get(job.work_mode, "🌍 Remote")
    if job.location:
        where += f" · {escape(job.location)}"
    lines.append(where)
    if job.salary:
        lines.append(f"💰 {escape(job.salary)}")
    meta = list(dict.fromkeys(x for x in (job.job_type, job.seniority) if x))
    if meta:
        lines.append("📋 " + escape(" · ".join(meta)))
    if job.min_years is not None:
        lines.append(f"🎓 Asks {job.min_years}+ yrs" if job.min_years else "🎓 Freshers welcome")
    app = applicants_line(job.applicants)
    if app:
        lines.append(app)
    tags = " ".join(t for t in (_hashtag(x) for x in job.tags[:5]) if t)
    if tags:
        lines += ["", tags]
    foot = f"via {src}"
    if job.matched:
        foot += f" · matched “{escape(job.matched)}”"
    lines += ["", f"<i>{foot}</i>"]
    return "\n".join(lines)


def job_buttons(job: Job, job_id: int, counts: dict | None = None) -> list:
    """Same buttons for everyone (it's a shared group message); each tap is personal.
    Counts show how many people saved / applied."""
    counts = counts or {}
    src = SOURCE_NAMES.get(job.source, "site")
    n = lambda k: f" · {counts[k]}" if counts.get(k) else ""
    return [
        [{"text": f"🚀 Apply on {src}", "url": job.url}],
        [{"text": f"⭐ Save{n('saved')}", "callback_data": f"save:{job_id}"},
         {"text": f"✅ Applied{n('applied')}", "callback_data": f"applied:{job_id}"},
         {"text": "🙈 Not for me", "callback_data": f"hide:{job_id}"},
         {"text": "🔇 Mute co.", "callback_data": f"mute:{job_id}"}],
    ]


def job_list(title: str, items: list[tuple[int, Job]], now: datetime | None = None) -> str:
    if not items:
        return f"<b>{escape(title)}</b>\n\nNothing here yet."
    now = now or utcnow()
    rows = [f"<b>{escape(title)}</b> ({len(items)})", ""]
    for i, (_, j) in enumerate(items, 1):
        rows.append(f"{i}. <a href=\"{escape(j.url, quote=True)}\">{escape(j.title)}</a>\n"
                    f"    {escape(j.company)} · {SOURCE_NAMES.get(j.source, j.source)} · "
                    f"{human_age(j.age_minutes(now))}")
    return "\n".join(rows)
