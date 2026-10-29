"""Settings: defaults <- config.toml <- live overrides changed from Telegram."""
from __future__ import annotations

import os
import tomllib
from dataclasses import dataclass, field, fields
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent

LINKEDIN_EXPERIENCE = {
    "internship": "1", "entry": "2", "associate": "3",
    "mid_senior": "4", "director": "5", "executive": "6",
}
LINKEDIN_WORK_MODE = {"onsite": "1", "remote": "2", "hybrid": "3"}
LINKEDIN_JOB_TYPE = {
    "full_time": "F", "part_time": "P", "contract": "C",
    "temporary": "T", "internship": "I", "volunteer": "V",
}
WORK_MODES = ("remote", "remote_hybrid", "hybrid", "any")
ALL_SOURCES = (
    "linkedin", "remotive", "remoteok", "himalayas", "jobicy",
    "workingnomads", "weworkremotely", "arbeitnow", "greenhouse", "lever", "ashby",
)


@dataclass
class Settings:
    # --- what to search ---
    keywords: list[str] = field(default_factory=lambda: [
        "Python Developer", "Backend Engineer", "Full Stack Developer", "Software Engineer",
        "Frontend Engineer", "React Developer", "Java Developer", "Django Developer",
        "FastAPI Developer", "Spring Boot Developer", "MERN Stack Developer", "Node.js Developer",
        "Blockchain Developer", "Data Scientist", "Machine Learning Engineer", "AI Engineer",
        "Software Developer Intern",
    ])
    # Job boards return everything; a title must contain one of these to pass.
    match_terms: list[str] = field(default_factory=lambda: [
        "python", "backend", "back-end", "back end", "full stack", "fullstack", "full-stack",
        "software engineer", "software developer", "frontend", "front-end", "front end",
        "react", "java", "django", "flask", "fastapi", "spring", "mern", "node",
        "blockchain", "web3", "data scientist", "machine learning", "ml engineer",
        "ai engineer", "llm", "developer", "sde", "programmer", "data engineer",
    ])
    exclude_title_words: list[str] = field(default_factory=lambda: [
        "senior", "sr", "sr.", "lead", "principal", "staff", "manager", "head",
        "director", "architect", "vp",
    ])
    muted_companies: list[str] = field(default_factory=list)
    # Drop jobs whose description asks for more than N years. -1 turns this off.
    max_years_experience: int = 2

    # --- LinkedIn ---
    linkedin_locations: list[str] = field(default_factory=lambda: ["India"])
    experience: list[str] = field(default_factory=lambda: ["internship", "entry"])
    job_types: list[str] = field(default_factory=lambda: ["full_time", "internship"])
    work_mode: str = "remote"               # remote | remote_hybrid | hybrid | any
    linkedin_max_age_min: int = 15          # only jobs posted in the last N minutes
    linkedin_group_size: int = 6            # keywords per OR-search (fewer requests)
    linkedin_max_pages: int = 4
    linkedin_delay_sec: float = 4.0
    linkedin_details: bool = True           # fetch applicant count + seniority
    linkedin_title_match: bool = True       # also require a match_terms word in LinkedIn titles

    # --- other boards ---
    board_max_age_min: int = 1440       # boards post less often; seen-store prevents repeats
    region_filter: bool = True              # drop remote jobs you can't take (e.g. "US only")
    allowed_regions: list[str] = field(default_factory=lambda: [
        "worldwide", "anywhere", "global", "india", "asia", "apac", "remote",
    ])
    greenhouse_companies: list[str] = field(default_factory=lambda: [
        "gitlab", "razorpaysoftwareprivatelimited", "hackerrank", "vercel", "grafanalabs",
    ])
    lever_companies: list[str] = field(default_factory=lambda: ["cred", "meesho", "zeta"])
    ashby_companies: list[str] = field(default_factory=lambda: [
        "supabase", "posthog", "linear", "zapier",
    ])

    # --- delivery ---
    sources: dict[str, bool] = field(default_factory=lambda: {s: True for s in ALL_SOURCES})
    scan_interval_sec: int = 300
    max_per_cycle: int = 15
    send_delay_sec: float = 3.0
    style: str = "card"                     # card | compact
    paused: bool = False

    def source_on(self, name: str) -> bool:
        return self.sources.get(name, False)

    def apply(self, overrides: dict) -> "Settings":
        names = {f.name for f in fields(self)}
        for k, v in overrides.items():
            if k == "sources":
                self.sources = {**self.sources, **v}
            elif k in names:
                setattr(self, k, v)
        return self


def load_settings(path: Path | None = None) -> Settings:
    s = Settings()
    path = path or ROOT / "config.toml"
    if path.exists():
        with open(path, "rb") as f:
            s.apply(tomllib.load(f))
    return s


def load_env(path: Path | None = None) -> dict:
    """Read .env without needing python-dotenv."""
    path = path or ROOT / ".env"
    if path.exists():
        for line in path.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if line and not line.startswith("#") and "=" in line:
                k, v = line.split("=", 1)
                os.environ.setdefault(k.strip(), v.strip().strip('"').strip("'"))
    admins = {int(x) for x in os.environ.get("ADMIN_IDS", "").replace(" ", "").split(",") if x}
    return {
        "token": os.environ.get("BOT_TOKEN", ""),
        "chat_id": os.environ.get("CHAT_ID", ""),
        "admin_ids": admins,
    }
