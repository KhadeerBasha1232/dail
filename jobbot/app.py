"""Scanner loop + Telegram command / button handling."""
from __future__ import annotations

import asyncio
import logging
import re
import time
from dataclasses import asdict, fields
from html import escape

import httpx

from .config import ALL_SOURCES, LINKEDIN_EXPERIENCE, WORK_MODES, Settings
from .filters import reject_reason
from .formatter import SOURCE_NAMES, human_age, job_buttons, job_card, job_list
from .models import Job, utcnow
from .sources.boards import BOARD_SOURCES, fetch_board
from .sources.linkedin import LinkedInSource
from .store import Store
from .telegram import Telegram, TelegramError

log = logging.getLogger("jobbot")

COMMANDS = [
    ("settings", "⚙️ Tap-to-change settings"),
    ("status", "📊 Sources, last scan, stats"),
    ("scan", "🔎 Scan right now"),
    ("latest", "🕐 Jobs sent in the last hour"),
    ("saved", "⭐ Your saved jobs"),
    ("applied", "✅ Jobs you applied to"),
    ("keywords", "🔤 Show LinkedIn search keywords"),
    ("addkw", "➕ Add keywords: /addkw Go Developer, SRE"),
    ("rmkw", "➖ Remove keywords: /rmkw Java Developer"),
    ("exclude", "🚫 Skip titles with words: /exclude php, wordpress"),
    ("include", "♻️ Stop skipping words: /include lead"),
    ("fresh", "⏱ LinkedIn max age in minutes: /fresh 15"),
    ("interval", "🔁 Minutes between scans: /interval 2"),
    ("mode", "🌍 remote | remote_hybrid | hybrid | any"),
    ("exp", "🎓 internship, entry, associate, mid_senior"),
    ("years", "🎓 Max years asked: /years 2 (or off)"),
    ("locations", "📍 LinkedIn locations: /locations India, Worldwide"),
    ("mute", "🔇 Mute company: /mute Acme"),
    ("unmute", "🔊 Unmute company"),
    ("addco", "🏢 Watch a company board: /addco greenhouse gitlab"),
    ("pause", "⏸ Pause alerts"),
    ("resume", "▶️ Resume alerts"),
    ("help", "❓ How to use this bot"),
]

# Taps anyone in the group may do (they only touch that person's own lists).
JOB_ACTIONS = {"save", "unsave", "applied", "unapply", "hide", "mute"}
# Commands anyone in the group may use, in the group or in a private chat with the bot.
PERSONAL_COMMANDS = {"start", "help", "menu", "saved", "applied", "latest"}

FRESH_STEPS = [5, 10, 15, 30, 60]
INTERVAL_STEPS = [60, 120, 300, 600]      # seconds between scans
BOARD_STEPS = [60, 360, 1440, 4320]
YEARS_STEPS = [0, 1, 2, 3, 5, -1]


def _csv(text: str) -> list[str]:
    return [x.strip() for x in re.split(r"[,\n]", text) if x.strip()]


def _next(options: list, current):
    return options[(options.index(current) + 1) % len(options)] if current in options else options[0]


def _every(sec: int) -> str:
    return f"{sec // 60} min" if sec % 60 == 0 else f"{sec} s"


def _hours(m: int) -> str:
    return f"{m} min" if m < 60 else (f"{m // 60} h" if m < 1440 else f"{m // 1440} d")


class JobBot:
    def __init__(self, settings: Settings, store: Store, token: str = "", chat_id: str = "",
                 admin_ids: set[int] | None = None, dry_run: bool = False):
        self.base = settings
        self.store = store
        self.settings = Settings().apply(asdict(settings)).apply(store.kv_get("overrides", {}))
        self.token, self.chat_id = token, str(chat_id)
        self.admin_ids = admin_ids or set()
        self.dry_run = dry_run
        self.linkedin = LinkedInSource()
        self.source_status: dict[str, str] = {}
        self.last_scan: dict = {}
        self.scan_now = asyncio.Event()
        self.client: httpx.AsyncClient | None = None
        self.tg: Telegram | None = None
        self.sent_log: list[tuple[str, list]] = []
        self.username = ""                            # bot's @name, for "open private chat" links
        self._members: dict[int, tuple[bool, float]] = {}   # dry-run output, used by tests

    # ---------------- settings ----------------
    def update(self, **changes):
        overrides = self.store.kv_get("overrides", {})
        for k, v in changes.items():
            if k == "sources":
                overrides["sources"] = {**overrides.get("sources", {}), **v}
                self.settings.sources = {**self.settings.sources, **v}
            else:
                overrides[k] = v
                setattr(self.settings, k, v)
        self.store.kv_set("overrides", overrides)

    # ---------------- scanning ----------------
    async def _collect(self) -> list[Job]:
        s = self.settings
        names = [n for n in BOARD_SOURCES if s.source_on(n)]
        coros = [fetch_board(n, self.client, s) for n in names]
        if s.source_on("linkedin"):
            names.append("linkedin")
            coros.append(self.linkedin.fetch(self.client, s))
        results = await asyncio.gather(*coros, return_exceptions=True)
        jobs = []
        for name, res in zip(names, results):
            if isinstance(res, Exception):
                self.source_status[name] = f"error: {type(res).__name__} {str(res)[:60]}"
                log.warning("%s failed: %s", name, res)
                continue
            self.source_status[name] = self.linkedin.last_status if name == "linkedin" \
                else f"ok · {len(res)} listed"
            jobs += res
        for n in ALL_SOURCES:
            if not s.source_on(n):
                self.source_status[n] = "off"
        return jobs

    def select(self, jobs: list[Job]) -> list[Job]:
        """New + passing filters, freshest first, one per fingerprint."""
        now = utcnow()
        picked, fps = [], set()
        for j in jobs:
            if j.fingerprint in fps or self.store.is_seen(j):
                continue
            why = reject_reason(j, self.settings, now)
            if why:
                log.debug("skip %s | %s: %s", j.source, j.title, why)
                continue
            fps.add(j.fingerprint)
            picked.append(j)
        picked.sort(key=lambda j: j.age_minutes(now) if j.posted_at else 1e9)
        return picked

    async def scan_once(self) -> dict:
        started = time.time()
        jobs = await self._collect()
        fresh = self.select(jobs)
        to_send = fresh[: self.settings.max_per_cycle]
        sent = 0
        for job in to_send:
            if job.source == "linkedin" and self.settings.linkedin_details:
                await self.linkedin.enrich(self.client, job)
                await asyncio.sleep(1.5)
                why = reject_reason(job, self.settings, utcnow())   # e.g. description asks 5 yrs
                if why:
                    log.info("dropped after details: %s @ %s (%s)", job.title, job.company, why)
                    continue
            if await self.deliver(job):
                sent += 1
                await asyncio.sleep(self.settings.send_delay_sec if not self.dry_run else 0)
        self.last_scan = {"at": time.time(), "took": time.time() - started, "listed": len(jobs),
                          "matched": len(fresh), "sent": sent}
        log.info("scan: %d listed, %d new matches, %d sent (%.0fs)",
                 len(jobs), len(fresh), sent, self.last_scan["took"])
        return self.last_scan

    async def deliver(self, job: Job) -> bool:
        job_id = self.store.record(job, self.chat_id)
        text = job_card(job, style=self.settings.style)
        buttons = job_buttons(job, job_id)
        if self.settings.style == "compact":
            buttons = buttons[:1]
        if self.dry_run:
            self.sent_log.append((text, buttons))
            print("\n" + "─" * 48 + "\n" + re.sub(r"<[^>]+>", "", text) + f"\n[ {job.url} ]")
            return True
        try:
            msg = await self.tg.send(self.chat_id, text, buttons)
            self.store.set_message(job_id, self.chat_id, msg["message_id"])
            return True
        except TelegramError as e:
            log.error("send failed for %s: %s", job.uid, e)
            self.store.db.execute("DELETE FROM jobs WHERE id=?", (job_id,))
            self.store.db.commit()
            return False

    async def scanner_loop(self):
        while True:
            if not self.settings.paused:
                try:
                    await self.scan_once()
                except Exception:
                    log.exception("scan crashed; will retry next cycle")
            # Wait in short steps so a new interval from /settings applies right away.
            done_at = time.time()
            while not self.scan_now.is_set() and time.time() - done_at < self.settings.scan_interval_sec:
                try:
                    await asyncio.wait_for(self.scan_now.wait(), timeout=2)
                except asyncio.TimeoutError:
                    pass
            self.scan_now.clear()

    # ---------------- texts ----------------
    def settings_text(self) -> str:
        s = self.settings
        years = "any" if s.max_years_experience < 0 else f"≤ {s.max_years_experience} yrs"
        on = [SOURCE_NAMES[n] for n in ALL_SOURCES if s.source_on(n)]
        return "\n".join([
            "⚙️ <b>Settings</b>  <i>(tap buttons to change)</i>", "",
            f"{'⏸ <b>PAUSED</b>' if s.paused else '▶️ Running'} · scans every <b>{_every(s.scan_interval_sec)}</b>",
            f"🌍 Work mode: <b>{s.work_mode.replace('_', ' + ')}</b>",
            f"⏱ LinkedIn: posted in last <b>{s.linkedin_max_age_min} min</b>",
            f"⏱ Other boards: last <b>{_hours(s.board_max_age_min)}</b>",
            f"🎓 Level: <b>{', '.join(s.experience) or 'any'}</b> · experience asked {years}",
            f"🗺 Region filter: <b>{'on' if s.region_filter else 'off'}</b>"
            + (f" ({', '.join(r for r in s.allowed_regions if r != 'remote')})" if s.region_filter else ""),
            f"📍 LinkedIn locations: {escape(', '.join(s.linkedin_locations))}",
            f"🔤 {len(s.keywords)} keywords · 🚫 {len(s.exclude_title_words)} skip-words · "
            f"🔇 {len(s.muted_companies)} muted",
            f"🎨 Message style: <b>{s.style}</b>",
            f"📡 Sources on ({len(on)}): {escape(', '.join(on))}",
        ])

    def settings_buttons(self) -> list:
        s = self.settings
        b = lambda t, d: {"text": t, "callback_data": d}
        exp_row = [b(("✅ " if e in s.experience else "▫️ ") + e.replace("_", "-").title(), f"exp:{e}")
                   for e in ("internship", "entry", "associate", "mid_senior")]
        years = "any" if s.max_years_experience < 0 else f"≤{s.max_years_experience}y"
        return [
            [b(f"🌍 Mode: {s.work_mode.replace('_', '+')}", "set:mode"),
             b(f"⏱ LinkedIn: {s.linkedin_max_age_min}m", "set:fresh")],
            [b(f"⏱ Boards: {_hours(s.board_max_age_min)}", "set:bfresh"),
             b(f"🎓 Exp asked: {years}", "set:years")],
            exp_row,
            [b(f"🔁 Scan every: {_every(s.scan_interval_sec)}", "set:interval")],
            [b(f"🗺 Region: {'on' if s.region_filter else 'off'}", "set:region"),
             b(f"🎨 Style: {s.style}", "set:style")],
            [b("📡 Sources", "menu:sources"),
             b("▶️ Resume" if s.paused else "⏸ Pause", "set:pause"),
             b("🔎 Scan now", "menu:scan")],
        ]

    def sources_buttons(self) -> list:
        s = self.settings
        btns = [{"text": ("✅ " if s.source_on(n) else "▫️ ") + SOURCE_NAMES[n], "callback_data": f"src:{n}"}
                for n in ALL_SOURCES]
        rows = [btns[i:i + 2] for i in range(0, len(btns), 2)]
        rows.append([{"text": "⬅️ Back to settings", "callback_data": "menu:settings"}])
        return rows

    def status_text(self) -> str:
        st = self.store.stats()
        ls = self.last_scan
        if ls:
            nxt = max(0, self.settings.scan_interval_sec - (time.time() - ls["at"]))
            scan = (f"{human_age((time.time() - ls['at']) / 60)} (took {ls['took']:.0f}s) · "
                    f"next in {nxt / 60:.0f} min\n   {ls['listed']} listed → {ls['matched']} new matches → "
                    f"{ls['sent']} sent")
        else:
            scan = "not yet"
        src = []
        for n in ALL_SOURCES:
            v = self.source_status.get(n, "waiting for first scan" if self.settings.source_on(n) else "off")
            icon = "⏸" if v == "off" else ("❌" if v.startswith("error") else
                                          ("⏳" if "cooling" in v or "rate" in v else "✅"))
            src.append(f"{icon} {SOURCE_NAMES[n]} — {escape(v)}")
        today = ", ".join(f"{SOURCE_NAMES.get(k, k)} {v}" for k, v in st["per_source_today"].items())
        return "\n".join([
            "📊 <b>Job Bot status</b>", "",
            f"State: {'⏸ paused' if self.settings.paused else '▶️ running'}",
            f"Last scan: {scan}",
            f"Sent today: <b>{st['today']}</b>" + (f" ({escape(today)})" if today else ""),
            f"All time: {st['total']} jobs · ⭐ {st['saved']} saves · ✅ {st['applied']} applications"
            f" by {st['people']} people", "",
            "<b>Sources</b>", *src,
        ])

    def help_text(self) -> str:
        return "\n".join([
            "👋 <b>Remote Job Radar</b>", "",
            "I watch LinkedIn every few minutes for <b>remote</b> jobs posted in the last "
            f"<b>{self.settings.linkedin_max_age_min} min</b>, plus 10 remote job boards and company "
            "career pages (Greenhouse, Lever, Ashby).", "",
            "<b>On every job</b>: 🚀 Apply · ⭐ Save · ✅ Applied · 🙈 Not for me · 🔇 Mute company",
            "⭐ ✅ 🙈 are <b>just for you</b>: everyone has their own lists. Tap again to undo.", "",
            "<b>Quick commands</b>",
            "/settings – tap to change mode, freshness, level, sources",
            "/status – what each source is doing",
            "/scan – check right now",
            "/saved · /applied – your own lists (sent to you privately) · /latest",
            "/addkw · /rmkw · /keywords – LinkedIn searches",
            "/exclude · /include – skip titles with words",
            "/mute · /unmute – hide a company",
            "/interval 2 – scan every 2 min · /fresh 10 · /mode remote",
            "/exp entry,internship · /years 2",
            "/addco greenhouse stripe – watch a company's career page",
            "/pause · /resume",
        ])

    # ---------------- telegram input ----------------
    def _allowed(self, chat_id, user_id) -> bool:
        if user_id and user_id in self.admin_ids:
            return True
        return str(chat_id) == self.chat_id and (not self.admin_ids or user_id is None)

    async def reply(self, chat_id, text: str, buttons: list | None = None):
        if self.dry_run:
            self.sent_log.append((text, buttons or []))
            return
        await self.tg.send(chat_id, text, buttons)

    async def send_personal_list(self, chat_id, user: dict | None, which: str) -> None:
        """/saved and /applied: your own list, sent to you privately so the group stays clean."""
        if not user:
            return await self.reply(chat_id, "Send /saved or /applied in a private chat with me.")
        uid, name = user["id"], escape(user.get("first_name") or "there")
        items = self.store.user_jobs(uid, which)
        mine = self.store.user_stats(uid)
        title = ("⭐ Your saved jobs" if which == "saved" else "✅ Jobs you applied to")
        text = job_list(title, items) + (f"\n\n<i>Total: ⭐ {mine.get('saved', 0)} saved · "
                                         f"✅ {mine.get('applied', 0)} applied</i>")
        if str(chat_id) == str(uid):                # already in private chat
            return await self.reply(chat_id, text)
        try:
            await self.tg.send(uid, text)
            await self.reply(chat_id, f"📬 {name}, I sent your list to you privately.")
        except TelegramError:
            link = f"https://t.me/{self.username}?start={which}" if self.username else None
            await self.reply(chat_id, f"🔒 {name}, your list is private. Open a chat with me and press "
                                      f"<b>Start</b> once, then I can send it there.",
                             [[{"text": "💬 Open private chat", "url": link}]] if link else None)

    async def handle_command(self, chat_id, text: str, user: dict | None = None) -> None:
        cmd, _, arg = text.strip().partition(" ")
        cmd = cmd.lstrip("/").split("@")[0].lower()
        arg = arg.strip()
        s = self.settings
        r = lambda t, b=None: self.reply(chat_id, t, b)

        if cmd == "start" and arg in ("saved", "applied"):   # deep link from the group
            await self.send_personal_list(chat_id, user, arg)
        elif cmd in ("start", "help", "menu"):
            await r(self.help_text(), [[{"text": "⚙️ Settings", "callback_data": "menu:settings"},
                                        {"text": "📊 Status", "callback_data": "menu:status"},
                                        {"text": "🔎 Scan now", "callback_data": "menu:scan"}]])
        elif cmd == "settings":
            await r(self.settings_text(), self.settings_buttons())
        elif cmd == "status":
            await r(self.status_text())
        elif cmd == "scan":
            self.scan_now.set()
            await r("🔎 Scanning now… new jobs will appear here in a minute.")
        elif cmd in ("saved", "applied"):
            await self.send_personal_list(chat_id, user, cmd)
        elif cmd == "latest":
            await r(job_list("🕐 Sent in the last hour", self.store.recent(60, 15)))
        elif cmd == "keywords":
            await r("🔤 <b>LinkedIn keywords</b>\n\n" + "\n".join(f"• {escape(k)}" for k in s.keywords)
                    + "\n\n/addkw or /rmkw to change")
        elif cmd == "addkw" and arg:
            new = [k for k in _csv(arg) if k.lower() not in {x.lower() for x in s.keywords}]
            self.update(keywords=s.keywords + new)
            await r(f"➕ Added: {escape(', '.join(new)) or 'nothing new'} · {len(s.keywords)} keywords")
        elif cmd == "rmkw" and arg:
            drop = {k.lower() for k in _csv(arg)}
            self.update(keywords=[k for k in s.keywords if k.lower() not in drop])
            await r(f"➖ Removed. {len(s.keywords)} keywords left.")
        elif cmd == "exclude" and arg:
            self.update(exclude_title_words=sorted(set(s.exclude_title_words) | {w.lower() for w in _csv(arg)}))
            await r("🚫 Skipping titles with: " + escape(", ".join(s.exclude_title_words)))
        elif cmd == "include" and arg:
            drop = {w.lower() for w in _csv(arg)}
            self.update(exclude_title_words=[w for w in s.exclude_title_words if w not in drop])
            await r("♻️ Skip-words now: " + escape(", ".join(s.exclude_title_words) or "none"))
        elif cmd == "mute" and arg:
            self.update(muted_companies=sorted(set(s.muted_companies) | {arg}))
            await r(f"🔇 Muted {escape(arg)}")
        elif cmd == "unmute" and arg:
            self.update(muted_companies=[c for c in s.muted_companies if c.lower() != arg.lower()])
            await r(f"🔊 Unmuted {escape(arg)}")
        elif cmd == "muted":
            await r("🔇 Muted: " + (escape(", ".join(s.muted_companies)) or "none"))
        elif cmd == "interval" and arg.isdigit():
            self.update(scan_interval_sec=max(1, min(60, int(arg))) * 60)
            warn = ("\n⚠️ Scanning this often makes LinkedIn blocks more likely."
                    if s.scan_interval_sec < 120 else "")
            await r(f"🔁 Scanning every {_every(s.scan_interval_sec)}.{warn}")
        elif cmd == "fresh" and arg.isdigit():
            self.update(linkedin_max_age_min=max(1, min(1440, int(arg))))
            await r(f"⏱ LinkedIn: only jobs posted in the last {s.linkedin_max_age_min} min")
        elif cmd == "mode" and arg in WORK_MODES:
            self.update(work_mode=arg)
            await r(f"🌍 Work mode: {arg}")
        elif cmd == "exp" and arg:
            levels = [e for e in _csv(arg.lower()) if e in LINKEDIN_EXPERIENCE]
            self.update(experience=levels)
            await r(f"🎓 Levels: {', '.join(levels) or 'any'}")
        elif cmd == "years" and arg:
            self.update(max_years_experience=-1 if arg.lower() in ("off", "any") else int(arg) if arg.isdigit() else s.max_years_experience)
            await r(f"🎓 Max experience asked: {'any' if s.max_years_experience < 0 else s.max_years_experience}")
        elif cmd == "locations" and arg:
            self.update(linkedin_locations=_csv(arg))
            await r("📍 LinkedIn locations: " + escape(", ".join(s.linkedin_locations)))
        elif cmd == "addco":
            kind, _, slug = arg.partition(" ")
            if kind in ("greenhouse", "lever", "ashby") and slug:
                key = f"{kind}_companies"
                self.update(**{key: sorted(set(getattr(s, key)) | {slug.strip().lower()})})
                await r(f"🏢 Watching {escape(slug)} on {kind.title()}")
            else:
                await r("Usage: /addco greenhouse|lever|ashby company-slug\n"
                        "The slug is in the careers URL, e.g. boards.greenhouse.io/<b>stripe</b>")
        elif cmd in ("pause", "resume"):
            self.update(paused=cmd == "pause")
            await r("⏸ Paused. /resume to continue." if s.paused else "▶️ Resumed.")
            if not s.paused:
                self.scan_now.set()
        else:
            await r("🤔 Unknown command or missing value. /help shows everything.")

    async def handle_job_tap(self, cq: dict, action: str, job_id: int) -> None:
        """Save / Applied / Not-for-me are personal to whoever tapped. Mute affects the whole group."""
        msg = cq.get("message") or {}
        chat_id = (msg.get("chat") or {}).get("id")
        mid = msg.get("message_id")
        user_id = (cq.get("from") or {}).get("id")
        got = self.store.get(job_id)
        if not got or not user_id:
            return await self.tg.answer(cq["id"], "That job is gone.")
        job, _ = got

        if action == "mute":
            if not self._allowed(self.chat_id, user_id):
                return await self.tg.answer(cq["id"], "Only admins can mute a company for everyone.", True)
            self.update(muted_companies=sorted(set(self.settings.muted_companies) | {job.company}))
            return await self.tg.answer(cq["id"], f"🔇 No more jobs from {job.company} for this group")

        target = {"save": "saved", "unsave": "saved", "applied": "applied",
                  "unapply": "applied", "hide": "hidden"}[action]
        current = self.store.user_status(user_id, job_id)
        if current == target:                       # second tap undoes it
            self.store.set_user_status(user_id, job_id, None)
            toast = {"saved": "Removed from your saved jobs", "applied": "Removed from your applied list",
                     "hidden": "Un-hidden"}[target]
        else:
            self.store.set_user_status(user_id, job_id, target)
            toast = {"saved": "⭐ Saved to your list. /saved to see it",
                     "applied": "✅ Nice! Added to your applied list (/applied)",
                     "hidden": "🙈 Got it. Hidden from your lists"}[target]
        if mid and target != "hidden":
            await self.tg.edit_buttons(chat_id, mid, job_buttons(job, job_id, self.store.job_counts(job_id)))
        await self.tg.answer(cq["id"], toast)

    async def handle_callback(self, cq: dict) -> None:
        data = cq.get("data", "")
        msg = cq.get("message") or {}
        chat_id = (msg.get("chat") or {}).get("id")
        mid = msg.get("message_id")
        action, _, val = data.partition(":")
        s = self.settings
        toast = ""

        if action in ("save", "unsave", "applied", "unapply", "hide", "mute") and val.isdigit():
            return await self.handle_job_tap(cq, action, int(val))

        if action == "set":
            if val == "mode":
                self.update(work_mode=_next(list(WORK_MODES), s.work_mode))
            elif val == "interval":
                self.update(scan_interval_sec=_next(INTERVAL_STEPS, s.scan_interval_sec))
                if s.scan_interval_sec < 120:
                    toast = "🔁 Every 1 min. LinkedIn may block more often."
            elif val == "fresh":
                self.update(linkedin_max_age_min=_next(FRESH_STEPS, s.linkedin_max_age_min))
            elif val == "bfresh":
                self.update(board_max_age_min=_next(BOARD_STEPS, s.board_max_age_min))
            elif val == "years":
                self.update(max_years_experience=_next(YEARS_STEPS, s.max_years_experience))
            elif val == "region":
                self.update(region_filter=not s.region_filter)
            elif val == "style":
                self.update(style="compact" if s.style == "card" else "card")
            elif val == "pause":
                self.update(paused=not s.paused)
                if not s.paused:
                    self.scan_now.set()
        elif action == "exp" and val in LINKEDIN_EXPERIENCE:
            exp = [e for e in s.experience if e != val] if val in s.experience else s.experience + [val]
            self.update(experience=exp)
        elif action == "src" and val in ALL_SOURCES:
            self.update(sources={val: not s.source_on(val)})
            await self.tg.edit_text(chat_id, mid, self.settings_text(), self.sources_buttons())
            return await self.tg.answer(cq["id"], f"{SOURCE_NAMES[val]}: {'on' if s.source_on(val) else 'off'}")
        elif action == "menu":
            if val == "sources":
                await self.tg.edit_text(chat_id, mid, self.settings_text(), self.sources_buttons())
                return await self.tg.answer(cq["id"])
            if val == "status":
                await self.reply(chat_id, self.status_text())
                return await self.tg.answer(cq["id"])
            if val == "scan":
                self.scan_now.set()
                return await self.tg.answer(cq["id"], "🔎 Scanning now…")
        await self.tg.edit_text(chat_id, mid, self.settings_text(), self.settings_buttons())
        await self.tg.answer(cq["id"], toast or "Saved ✔")

    async def updates_loop(self):
        offset = self.store.kv_get("tg_offset")
        while True:
            try:
                ups = await self.tg.updates(offset)
            except TelegramError as e:
                log.warning("getUpdates: %s", e)
                await asyncio.sleep(60 if "webhook" in str(e).lower() else 5)
                continue
            for u in ups:
                offset = u["update_id"] + 1
                self.store.kv_set("tg_offset", offset)
                try:
                    await self._dispatch(u)
                except Exception:
                    log.exception("handling update failed")

    async def _is_member(self, user_id: int) -> bool:
        """Is this person in the jobs group? Cached for 10 min."""
        if user_id in self.admin_ids:
            return True
        hit = self._members.get(user_id)
        if hit and time.time() - hit[1] < 600:
            return hit[0]
        try:
            m = await self.tg.call("getChatMember", chat_id=self.chat_id, user_id=user_id)
            ok = (m or {}).get("status") in ("creator", "administrator", "member", "restricted")
        except TelegramError:
            ok = False
        self._members[user_id] = (ok, time.time())
        return ok

    async def _dispatch(self, u: dict):
        if "callback_query" in u:
            cq = u["callback_query"]
            chat = ((cq.get("message") or {}).get("chat") or {}).get("id")
            uid = (cq.get("from") or {}).get("id")
            action = (cq.get("data") or "").partition(":")[0]
            if action in JOB_ACTIONS and (str(chat) == self.chat_id or chat == uid):
                await self.handle_callback(cq)            # personal taps: anyone in the group
            elif self._allowed(chat, uid):
                await self.handle_callback(cq)
            else:
                await self.tg.answer(cq["id"], "Only admins can change settings.")
            return
        m = u.get("message") or u.get("channel_post")
        if not m or not (m.get("text") or "").startswith("/"):
            return
        chat = m["chat"]
        user = m.get("from")
        uid = (user or {}).get("id")
        cmd = m["text"].split()[0].lstrip("/").split("@")[0].lower()
        if cmd in PERSONAL_COMMANDS and user:
            if chat.get("type") == "private" and not await self._is_member(uid):
                await self.reply(chat["id"], "👋 This bot is for members of the jobs group. Join it first.")
                return
            await self.handle_command(chat["id"], m["text"], user)
        elif self._allowed(chat["id"], uid):
            await self.handle_command(chat["id"], m["text"], user)

    # ---------------- run ----------------
    async def run(self, once: bool = False):
        limits = httpx.Limits(max_connections=20)
        async with httpx.AsyncClient(timeout=30, follow_redirects=True, limits=limits) as client:
            self.client = client
            if self.dry_run:
                await self.scan_once()
                return
            self.tg = Telegram(self.token, client)
            me = await self.tg.call("getMe")
            self.username = me["username"]
            log.info("Logged in as @%s, posting to %s", me["username"], self.chat_id)
            hook = (await self.tg.call("getWebhookInfo")).get("url")
            if once:
                await self.scan_once()
                return
            if hook:
                log.error("This bot has a webhook set (%s), so Telegram sends button taps and commands "
                          "there instead of here. Alerts still send, but buttons/commands won't work. "
                          "If that isn't yours, revoke the token in @BotFather, then run: "
                          "python main.py --reset-webhook", hook)
            try:
                await self.tg.set_commands(COMMANDS)
            except TelegramError as e:
                log.info("setMyCommands: %s", e)
            await self.reply(self.chat_id, "🤖 <b>Remote Job Radar is online</b>\n\n" + self.settings_text(),
                             self.settings_buttons())
            await asyncio.gather(self.scanner_loop(), self.updates_loop())
