import requests
import asyncio
from bs4 import BeautifulSoup
from telegram import Bot
from collections import deque

BOT_TOKEN = "7659495124:AAEdFN1vItHUWzY0Im2PP6LyuPwjO7jRp0o"
CHAT_ID = "-1002649556090"

POSITIONS = [
    "Python Developer", "Backend Engineer", "Full Stack Developer", "Software Engineer", "Frontend Engineer",
    "React Developer", "Java Developer", "Django Developer", "Flask Developer",
    "FastAPI Developer", "Spring Boot Developer", "MERN Stack Developer", "Hibernate Developer",
    "Blockchain Developer", "Data Scientist", "Machine Learning Engineer", "AI Engineer", "Software Developer Intern"
]

LOCATIONS = ["India", "Hyderabad", "Bangalore", "Chennai", "Pune", "Delhi", "Mumbai", "Gurgaon", "Noida"]
EXPERIENCE_LEVELS = {"Entry-Level": 2, "Internship": 1}

bot = Bot(token=BOT_TOKEN)

def extract_job_id_from_urn(job_li):
    job_div = job_li.find('div', class_='base-card')
    if job_div:
        data_urn = job_div.get("data-entity-urn", "")
        if "jobPosting:" in data_urn:
            return data_urn.split("jobPosting:")[-1]
    return None

def parse_jobs(html_content):
    soup = BeautifulSoup(html_content, 'html.parser')
    li_cards = soup.find_all('li')
    jobs = []
    for job in li_cards:
        job_id = extract_job_id_from_urn(job)
        if not job_id or job_id in sent_jobs:
            continue
        job_link_tag = job.find('a', class_='base-card__full-link')
        job_url = job_link_tag['href'] if job_link_tag else "N/A"
        job_title_tag = job.find('h3', class_='base-search-card__title')
        job_title = job_title_tag.get_text(strip=True) if job_title_tag else "N/A"
        if any(x in job_title.lower() for x in ["sr", "senior", "lead", "years", "exp", "req", "manager"]):
            continue
        company_tag = job.find('h4', class_='base-search-card__subtitle')
        company_name = company_tag.get_text(strip=True) if company_tag else "N/A"
        location_tag = job.find('span', class_='job-search-card__location')
        location = location_tag.get_text(strip=True) if location_tag else "N/A"
        time_tag = job.find('time')
        posted_time = time_tag.get_text(strip=True) if time_tag else "N/A"
        jobs.append({
            "job_id": job_id,
            "title": job_title,
            "company": company_name,
            "location": location,
            "job_url": job_url,
            "posted_time": posted_time
        })
    return jobs, len(li_cards)

async def send_jobs_to_telegram(jobs, keyword, location, experience):
    new_jobs = [job for job in jobs if job["job_id"] not in sent_jobs]
    print(f" -> New jobs found for ({keyword} | {location} | {experience}): {len(new_jobs)}")
    for job in new_jobs[:5]:
        msg = (
            f"📢 *New Job Opportunity!*\n\n"
            f"🔹 *Position:* {job['title']}\n"
            f"🔹 *Company:* {job['company']}\n"
            f"🔹 *Location:* {job['location']}\n"
            f"🔹 *Posted:* {job['posted_time']}\n\n"
            f"🌐 [Apply Here]({job['job_url']})\n\n"
            f"🔍 `{keyword}` | `{location}` | `{experience}`"
        )
        try:
            await bot.send_message(CHAT_ID, msg, parse_mode="Markdown", disable_web_page_preview=True)
            sent_jobs.append(job["job_id"])
            print(f"   -> Sent: {job['job_id']} | {job['title']}")
        except Exception as e:
            print(f"   -> Failed to send {job['job_id']}: {e}")
        await asyncio.sleep(2)

async def fetch_linkedin_jobs_one_combination(keyword, location, experience):
    jobs = []
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36",
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8",
        "Accept-Language": "en-US,en;q=0.5",
        "Accept-Encoding": "gzip, deflate, br",
        "Connection": "keep-alive",
        "Upgrade-Insecure-Requests": "1",
        "Sec-Fetch-Dest": "document",
        "Sec-Fetch-Mode": "navigate",
        "Sec-Fetch-Site": "none",
        "Sec-Fetch-User": "?1",
        "Cache-Control": "max-age=0",
        "Referer": "https://www.linkedin.com/jobs/search/"
    }
    f_tpr = "r10800"  # past 3 hours
    f_e = EXPERIENCE_LEVELS[experience]
    f_wt = "2%2C3"  # encoded 2,3
    for start in range(0, 51, 25):
        params_set = {
            "keywords": keyword,
            "location": location,
            "f_TPR": f_tpr,
            "f_E": str(f_e),
            "sortBy": "DD",
            "start": str(start),
            "f_WT": "2,3",
            "f_JT": "F"
        }
        url = (
            "https://www.linkedin.com/jobs-guest/jobs/api/seeMoreJobPostings/search?"
            f"keywords={keyword.replace(' ', '%20')}&location={location.replace(' ', '%20')}"
            f"&f_TPR={f_tpr}&f_E={f_e}&sortBy=DD&start={start}&f_WT={f_wt}&f_JT=F"
        )
        print("Trying combination ->", params_set)
        print("Request URL ->", url)
        try:
            resp = requests.get(url, headers=headers, timeout=15)
        except Exception as e:
            print("Request error:", e)
            await asyncio.sleep(2)
            continue
        print("Status code:", resp.status_code, "| Response length:", len(resp.text))
        if resp.status_code != 200:
            print("Non-200 response; stopping this combination.")
            break
        parsed_jobs, li_count = parse_jobs(resp.text)
        print("Found <li> cards:", li_count, "| Parsed jobs (after filters):", len(parsed_jobs))
        if li_count == 0:
            if "<!DOCTYPE html>" in resp.text and len(resp.text.strip()) < 1000:
                print(" -> Response looks very small/empty (possible blocking or zero matches).")
            else:
                print(" -> No job <li> elements found in response.")
        jobs.extend(parsed_jobs)
        await asyncio.sleep(2)
    return jobs

async def main():
    global sent_jobs
    sent_jobs = deque(maxlen=300)
    while True:
        for keyword in POSITIONS:
            for location in LOCATIONS:
                for experience in EXPERIENCE_LEVELS:
                    print("\n===== NEW QUERY =====")
                    print(f"Keyword: {keyword} | Location: {location} | Experience: {experience} | TimeFilter: past 3 hours (r10800)")
                    jobs = await fetch_linkedin_jobs_one_combination(keyword, location, experience)
                    print(f"Total parsed jobs for combination: {len(jobs)}")
                    await send_jobs_to_telegram(jobs, keyword, location, experience)
                    await asyncio.sleep(5)
        print("Cycle complete. Sleeping 10 minutes.")
        await asyncio.sleep(600)

if __name__ == "__main__":
    asyncio.run(main())
