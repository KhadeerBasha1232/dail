from datetime import timedelta

from jobbot.config import Settings
from jobbot.filters import region_ok, reject_reason, title_excluded
from jobbot.formatter import freshness, job_buttons, job_card
from jobbot.models import Job, utcnow


def job(**kw):
    base = dict(source="remotive", source_id="1", title="Python Developer", company="Acme",
                url="https://x.test/job?a=1&b=2", location="Worldwide",
                posted_at=utcnow() - timedelta(minutes=5))
    base.update(kw)
    return Job(**base)


def test_whole_word_excludes():
    s = Settings()
    assert title_excluded("Senior Python Developer", s) == "senior"
    assert title_excluded("Sr. Backend Engineer", s) in ("sr", "sr.")
    assert title_excluded("Python Developers wanted", s) is None      # 'sr' isn't inside a word
    assert title_excluded("Leadership Coach", s) is None               # 'lead' != 'leadership'


def test_region():
    s = Settings()
    for ok in ["", "Remote", "Worldwide", "Anywhere in the World", "India", "APAC", "Remote - Asia"]:
        assert region_ok(ok, s), ok
    for bad in ["United States", "USA only", "Europe", "Remote (Canada)"]:
        assert not region_ok(bad, s), bad
    s.region_filter = False
    assert region_ok("United States", s)


def test_reject_reasons():
    s, now = Settings(), utcnow()
    assert reject_reason(job(), s, now) is None
    assert "too old" in reject_reason(job(posted_at=now - timedelta(days=3)), s, now)
    assert reject_reason(job(posted_at=None), s, now) == "no date"
    assert "excluded" in reject_reason(job(title="Lead Python Developer"), s, now)
    assert reject_reason(job(title="Account Executive"), s, now) == "title not relevant"
    assert "region" in reject_reason(job(location="United States"), s, now)
    assert reject_reason(job(title="Python Developer (US Based)", location=""), s, now) == "region-locked title"
    assert reject_reason(job(min_years=5), s, now) == "asks 5+ years"
    assert reject_reason(job(title="Python Developer 6+ years"), s, now) == "asks 6+ years"
    assert reject_reason(job(work_mode="onsite"), s, now) == "work mode onsite"
    s.muted_companies = ["acme"]
    assert reject_reason(job(), s, now) == "muted company"


def test_linkedin_15_minute_window():
    s, now = Settings(), utcnow()
    li = lambda m: job(source="linkedin", title="Backend Developer", posted_at=now - timedelta(minutes=m))
    assert reject_reason(li(14), s, now) is None
    assert "too old" in reject_reason(li(16), s, now)
    s.linkedin_max_age_min = 30
    assert reject_reason(li(16), s, now) is None


def test_work_mode_settings():
    s, now = Settings(), utcnow()
    h = job(work_mode="hybrid")
    assert reject_reason(h, s, now)
    s.work_mode = "remote_hybrid"
    assert reject_reason(h, s, now) is None
    s.work_mode = "any"
    assert reject_reason(job(work_mode="onsite"), s, now) is None


def test_freshness_badges():
    assert freshness(2)[0] == "🔥" and freshness(12)[0] == "⚡" and freshness(45)[0] == "🟢"
    assert freshness(200)[0] == "🕐" and freshness(5000)[0] == "📅" and freshness(None)[0] == "🆕"


def test_card_escapes_and_shows_details():
    j = job(title="C++ <Dev> & Co", company="A&B", salary="$50k", tags=["python", "Node.js"],
            applicants="Be among the first 25 applicants", job_type="Full-time", min_years=0,
            posted_at=utcnow() - timedelta(minutes=2))
    text = job_card(j)
    assert "C++ &lt;Dev&gt; &amp; Co" in text and "A&amp;B" in text
    assert "🔥 <b>JUST POSTED</b>" in text and "💰 $50k" in text
    assert "#python #node_js" in text
    assert "Be among the first 25 applicants" in text and "Freshers welcome" in text
    compact = job_card(j, style="compact")
    assert compact.count("\n") == 1 and 'href="https://x.test/job?a=1&amp;b=2"' in compact


def test_buttons_fit_telegram_limits():
    j = job()
    rows = job_buttons(j, 123456789)
    assert rows[0][0]["url"] == j.url
    for row in rows[1:]:
        for b in row:
            assert len(b["callback_data"].encode()) <= 64
    counted = job_buttons(j, 1, {"saved": 3, "applied": 1})[1]
    assert counted[0]["text"] == "⭐ Save · 3" and counted[1]["text"] == "✅ Applied · 1"
    assert job_buttons(j, 1)[1][0]["text"] == "⭐ Save"


def test_linkedin_title_and_level_checks():
    from jobbot.filters import seniority_key
    s, now = Settings(), utcnow()
    li = lambda **k: job(source="linkedin", **k)
    assert reject_reason(li(title="Technical Business Analyst"), s, now) == "title not relevant"
    assert reject_reason(li(title="Software Engineer, Backend"), s, now) is None
    assert reject_reason(li(title="Software Engineer", seniority="Mid-Senior level"), s, now) \
        == "level Mid-Senior level"
    assert reject_reason(li(title="Software Engineer", seniority="Entry level"), s, now) is None
    s.linkedin_title_match = False
    assert reject_reason(li(title="Technical Business Analyst"), s, now) is None
    assert seniority_key("Internship") == "internship" and seniority_key("Not Applicable") is None


def test_meta_not_repeated():
    text = job_card(job(job_type="Internship", seniority="Internship"))
    assert "📋 Internship\n" in text
