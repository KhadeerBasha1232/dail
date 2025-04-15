import requests
import asyncio
import logging
from bs4 import BeautifulSoup
from telegram import Bot
from supabase import create_client, Client

# 🔹 Telegram Bot Config
BOT_TOKEN = "7659495124:AAEdFN1vItHUWzY0Im2PP6LyuPwjO7jRp0o"
CHAT_ID = "-1002649556090"

# 🔹 Supabase Config
SUPABASE_URL = "https://zxuntuqugjptwvqgpeti.supabase.co"
SUPABASE_KEY = "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJpc3MiOiJzdXBhYmFzZSIsInJlZiI6Inp4dW50dXF1Z2pwdHd2cWdwZXRpIiwicm9sZSI6InNlcnZpY2Vfcm9sZSIsImlhdCI6MTc0MDY3MzkyOCwiZXhwIjoyMDU2MjQ5OTI4fQ.vcFceQqSLz34U_x42cEaAi8ZLYFTmaV8Vh7-xjSlle8"

# Job Titles & Locations to Search
POSITIONS = [
    "Python-Developer", "Backend-Engineer", "Full-Stack-Developer", "Software-Engineer", "Frontend-Engineer",
    "React-Developer", "Java-Developer", "Django-Developer", "Flask-Developer", 
    "FastAPI-Developer", "Spring-Boot-Developer", "MERN-Stack-Developer", "Hibernate-Developer",
    "Blockchain-Developer", "Data-Scientist", "Machine-Learning-Engineer", "AI-Engineer", "Software-Developer-Intern"
]

LOCATIONS = ["India", "India(Remote)", "Hyderabad", "Bangalore", "Chennai", "Pune", "Delhi", "Mumbai", "Gurgaon", "Noida"]
EXPERIENCE_LEVELS = ["Entry-Level", "Internship"]

# Initialize Supabase Client
supabase: Client = create_client(SUPABASE_URL, SUPABASE_KEY)

# Initialize Telegram Bot
bot = Bot(token=BOT_TOKEN)

async def fetch_sent_jobs():
    """Fetch sent job IDs from Supabase."""
    response = supabase.table("sent_jobs").select("job_id").execute()
    if not response.data:  # Check if data is None or empty
        return set()
    return {row["job_id"] for row in response.data}

async def save_sent_job(job_id):
    """Save a sent job ID to Supabase."""
    response = supabase.table("sent_jobs").insert({"job_id": job_id}).execute()

def parse_jobs(html_content):
    """Extract job details from LinkedIn HTML response."""
    soup = BeautifulSoup(html_content, 'html.parser')
    job_list = []
    job_cards = soup.find_all('li')

    for job in job_cards:
        job_id = extract_job_id_from_urn(job)
        if not job_id or job_id in sent_jobs:
            continue

        job_link_tag = job.find('a', class_='base-card__full-link')
        job_url = job_link_tag['href'] if job_link_tag else "N/A"

        job_title_tag = job.find('h3', class_='base-search-card__title')
        job_title = job_title_tag.get_text(strip=True) if job_title_tag else "N/A"

        # Filter out titles containing "Sr." or "years"
        if "Sr." in job_title or "years" in job_title or "yrs" in job_title or "exp" in job_title or "req" in job_title or "Senior" in job_title or "senior" in job_title or "sr" in job_title:
            continue

        company_tag = job.find('h4', class_='base-search-card__subtitle')
        company_name = company_tag.get_text(strip=True) if company_tag else "N/A"

        location_tag = job.find('span', class_='job-search-card__location')
        location = location_tag.get_text(strip=True) if location_tag else "N/A"

        time_tag = job.find('time', class_='job-search-card__listdate--new')
        posted_time = time_tag.get_text(strip=True) if time_tag else "N/A"

        job_list.append({
            "job_id": job_id,
            "title": job_title,
            "company": company_name,
            "location": location,
            "job_url": job_url,
            "posted_time": posted_time
        })

    return job_list

def extract_job_id_from_urn(job_li):
    """Extracts job ID from LinkedIn's job URN."""
    job_div = job_li.find('div', class_='base-card')
    if job_div:
        data_urn = job_div.get("data-entity-urn", "")
        if "jobPosting:" in data_urn:
            return data_urn.split("jobPosting:")[-1]
    return None

async def send_jobs_to_telegram(jobs, keyword, location, experience):
    """Send only new job posts to Telegram asynchronously."""
    global sent_jobs

    new_jobs = [job for job in jobs if job["job_id"] not in sent_jobs]

    if not new_jobs:
        return  # No new jobs to send

    for job in new_jobs[:5]:  # Send first 5 new jobs to avoid spam
        message = (
            f"📢 *New Job Opportunity!*\n\n"
            f"🔹 *Position:* {job['title']}\n"
            f"🔹 *Company:* {job['company']}\n"
            f"🔹 *Location:* {job['location']}\n"
            f"🔹 *Posted:* {job['posted_time']}\n\n"
            f"🌐 *Apply Here:* [Click to Apply]({job['job_url']})\n\n"
            f"🔍 *Search Criteria:* `{keyword}` | `{location}` | `{experience}`"
        )

        try:
            await bot.send_message(CHAT_ID, message, parse_mode="Markdown", disable_web_page_preview=True)
            await save_sent_job(job["job_id"])
            sent_jobs.add(job["job_id"])
        except Exception as e:
        await asyncio.sleep(2)  # Use asyncio.sleep() instead of time.sleep()

async def fetch_linkedin_jobs_one_combination(keyword, location, experience):
    """Fetch jobs for a single combination of keyword, location, and experience level."""
    jobs = []
    headers = {"User-Agent": "Mozilla/5.0"}

    for start in range(0, 51, 25):  # Fetch up to 50 jobs per query
        url = (f"https://www.linkedin.com/jobs-guest/jobs/api/seeMoreJobPostings/search?"
       f"keywords={keyword}&location={location}&f_TPR=r3600&f_E={experience}"
       f"&sortBy=DD&start={start}&f_WT=2,3&f_JT=F")
        response = requests.get(url, headers=headers)
        if response.status_code == 200:
            jobs.extend(parse_jobs(response.text))
        else:
            break  # Stop if LinkedIn blocks further requests

        # Add a 2-second delay between API calls
        await asyncio.sleep(2)

    return jobs

async def main():
    global sent_jobs
    sent_jobs = await fetch_sent_jobs()  # Load sent jobs from Supabase

    while True:
        for keyword in POSITIONS:
            for location in LOCATIONS:
                for experience in EXPERIENCE_LEVELS:
                    jobs = await fetch_linkedin_jobs_one_combination(keyword, location, experience)
                    await send_jobs_to_telegram(jobs, keyword, location, experience)  # Pass combination details
                    await asyncio.sleep(5)  # Sleep for 5 seconds between combinations
        await asyncio.sleep(300)  # Sleep for 5 minutes between cycles

if __name__ == "__main__":
    asyncio.run(main())  # Run the async main function properly
