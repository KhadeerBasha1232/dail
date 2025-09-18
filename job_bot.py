import requests
from bs4 import BeautifulSoup
from telegram import Bot
from telegram.constants import ParseMode
import urllib.parse
import asyncio
from collections import deque

TOKEN = "7659495124:AAEdFN1vItHUWzY0Im2PP6LyuPwjO7jRp0o"
CHAT_ID = "-1002649556090"
bot = Bot(token=TOKEN)

POSITIONS = [
    "Python-Developer", "Backend-Engineer", "Full-Stack-Developer", "Software-Engineer", "Frontend-Engineer",
    "React-Developer", "Java-Developer", "Django-Developer", "Flask-Developer", 
    "FastAPI-Developer", "Spring-Boot-Developer", "MERN-Stack-Developer", "Hibernate-Developer",
    "Blockchain-Developer", "Data-Scientist", "Machine-Learning-Engineer", "AI-Engineer", "Software-Developer-Intern"
]

LOCATIONS = ["India", "India(Remote)", "Hyderabad", "Bangalore", "Chennai", "Pune", "Delhi", "Mumbai", "Gurgaon", "Noida"]
EXPERIENCE_LEVELS = ["Entry-Level", "Internship"]

SKIP_WORDS = [
    "senior", "sr.", "sr ", "s.r", "lead", "staff", "manager", "director",
    "head", "principal", "10 years", "5 years", "7 years", "8 years", "6 years",
    "10 yrs", "7 yrs", "5 yrs", "6 yrs", "8 yrs", "experienced", "require", "required"
]

sent_ids = deque(maxlen=5000)

def build_url(keyword, location):
    base_url = "https://www.linkedin.com/jobs/search"
    params = {
        "keywords": keyword,
        "location": location,
        "f_TPR": "r1800",  # last 30 mins
        "f_WT": "2",       # remote
        "f_JT": "F",       # full-time
        "position": "1",
        "pageNum": "0"
    }
    return f"{base_url}?{urllib.parse.urlencode(params)}"

def should_skip(title):
    if any(word in title.lower() for word in SKIP_WORDS):
        print(f"[SKIP] Title contains skip word: {title}")
        return True
    return False

def extract_jobs(html):
    soup = BeautifulSoup(html, "html.parser")
    job_cards = soup.select(".base-search-card")
    print(f"Found {len(job_cards)} job cards in page.")
    jobs = []

    for job in job_cards:
        title = job.select_one(".base-search-card__title")
        company = job.select_one(".base-search-card__subtitle")
        location = job.select_one(".job-search-card__location")
        posted = job.select_one("time")
        job_url = job.select_one("a")["href"]

        if not title or not job_url:
            print("Skipping: Missing title or URL")
            continue

        if should_skip(title.text):
            continue

        job_id = job_url.split("view/")[-1].split("?")[0]
        if job_id in sent_ids:
            print(f"[DUPLICATE] Already sent job ID: {job_id}")
            continue

        sent_ids.append(job_id)

        job_data = {
            "title": title.get_text(strip=True),
            "company": company.get_text(strip=True) if company else "N/A",
            "location": location.get_text(strip=True) if location else "N/A",
            "posted_time": posted.get_text(strip=True) if posted else "Just now",
            "job_url": job_url
        }

        print(f"[NEW] Job: {job_data['title']} at {job_data['company']}")
        jobs.append(job_data)

    return jobs

async def send_job(job, keyword, location, experience):
    message = (
        f"📢 *New Job Opportunity!*\n\n"
        f"🔹 *Position:* {job['title']}\n"
        f"🔹 *Company:* {job['company']}\n"
        f"🔹 *Location:* {job['location']}\n"
        f"🔹 *Posted:* {job['posted_time']}\n\n"
        f"🌐 *Apply Here:* [Click to Apply]({job['job_url']})\n\n"
        f"🔍 *Search Criteria:* `{keyword}` | `{location}` | `{experience}`"
    )
    print(f"[SEND] Sending job: {job['title']}")
    await bot.send_message(chat_id=CHAT_ID, text=message, parse_mode=ParseMode.MARKDOWN)

async def main():
    while True:  # <-- run forever
        for keyword in POSITIONS:
            for location in LOCATIONS:
                for experience in EXPERIENCE_LEVELS:
                    try:
                        print(f"\n[INFO] Fetching jobs for: {keyword} | {location} | {experience}")
                        url = build_url(keyword, location)
                        print(f"[URL] {url}")
                        headers = {
                            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)"
                        }
                        res = requests.get(url, headers=headers)
                        jobs = extract_jobs(res.text)

                        for job in jobs:
                            await send_job(job, keyword, location, experience)
                            await asyncio.sleep(1.2)  # avoid rate limits

                    except Exception as e:
                        print(f"[ERROR] Fetching {keyword} - {location}: {e}")
                    await asyncio.sleep(1)

        print("[INFO] Sleeping 30 minutes before next cycle...")
        await asyncio.sleep(1800)  # wait 30 minutes before checking again


if __name__ == "__main__":
    print("✅ Job Scraper Started...")
    asyncio.run(main())
