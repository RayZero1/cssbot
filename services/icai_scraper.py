import requests
from bs4 import BeautifulSoup
from datetime import datetime, date, timedelta

ICAI_URL = "https://boslive.icai.org/examination_announcement.php"

HEADERS = {
    "User-Agent": "CSSBot/1.0 (CA Study Space)"
}

def fetch_todays_announcements():
    try:
        response = requests.get(ICAI_URL, headers=HEADERS, timeout=15)
        response.raise_for_status()

        soup = BeautifulSoup(response.text, "html.parser")
        announcements = soup.find_all("div", class_="ann_details")

        results = []
        start_date = date.today() - timedelta(days=7)
        end_date = date.today()

        for ann in announcements:
            date_p = ann.find("p")
            link_tag = ann.find("a")
            title_tag = ann.find("h4")

            if not (date_p and link_tag and title_tag):
                continue

            raw_date = date_p.get_text(strip=True)

            try:
                parts = raw_date.split(",")
                date_part = f"{parts[0].strip()}, {parts[1].strip()}"
                ann_date = datetime.strptime(date_part, "%d %B, %Y").date()
            except Exception:
                continue
            
            if ann_date < start_date or ann_date > end_date:
                continue

            results.append({
                "id": link_tag["href"],
                "title": title_tag.get_text(strip=True),
                "date": raw_date,
                "url": f"https://boslive.icai.org/{link_tag['href']}"
            })

        return results
    except Exception as e:
        print(f"[ICAI Scraper] Error fetching announcements: {e}")
        return []