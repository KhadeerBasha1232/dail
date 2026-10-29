"""Core data types."""
from __future__ import annotations

import re
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


def _norm(text: str) -> str:
    return re.sub(r"[^a-z0-9]+", "", (text or "").lower())


@dataclass
class Job:
    source: str                    # e.g. "linkedin", "remotive"
    source_id: str                 # id inside that source
    title: str
    company: str
    url: str                       # where the user applies
    location: str = ""
    posted_at: datetime | None = None   # timezone-aware UTC
    remote: bool = True
    work_mode: str = "remote"      # remote | hybrid | onsite
    salary: str = ""
    tags: list[str] = field(default_factory=list)
    job_type: str = ""             # Full-time, Internship, ...
    seniority: str = ""
    applicants: str = ""           # "56 applicants" (LinkedIn only)
    matched: str = ""              # search keyword / term that matched
    min_years: int | None = None   # experience the description asks for, if found

    @property
    def uid(self) -> str:
        return f"{self.source}:{self.source_id}"

    @property
    def fingerprint(self) -> str:
        """Same title + company on two boards counts as one job."""
        return f"{_norm(self.title)}|{_norm(self.company)}"

    def age_minutes(self, now: datetime | None = None) -> float | None:
        if not self.posted_at:
            return None
        now = now or utcnow()
        return max(0.0, (now - self.posted_at).total_seconds() / 60)

    def to_dict(self) -> dict:
        d = asdict(self)
        d["posted_at"] = self.posted_at.isoformat() if self.posted_at else None
        return d

    @classmethod
    def from_dict(cls, d: dict) -> "Job":
        d = dict(d)
        if d.get("posted_at"):
            d["posted_at"] = datetime.fromisoformat(d["posted_at"])
        return cls(**d)
