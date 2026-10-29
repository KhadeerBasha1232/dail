"""Free public job APIs. Each parser takes the decoded response and returns Jobs,
so they can be tested offline with saved samples."""
from __future__ import annotations

import logging

import httpx
from bs4 import BeautifulSoup

from ..config import Settings
from ..models import Job
from .common import HEADERS, clean, fmt_money, parse_date, remote_mode, years_required

log = logging.getLogger("jobbot.boards")


def _text(html: str) -> str:
    return BeautifulSoup(html or "", "lxml").get_text(" ") if html else ""


# ---------- parsers ----------

def parse_remotive(data: dict) -> list[Job]:
    out = []
    for j in data.get("jobs", []):
        out.append(Job(
            source="remotive", source_id=str(j["id"]), title=clean(j.get("title")),
            company=clean(j.get("company_name")), url=j.get("url", ""),
            location=clean(j.get("candidate_required_location")),
            posted_at=parse_date(j.get("publication_date")),
            salary=clean(j.get("salary")), tags=[t for t in j.get("tags", [])][:6],
            job_type=clean(j.get("job_type", "")).replace("_", " ").title(),
            min_years=years_required(_text(j.get("description", ""))),
        ))
    return out


def parse_remoteok(data: list) -> list[Job]:
    out = []
    for j in data:
        if not isinstance(j, dict) or "id" not in j:
            continue          # first element is the legal notice
        out.append(Job(
            source="remoteok", source_id=str(j["id"]), title=clean(j.get("position")),
            company=clean(j.get("company")), url=j.get("apply_url") or j.get("url", ""),
            location=clean(j.get("location")), posted_at=parse_date(j.get("epoch") or j.get("date")),
            salary=fmt_money(j.get("salary_min"), j.get("salary_max"), "USD", "annual"),
            tags=j.get("tags", [])[:6],
            min_years=years_required(_text(j.get("description", ""))),
        ))
    return out


def parse_himalayas(data: dict) -> list[Job]:
    out = []
    for j in data.get("jobs", []):
        locs = j.get("locationRestrictions") or []
        out.append(Job(
            source="himalayas", source_id=j.get("guid") or j.get("applicationLink", ""),
            title=clean(j.get("title")), company=clean(j.get("companyName")),
            url=j.get("applicationLink") or j.get("guid", ""),
            location=", ".join(locs) if locs else "Worldwide",
            posted_at=parse_date(j.get("pubDate")),
            salary=fmt_money(j.get("minSalary"), j.get("maxSalary"), j.get("currency") or "USD",
                             j.get("salaryPeriod", "")) if j.get("minSalary") or j.get("maxSalary") else "",
            job_type=clean(j.get("employmentType")),
            seniority=", ".join(j.get("seniority") or []),
            tags=[c.replace("-", " ") for c in (j.get("categories") or [])][:4],
            min_years=years_required(_text(j.get("description", ""))),
        ))
    return out


def parse_jobicy(data: dict) -> list[Job]:
    out = []
    for j in data.get("jobs", []):
        out.append(Job(
            source="jobicy", source_id=str(j["id"]), title=clean(j.get("jobTitle")),
            company=clean(j.get("companyName")), url=j.get("url", ""),
            location=clean(j.get("jobGeo")), posted_at=parse_date(j.get("pubDate")),
            job_type=", ".join(j.get("jobType") or []), seniority=clean(j.get("jobLevel")),
            salary=fmt_money(j.get("annualSalaryMin"), j.get("annualSalaryMax"),
                             j.get("salaryCurrency") or "USD", "annual"),
            tags=(j.get("jobIndustry") or [])[:3],
            min_years=years_required(_text(j.get("jobDescription", ""))),
        ))
    return out


def parse_workingnomads(data: list) -> list[Job]:
    out = []
    for j in data:
        url = j.get("url", "")
        out.append(Job(
            source="workingnomads", source_id=url.rstrip("/").split("/")[-1] or url,
            title=clean(j.get("title")), company=clean(j.get("company_name")), url=url,
            location=clean(j.get("location")), posted_at=parse_date(j.get("pub_date")),
            tags=[t for t in (j.get("tags") or "").split(",") if t][:6],
            min_years=years_required(_text(j.get("description", ""))),
        ))
    return out


def parse_wwr(xml: str) -> list[Job]:
    soup = BeautifulSoup(xml, "xml")
    out = []
    for it in soup.find_all("item"):
        raw = clean(it.title.get_text() if it.title else "")
        company, _, title = raw.partition(": ")
        if not title:
            company, title = "", raw
        link = clean(it.link.get_text() if it.link else "")
        region = it.find("region")
        desc = it.find("description")
        out.append(Job(
            source="weworkremotely", source_id=link.rstrip("/").split("/")[-1], title=title,
            company=company, url=link, location=clean(region.get_text()) if region else "",
            posted_at=parse_date(it.pubDate.get_text() if it.pubDate else None),
            min_years=years_required(_text(desc.get_text())) if desc else None,
        ))
    return out


def parse_arbeitnow(data: dict) -> list[Job]:
    out = []
    for j in data.get("data", []):
        out.append(Job(
            source="arbeitnow", source_id=j["slug"], title=clean(j.get("title")),
            company=clean(j.get("company_name")), url=j.get("url", ""),
            location=clean(j.get("location")), posted_at=parse_date(j.get("created_at")),
            remote=bool(j.get("remote")), work_mode="remote" if j.get("remote") else "onsite",
            job_type=", ".join(j.get("job_types") or []), tags=(j.get("tags") or [])[:4],
        ))
    return out


def parse_greenhouse(data: dict, slug: str) -> list[Job]:
    out = []
    for j in data.get("jobs", []):
        loc = clean((j.get("location") or {}).get("name"))
        out.append(Job(
            source="greenhouse", source_id=f"{slug}-{j['id']}", title=clean(j.get("title")),
            company=clean(j.get("company_name")) or slug.title(), url=j.get("absolute_url", ""),
            location=loc, posted_at=parse_date(j.get("first_published") or j.get("updated_at")),
            work_mode=remote_mode(loc), remote=remote_mode(loc) == "remote",
        ))
    return out


def parse_lever(data: list, slug: str) -> list[Job]:
    out = []
    for j in data:
        cats = j.get("categories") or {}
        loc = clean(cats.get("location") or ", ".join(cats.get("allLocations") or []))
        wt = (j.get("workplaceType") or "").lower()
        mode = {"remote": "remote", "hybrid": "hybrid", "on-site": "onsite", "onsite": "onsite"}.get(
            wt, remote_mode(loc))
        out.append(Job(
            source="lever", source_id=f"{slug}-{j['id']}", title=clean(j.get("text")),
            company=slug.title(), url=j.get("hostedUrl") or j.get("applyUrl", ""), location=loc,
            posted_at=parse_date(j.get("createdAt")), work_mode=mode, remote=mode == "remote",
            job_type=clean(cats.get("commitment")),
            min_years=years_required(j.get("descriptionPlain", "")),
        ))
    return out


def parse_ashby(data: dict, slug: str) -> list[Job]:
    out = []
    for j in data.get("jobs", []):
        if j.get("isListed") is False:
            continue
        locs = [j.get("location", "")] + [l.get("location", "") for l in j.get("secondaryLocations") or []]
        remote_locs = [l for l in locs if "remote" in l.lower()]
        wt = (j.get("workplaceType") or "").lower()
        mode = "remote" if j.get("isRemote") or wt == "remote" else ("hybrid" if wt == "hybrid" else "onsite")
        comp = (j.get("compensation") or {}).get("compensationTierSummary", "")
        out.append(Job(
            source="ashby", source_id=f"{slug}-{j['id']}", title=clean(j.get("title")),
            company=slug.title(), url=j.get("jobUrl") or j.get("applyUrl", ""),
            location=", ".join(remote_locs or locs[:1]), posted_at=parse_date(j.get("publishedAt")),
            work_mode=mode, remote=mode == "remote", job_type=clean(j.get("employmentType")),
            salary=clean(comp), min_years=years_required(j.get("descriptionPlain", "")),
        ))
    return out


# ---------- fetchers ----------

async def _get(client: httpx.AsyncClient, url: str, as_json: bool = True):
    r = await client.get(url, headers=HEADERS)
    r.raise_for_status()
    return r.json() if as_json else r.text


async def fetch_board(name: str, client: httpx.AsyncClient, s: Settings) -> list[Job]:
    if name == "remotive":
        return parse_remotive(await _get(client, "https://remotive.com/api/remote-jobs?category=software-dev&limit=150"))
    if name == "remoteok":
        return parse_remoteok(await _get(client, "https://remoteok.com/api?tag=dev"))
    if name == "himalayas":
        out, cursor = [], ""
        for _ in range(5):                       # API caps pages at 20 jobs
            data = await _get(client, "https://himalayas.app/jobs/api?limit=20"
                              + (f"&cursor={cursor}" if cursor else ""))
            out += parse_himalayas(data)
            cursor = data.get("nextCursor")
            if not cursor:
                break
        return out
    if name == "jobicy":
        return parse_jobicy(await _get(client, "https://jobicy.com/api/v2/remote-jobs?count=100&industry=engineering"))
    if name == "workingnomads":
        return parse_workingnomads(await _get(client, "https://www.workingnomads.com/api/exposed_jobs/"))
    if name == "weworkremotely":
        out = []
        for cat in ("remote-programming-jobs", "remote-full-stack-programming-jobs",
                    "remote-back-end-programming-jobs", "remote-front-end-programming-jobs"):
            out += parse_wwr(await _get(client, f"https://weworkremotely.com/categories/{cat}.rss", False))
        return out
    if name == "arbeitnow":
        return parse_arbeitnow(await _get(client, "https://www.arbeitnow.com/api/job-board-api"))
    if name in ("greenhouse", "lever", "ashby"):
        companies = getattr(s, f"{name}_companies")
        out = []
        for slug in companies:
            url = {
                "greenhouse": f"https://boards-api.greenhouse.io/v1/boards/{slug}/jobs",
                "lever": f"https://api.lever.co/v0/postings/{slug}?mode=json",
                "ashby": f"https://api.ashbyhq.com/posting-api/job-board/{slug}?includeCompensation=true",
            }[name]
            try:
                data = await _get(client, url)
            except (httpx.HTTPError, ValueError) as e:
                log.info("%s/%s failed: %s", name, slug, e)
                continue
            out += {"greenhouse": parse_greenhouse, "lever": parse_lever, "ashby": parse_ashby}[name](data, slug)
        return out
    raise ValueError(f"unknown source {name}")


BOARD_SOURCES = ("remotive", "remoteok", "himalayas", "jobicy", "workingnomads",
                 "weworkremotely", "arbeitnow", "greenhouse", "lever", "ashby")
