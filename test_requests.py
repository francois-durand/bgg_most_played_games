"""Quick test: can we scrape the BGG monthly plays page with plain `requests`,
or do we need Selenium?

Run this from PyCharm. Look at the printed output:
  - If you see "SUCCESS" and a list of games, plain requests works -> we'll
    write scrape_rankings.py without Selenium (faster, simpler).
  - If you see "BLOCKED (403)" or no games found, BGG blocks plain requests
    -> we'll use Selenium instead.

Requires: pip install requests beautifulsoup4
"""

import requests
from bs4 import BeautifulSoup

URL = ("https://boardgamegeek.com/plays/bygame/subtype/boardgame/"
       "start/2026-01-01/end/2026-01-31/page/1")

HEADERS = {
    "User-Agent": ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                   "AppleWebKit/537.36 (KHTML, like Gecko) "
                   "Chrome/124.0 Safari/537.36"),
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Accept-Language": "en-US,en;q=0.9",
}


def main():
    print("Fetching:", URL)
    try:
        r = requests.get(URL, headers=HEADERS, timeout=30)
    except Exception as e:
        print("ERROR during request:", type(e).__name__, e)
        return

    print("HTTP status:", r.status_code)
    print("Response length:", len(r.text), "chars")

    if r.status_code == 403:
        print("\n>>> BLOCKED (403). Plain requests does NOT work. We'll use Selenium.")
        return
    if r.status_code != 200:
        print(f"\n>>> Unexpected status {r.status_code}. Inspect manually.")
        return

    soup = BeautifulSoup(r.text, "html.parser")
    table = soup.find("table", class_="forum_table")
    if table is None:
        print("\n>>> No <table class='forum_table'> found.")
        print("    Either the page is JS-rendered (needs Selenium) or the")
        print("    HTML structure changed. First 1000 chars of response:\n")
        print(r.text[:1000])
        return

    rows = table.find_all("tr")
    games = []
    for row in rows:
        cells = row.find_all("td")
        if len(cells) < 3:
            continue  # header row or malformed
        title_link = cells[0].find("a")
        if title_link is None:
            continue
        title = title_link.get_text(strip=True)
        href = title_link.get("href", "")
        qty = cells[1].get_text(strip=True)
        unique_users = cells[2].get_text(strip=True)
        games.append((title, href, qty, unique_users))

    if not games:
        print("\n>>> Table found but no game rows parsed. Structure may differ.")
        return

    print(f"\n>>> SUCCESS: parsed {len(games)} games with plain requests.\n")
    print("First 5 rows (title | href | qty | unique_users):")
    for g in games[:5]:
        print("  ", g)
    print("\nLast row:")
    print("  ", games[-1])


if __name__ == "__main__":
    main()