from datetime import timedelta, timezone

from jobbot.config import Settings
from jobbot.models import utcnow
from jobbot.sources import boards
from jobbot.sources.common import fmt_money, parse_date, relative_minutes, years_required
from jobbot.sources.linkedin import (best_keyword, build_params, keyword_groups, parse_cards,
                                     parse_detail)

CARD = """<li><div class="base-card job-search-card" data-entity-urn="urn:li:jobPosting:{id}">
<a class="base-card__full-link" href="https://in.linkedin.com/jobs/view/x-{id}?position=1&amp;refId=abc"></a>
<h3 class="base-search-card__title"> {title} </h3>
<h4 class="base-search-card__subtitle"><a>{company}</a></h4>
<span class="job-search-card__location">{loc}</span>
<time class="job-search-card__listdate--new" datetime="2026-10-29">{ago}</time>
</div></li>"""

DETAIL = """<span class="num-applicants__caption">Be among the first 25 applicants</span>
<ul><li class="description__job-criteria-item"><h3 class="description__job-criteria-subheader">Seniority level</h3>
<span class="description__job-criteria-text">Entry level</span></li>
<li class="description__job-criteria-item"><h3 class="description__job-criteria-subheader">Employment type</h3>
<span class="description__job-criteria-text">Full-time</span></li></ul>
<div class="show-more-less-html__markup">We need 1-3 years of Python. Company founded 12 years ago.</div>"""


def test_parse_date_formats():
    assert parse_date("2026-10-29T08:10:18+00:00").hour == 8
    assert parse_date("2026-10-27T12:56:13").tzinfo == timezone.utc       # naive -> UTC
    assert parse_date(1793269812).year == 2026                            # unix seconds
    assert parse_date(1793269812000).year == 2026                         # unix ms
    assert parse_date("Sat, 10 Oct 2026 07:31:08 +0000").day == 10        # RSS
    assert parse_date("garbage") is None and parse_date(None) is None


def test_relative_minutes():
    assert relative_minutes("2 minutes ago") == 2
    assert relative_minutes("1 hour ago") == 60
    assert relative_minutes("Just now") == 0
    assert relative_minutes("3 days ago") == 4320
    assert relative_minutes("") is None


def test_years_required():
    assert years_required("needs 5+ years of experience") == 5
    assert years_required("Software Engineer (GO/Java | 8-12 years)") == 8
    assert years_required("1-3 years Python, 4+ yrs total") == 1          # smallest wins
    assert years_required("great team, no requirement") is None


def test_fmt_money():
    assert fmt_money(80000, 120000, "USD", "annual") == "$80k–$120k/yr"
    assert fmt_money(0, 0) == ""
    assert fmt_money(50000, None, "EUR") == "€50k"


def test_linkedin_cards():
    html = "<!DOCTYPE html>" + CARD.format(id=111, title="Python Developer", company="Acme",
                                            loc="Pune, India", ago="4 minutes ago") \
        + CARD.format(id=222, title="Java &amp; Spring Dev", company="Beta", loc="Remote", ago="1 hour ago")
    jobs = parse_cards(html, Settings())
    assert [j.source_id for j in jobs] == ["111", "222"]
    a, b = jobs
    assert a.url == "https://in.linkedin.com/jobs/view/x-111"            # tracking params dropped
    assert a.company == "Acme" and a.location == "Pune, India" and a.work_mode == "remote"
    assert 3.5 < a.age_minutes() < 4.5
    assert b.title == "Java & Spring Dev"


def test_linkedin_detail():
    j = parse_cards("<!DOCTYPE html>" + CARD.format(id=1, title="T", company="C", loc="India",
                                                    ago="1 minute ago"), Settings())[0]
    parse_detail(DETAIL, j)
    assert j.applicants == "Be among the first 25 applicants"
    assert j.seniority == "Entry level" and j.job_type == "Full-time" and j.min_years == 1


def test_linkedin_params():
    s = Settings()
    p = build_params('"Python Developer" OR "Go Dev"', "India", s, start=10)
    assert p["f_TPR"] == "r900"            # 15 minutes
    assert p["f_WT"] == "2"                # remote
    assert p["f_E"] == "1,2" and p["f_JT"] == "F,I" and p["start"] == "10" and p["sortBy"] == "DD"
    s.work_mode = "any"
    assert "f_WT" not in build_params("x", "India", s)
    s.work_mode = "remote_hybrid"
    assert build_params("x", "India", s)["f_WT"] == "2,3"


def test_keyword_groups():
    groups = keyword_groups([f"k{i}" for i in range(13)], 6)
    assert [len(g) for g in groups] == [6, 6, 1]
    g = ["Python Developer", "Django Developer", "Full Stack Developer"]
    assert best_keyword("Senior Django Engineer", g) == "Django Developer"
    assert best_keyword("Rust wizard", g) == ""


def iso(minutes_ago):
    return (utcnow() - timedelta(minutes=minutes_ago)).isoformat()


def test_board_parsers():
    r = boards.parse_remotive({"jobs": [{"id": 1, "title": "Backend Dev", "company_name": "R",
                                         "url": "u", "candidate_required_location": "Worldwide",
                                         "publication_date": iso(5), "salary": "$50k", "tags": ["python"],
                                         "job_type": "full_time", "description": "<p>2+ years</p>"}]})[0]
    assert (r.source, r.location, r.job_type, r.min_years) == ("remotive", "Worldwide", "Full Time", 2)

    ok = boards.parse_remoteok([{"legal": "x"}, {"id": "9", "position": "Dev", "company": "O",
                                                 "epoch": 1793001612, "salary_min": 60000,
                                                 "salary_max": 90000, "apply_url": "a"}])
    assert len(ok) == 1 and ok[0].salary == "$60k–$90k/yr"

    h = boards.parse_himalayas({"jobs": [{"guid": "g", "title": "Dev", "companyName": "H",
                                          "applicationLink": "app", "locationRestrictions": [],
                                          "pubDate": 1793269812, "seniority": ["Entry-level"]}]})[0]
    assert h.location == "Worldwide" and h.url == "app" and h.seniority == "Entry-level"

    w = boards.parse_wwr("""<rss><channel><item><title>Typeform: Full Stack Developer</title>
        <region>Anywhere in the World</region><pubDate>Sat, 10 Oct 2026 07:31:08 +0000</pubDate>
        <link>https://weworkremotely.com/remote-jobs/typeform-fsd</link></item></channel></rss>""")[0]
    assert (w.company, w.title, w.source_id) == ("Typeform", "Full Stack Developer", "typeform-fsd")

    a = boards.parse_ashby({"jobs": [{"id": "x", "title": "Eng", "location": "NYC", "isRemote": True,
                                      "secondaryLocations": [{"location": "Remote (India)"}],
                                      "publishedAt": iso(1), "jobUrl": "j"}]}, "acme")[0]
    assert a.work_mode == "remote" and a.location == "Remote (India)" and a.company == "Acme"

    lv = boards.parse_lever([{"id": "1", "text": "SDE", "hostedUrl": "h", "createdAt": 1793269812000,
                              "workplaceType": "remote", "categories": {"location": "Bengaluru"}}], "cred")[0]
    assert lv.work_mode == "remote" and lv.posted_at.year == 2026

    gh = boards.parse_greenhouse({"jobs": [{"id": 5, "title": "SWE", "absolute_url": "x",
                                            "location": {"name": "Remote, India"},
                                            "first_published": iso(3)}]}, "gitlab")[0]
    assert gh.work_mode == "remote" and gh.company == "Gitlab"

    an = boards.parse_arbeitnow({"data": [{"slug": "s", "title": "Dev", "company_name": "A",
                                           "remote": False, "created_at": 1793267716}]})[0]
    assert an.work_mode == "onsite"


def test_best_keyword_prefers_specific_words():
    g = ["Data Scientist", "Machine Learning Engineer", "AI Engineer", "Software Developer Intern"]
    assert best_keyword("Software Engineer, Backend", g) == ""
    assert best_keyword("Machine Learning Engineer II", g) == "Machine Learning Engineer"
    assert best_keyword("AI Engineer (LLM)", g) == "AI Engineer"
    assert best_keyword("Software Engineer, Backend", ["Software Engineer", "Backend Engineer"])         == "Software Engineer"
