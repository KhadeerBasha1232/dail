"""LinkedIn public (guest) job search. No login needed, but it rate-limits hard."""
from __future__ import annotations

import asyncio
import logging
import random
import re
import time

import httpx
from bs4 import BeautifulSoup

from ..config import LINKEDIN_EXPERIENCE, LINKEDIN_JOB_TYPE, Settings
from ..models import Job, utcnow
from .common import HEADERS, ago, clean, relative_minutes, remote_mode, years_required

log = logging.getLogger("jobbot.linkedin")

SEARCH_URL = "https://www.linkedin.com/jobs-guest/jobs/api/seeMoreJobPostings/search"
DETAIL_URL = "https://www.linkedin.com/jobs-guest/jobs/api/jobPosting/{id}"
PAGE_SIZE = 10


def build_params(keyword: str, location: str, s: Settings, start: int = 0) -> dict:
    p = {
        "keywords": keyword,
        "location": location,
        "f_TPR": f"r{max(60, s.linkedin_max_age_min * 60)}",
        "sortBy": "DD",
        "start": str(start),
    }
    exp = ",".join(LINKEDIN_EXPERIENCE[e] for e in s.experience if e in LINKEDIN_EXPERIENCE)
    if exp:
        p["f_E"] = exp
    wt = {"remote": "2", "hybrid": "3", "remote_hybrid": "2,3"}.get(s.work_mode)
    if wt:
        p["f_WT"] = wt
    jt = ",".join(LINKEDIN_JOB_TYPE[t] for t in s.job_types if t in LINKEDIN_JOB_TYPE)
    if jt:
        p["f_JT"] = jt
    return p


def parse_cards(html: str, s: Settings, keyword: str = "") -> list[Job]:
    soup = BeautifulSoup(html, "lxml")
    now = utcnow()
    default_mode = "hybrid" if s.work_mode == "hybrid" else "remote"
    jobs = []
    for card in soup.select("div.base-card"):
        urn = card.get("data-entity-urn", "")
        if "jobPosting:" not in urn:
            continue
        job_id = urn.split("jobPosting:")[-1]
        link = card.select_one("a.base-card__full-link")
        title = card.select_one("h3.base-search-card__title")
        company = card.select_one("h4.base-search-card__subtitle")
        location = card.select_one("span.job-search-card__location")
        salary = card.select_one("span.job-search-card__salary-info")
        t = card.find("time")
        mins = relative_minutes(t.get_text()) if t else None
        url = (link.get("href", "") if link else "").split("?")[0] or \
            f"https://www.linkedin.com/jobs/view/{job_id}"
        loc = clean(location.get_text()) if location else ""
        jobs.append(Job(
            source="linkedin",
            source_id=job_id,
            title=clean(title.get_text()) if title else "Untitled",
            company=clean(company.get_text()) if company else "Unknown",
            url=url,
            location=loc,
            posted_at=ago(mins, now) if mins is not None else None,
            work_mode=remote_mode(loc, default_mode),
            salary=clean(salary.get_text()) if salary else "",
            matched=keyword,
        ))
    return jobs


def parse_detail(html: str, job: Job) -> Job:
    soup = BeautifulSoup(html, "lxml")
    n = soup.select_one(".num-applicants__caption")
    if n:
        job.applicants = clean(n.get_text())
    for item in soup.select(".description__job-criteria-item"):
        head = item.select_one(".description__job-criteria-subheader")
        val = item.select_one(".description__job-criteria-text")
        if not head or not val:
            continue
        h, v = clean(head.get_text()).lower(), clean(val.get_text())
        if "seniority" in h and v.lower() != "not applicable":
            job.seniority = v
        elif "employment" in h:
            job.job_type = v
    desc = soup.select_one(".show-more-less-html__markup, .description__text")
    if desc:
        job.min_years = years_required(desc.get_text(" "))
    return job


def keyword_groups(keywords: list[str], size: int) -> list[list[str]]:
    """LinkedIn accepts '"A" OR "B"', so 17 keywords become 3 searches instead of 17."""
    size = max(1, size)
    return [keywords[i:i + size] for i in range(0, len(keywords), size)]


def best_keyword(title: str, group: list[str]) -> str:
    """Which keyword of an OR-search this title most looks like."""
    words = set(re.findall(r"[a-z0-9.+#]+", title.lower()))
    generic = {"developer", "engineer", "intern", "stack", "software", "full"}

    def score(k):
        kw = re.findall(r"[a-z0-9.+#]+", k.lower())
        specific = [w for w in kw if w not in generic] or kw
        hits = sum(w in words for w in specific)
        return (hits / max(1, len(specific)), sum(w in words for w in kw))
    best = max(group, key=score)
    return best if score(best)[0] >= 0.5 else ""


class LinkedInSource:
    name = "linkedin"

    def __init__(self):
        self.cooldown_until = 0.0
        self.backoff = 120.0
        self.last_status = "not run yet"

    @property
    def cooling_down(self) -> bool:
        return time.time() < self.cooldown_until

    def _rate_limited(self):
        self.cooldown_until = time.time() + self.backoff
        self.last_status = f"rate-limited, pausing {self.backoff / 60:.0f} min"
        log.warning("LinkedIn %s", self.last_status)
        self.backoff = min(self.backoff * 2, 1800)

    async def _get(self, client, url, params=None):
        """GET with one polite retry on 429. Returns None if still limited."""
        for attempt in range(2):
            r = await client.get(url, params=params, headers=HEADERS)
            if r.status_code != 429:
                return r
            if attempt == 0:
                await asyncio.sleep(20 + random.random() * 10)
        self._rate_limited()
        return None

    async def fetch(self, client: httpx.AsyncClient, s: Settings) -> list[Job]:
        if self.cooling_down:
            left = (self.cooldown_until - time.time()) / 60
            self.last_status = f"cooling down ({left:.0f} min left)"
            return []
        jobs: dict[str, Job] = {}
        requests = 0
        for group in keyword_groups(s.keywords, s.linkedin_group_size):
            query = " OR ".join(f'"{k}"' for k in group) if len(group) > 1 else group[0]
            for location in s.linkedin_locations:
                for page in range(s.linkedin_max_pages):
                    if requests:
                        await asyncio.sleep(s.linkedin_delay_sec + random.random())
                    requests += 1
                    params = build_params(query, location, s, start=page * PAGE_SIZE)
                    try:
                        r = await self._get(client, SEARCH_URL, params)
                    except httpx.HTTPError as e:
                        log.info("LinkedIn request failed (%s): %s", query, e)
                        break
                    if r is None:
                        return list(jobs.values())
                    if r.status_code != 200:
                        log.info("LinkedIn %s for %r/%s", r.status_code, query, location)
                        break
                    found = parse_cards(r.text, s)
                    for j in found:
                        j.matched = best_keyword(j.title, group)
                        jobs.setdefault(j.source_id, j)
                    if len(found) < PAGE_SIZE:
                        break
        self.backoff = 120.0
        self.last_status = f"ok · {requests} searches · {len(jobs)} fresh jobs"
        return list(jobs.values())

    async def enrich(self, client: httpx.AsyncClient, job: Job) -> Job:
        if self.cooling_down:
            return job
        try:
            r = await self._get(client, DETAIL_URL.format(id=job.source_id))
            if r is not None and r.status_code == 200:
                parse_detail(r.text, job)
        except httpx.HTTPError as e:
            log.info("LinkedIn detail failed for %s: %s", job.source_id, e)
        return job
