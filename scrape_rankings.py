"""Scrape the monthly "top 100 most played games" from BGG, using Selenium.

For each month in the configured window, we:
  1. Load several pages of https://boardgamegeek.com/plays/bygame/... ,
     each listing games with their quantity of plays and unique-user counts.
  2. Sort all collected games by unique users (descending), because BGG no
     longer lets us sort by unique users directly on the site.
  3. Keep the top 100 and assign them positions 1..100.
  4. Cache the result for that month as cache/monthly_rankings/YYYY-MM.json .

Months already present in the cache are skipped, so the script is resumable:
if it crashes at month 142, just run it again and it picks up where it left off.

This script does NOT produce the final raw_data.json; that aggregation happens
in build_dataset.py. This script only fills the per-month cache.

Parameters live in config.py (time window, paths, headless flag). Run from
PyCharm; no command-line arguments needed.
"""

import calendar
import json
import re
import time

from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.common.exceptions import TimeoutException
from webdriver_manager.chrome import ChromeDriverManager

import config


# --- Local parameters ------------------------------------------------------

# Seconds to wait for the games table to appear on each page before giving up.
PAGE_LOAD_TIMEOUT = 20

# Polite pause between page loads (seconds), to avoid hammering BGG.
PAGE_DELAY = 1.5

# How many games we keep per month (the "top 100").
TOP_N = 100

# Candidate selectors for the cookie/consent "Accept" button. We try each in
# order until one works. OneTrust (used by many sites) is tried first.
# If none of these match, add the right one after inspecting the banner.
CONSENT_BUTTON_SELECTORS = [
    # Google fundingchoices CMP (BGG uses this): button labelled
    # "I'm OK with that", whose label is <p class="fc-button-label">.
    # We click the clickable ancestor (button), not just the <p>.
    (By.XPATH, "//p[@class='fc-button-label' and normalize-space(.)=\"I'm OK with that\"]/ancestor::button"),
    (By.XPATH, "//p[contains(@class,'fc-button-label')]/ancestor::button"),
    (By.CSS_SELECTOR, ".fc-cta-consent"),
    (By.CSS_SELECTOR, "button.fc-button.fc-cta-consent"),
    # OneTrust (kept as fallback for other pages / future changes).
    (By.ID, "onetrust-accept-btn-handler"),
    (By.CSS_SELECTOR, "button#onetrust-accept-btn-handler"),
    # Generic fallbacks.
    (By.XPATH, "//button[contains(translate(text(), 'ACCEPT', 'accept'), 'accept')]"),
    (By.XPATH, "//button[contains(translate(text(), 'AGREE', 'agree'), 'agree')]"),
    (By.XPATH, "//button[contains(translate(text(), 'CONSENT', 'consent'), 'consent')]"),
]

# --- Login (BGG now requires authentication for the plays pages) -----------

LOGIN_URL = "https://boardgamegeek.com/login"

# Selectors for the login form (Angular-rendered, so we wait explicitly).
LOGIN_USERNAME_SELECTOR = (By.ID, "inputUsername")
LOGIN_PASSWORD_SELECTOR = (By.ID, "inputPassword")
# The Sign In button has no id; match it by its (trimmed) visible text.
LOGIN_SUBMIT_SELECTOR = (
    By.XPATH,
    "//button[normalize-space(.)='Sign In']",
)

# After submitting, we consider login successful once the username/password
# form is gone. Max seconds to wait for that.
LOGIN_TIMEOUT = 20

# Regex to extract the bgg_id from a /boardgame/<id>/<slug> href.
_BGG_ID_RE = re.compile(r"/boardgame/(\d+)")


# --- Date iteration --------------------------------------------------------

def month_year_iter(start_year, start_month, end_year, end_month):
    """Yield (year, month) pairs from start (inclusive) to end (exclusive)."""
    ym_start = 12 * start_year + start_month - 1
    ym_end = 12 * end_year + end_month - 1
    for ym in range(ym_start, ym_end):
        y, m = divmod(ym, 12)
        yield y, m + 1


# --- Selenium driver -------------------------------------------------------

def make_driver(headless):
    """Create and return a Chrome WebDriver."""
    options = Options()
    if headless:
        options.add_argument("--headless=new")
    options.add_argument("--no-sandbox")
    options.add_argument("--disable-dev-shm-usage")
    options.add_argument("--disable-gpu")
    options.add_argument("--window-size=1920,1080")
    # A realistic user agent helps avoid trivial bot detection.
    options.add_argument(
        "user-agent=Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0 Safari/537.36"
    )
    service = Service(ChromeDriverManager().install())
    return webdriver.Chrome(service=service, options=options)


def _try_consent_buttons(driver):
    """Try each consent selector in the CURRENT frame. Return True on success."""
    for by, selector in CONSENT_BUTTON_SELECTORS:
        try:
            button = WebDriverWait(driver, 2).until(
                EC.element_to_be_clickable((by, selector))
            )
            button.click()
            print("Consent banner dismissed via {}={}".format(by, selector))
            time.sleep(1.0)
            return True
        except TimeoutException:
            continue
        except Exception as e:
            print("Consent click failed for {}={}: {}".format(by, selector, e))
            continue
    return False


def dismiss_consent(driver):
    """Try to accept/close the cookie-consent banner, if one is present.

    Handles both the case where the banner is in the main document and the
    case where it lives inside an iframe (as Google's fundingchoices CMP
    often does). Returns True if a button was clicked, False otherwise.
    """
    # Give the banner a moment to render.
    time.sleep(2.0)

    # 1) Try in the main document first.
    if _try_consent_buttons(driver):
        return True

    # 2) Try inside each iframe (fundingchoices renders in one).
    iframes = driver.find_elements(By.TAG_NAME, "iframe")
    for frame in iframes:
        try:
            driver.switch_to.frame(frame)
        except Exception:
            continue
        found = _try_consent_buttons(driver)
        driver.switch_to.default_content()
        if found:
            return True

    print("No consent banner found (or already accepted).")
    return False


def login(driver, username, password):
    """Log in to BGG so the plays pages become accessible.

    Navigates to the login page, dismisses the consent banner if present,
    fills the form, and clicks "Sign In". Raises RuntimeError if the login
    form does not disappear (i.e. login likely failed).
    """
    print("Logging in to BGG as", username, "...")
    driver.get(LOGIN_URL)

    # The consent banner usually appears on this first page load.
    dismiss_consent(driver)

    # Wait for the username field, then fill the form.
    username_field = WebDriverWait(driver, LOGIN_TIMEOUT).until(
        EC.element_to_be_clickable(LOGIN_USERNAME_SELECTOR)
    )
    password_field = driver.find_element(*LOGIN_PASSWORD_SELECTOR)

    username_field.clear()
    username_field.send_keys(username)
    password_field.clear()
    password_field.send_keys(password)

    submit = WebDriverWait(driver, LOGIN_TIMEOUT).until(
        EC.element_to_be_clickable(LOGIN_SUBMIT_SELECTOR)
    )
    submit.click()

    # Consider login successful once the password field is gone from the DOM.
    try:
        WebDriverWait(driver, LOGIN_TIMEOUT).until(
            EC.staleness_of(password_field)
        )
    except TimeoutException:
        raise RuntimeError(
            "Login may have failed: the login form is still present. "
            "Check your username/password."
        )
    print("Login successful.")


# --- Page parsing ----------------------------------------------------------

def parse_id_from_href(href):
    """Extract the integer bgg_id from a /boardgame/<id>/<slug> href.

    Returns None if no id can be found.
    """
    match = _BGG_ID_RE.search(href or "")
    return int(match.group(1)) if match else None


def scrape_one_page(driver, url):
    """Load one plays page and return a list of game dicts found on it.

    Each dict has keys: bgg_id, title, qty, unique_users.
    Returns an empty list if the table is absent (e.g. past the last page).
    """
    driver.get(url)

    # Wait until the games table is present (BGG may render slowly / show a
    # bot-check first). If it never appears, treat the page as empty.
    try:
        WebDriverWait(driver, PAGE_LOAD_TIMEOUT).until(
            EC.presence_of_element_located((By.CSS_SELECTOR, "table.forum_table"))
        )
    except TimeoutException:
        print("\n  [debug] table.forum_table not found within {}s on {}".format(
            PAGE_LOAD_TIMEOUT, url))
        _debug_dump(driver, "no_table")
        return []

    tables = driver.find_elements(By.CSS_SELECTOR, "table.forum_table")
    if not tables:
        print("\n  [debug] no table.forum_table after wait on {}".format(url))
        _debug_dump(driver, "no_table")
        return []

    # There can be several 'forum_table' tables on the page (e.g. a small
    # navigation/header table plus the actual data table). Pick the one that
    # actually contains game links (/boardgame/...).
    table = _pick_games_table(tables)
    if table is None:
        print("\n  [debug] {} forum_table(s) found but none contains "
              "/boardgame/ links on {}".format(len(tables), url))
        _debug_dump(driver, "no_games_table")
        return []

    rows = table.find_elements(By.TAG_NAME, "tr")

    games = []
    for row in rows:
        cells = row.find_elements(By.TAG_NAME, "td")
        if len(cells) < 3:
            continue  # header row (uses <th>) or malformed row

        # Cell 0: <a href="/boardgame/<id>/<slug>">Title</a>
        try:
            title_link = cells[0].find_element(By.TAG_NAME, "a")
        except Exception:
            continue
        href = title_link.get_attribute("href")
        title = title_link.text.strip()
        bgg_id = parse_id_from_href(href)
        if bgg_id is None or not title:
            continue

        # Cell 1: quantity of plays (plain integer text)
        qty = _parse_int(cells[1].text)

        # Cell 2: <a href="/playstats/thing/<id>">unique_users</a>
        unique_users = _parse_int(cells[2].text)
        if unique_users is None:
            continue  # without unique users we can't rank this row

        games.append({
            "bgg_id": bgg_id,
            "title": title,
            "qty": qty,
            "unique_users": unique_users,
        })

    if not games:
        print("\n  [debug] table found ({} rows) but 0 games parsed on {}".format(
            len(rows), url))
        _debug_dump(driver, "table_no_games")

    return games


def _pick_games_table(tables):
    """Among candidate tables, return the one containing /boardgame/ links.

    If several do, return the one with the most such links. Returns None if
    none qualify.
    """
    best = None
    best_count = 0
    for t in tables:
        links = t.find_elements(By.CSS_SELECTOR, "a[href*='/boardgame/']")
        if len(links) > best_count:
            best = t
            best_count = len(links)
    return best


def _debug_dump(driver, tag):
    """Save current page HTML and a screenshot for diagnosis (if DEBUG_DUMP)."""
    if not getattr(config, "DEBUG_DUMP", False):
        return
    config.CACHE_DIR.mkdir(parents=True, exist_ok=True)
    html_path = config.CACHE_DIR / "debug_{}.html".format(tag)
    png_path = config.CACHE_DIR / "debug_{}.png".format(tag)
    try:
        with open(html_path, "w", encoding="utf-8") as f:
            f.write(driver.page_source)
        print("  [debug] wrote {}".format(html_path))
    except Exception as e:
        print("  [debug] could not write HTML: {}".format(e))
    try:
        driver.save_screenshot(str(png_path))
        print("  [debug] wrote {}".format(png_path))
    except Exception as e:
        print("  [debug] could not write screenshot: {}".format(e))


def _parse_int(text):
    """Parse an integer from messy cell text (may contain whitespace/newlines).

    Returns None if no integer can be parsed.
    """
    if text is None:
        return None
    digits = re.sub(r"[^\d]", "", text)
    return int(digits) if digits else None


# --- Per-month scraping ----------------------------------------------------

def scrape_month(driver, year, month, n_hundreds):
    """Scrape one month and return the ranked top-N list of game dicts.

    Each returned dict has: bgg_id, title, qty, unique_users, position.
    """
    _, last_day = calendar.monthrange(year, month)
    start_date = "{}-{:02d}-01".format(year, month)
    end_date = "{}-{:02d}-{:02d}".format(year, month, last_day)

    # We oversample (3x) because the page is sorted by qty of plays, not by
    # unique users; the top-100-by-unique-users may include games ranked
    # lower by qty. Collecting 3*n_hundreds pages gives us a safe margin.
    collected = []
    seen_ids = set()
    n_pages = 3 * n_hundreds
    for page in range(1, n_pages + 1):
        url = ("https://boardgamegeek.com/plays/bygame/subtype/boardgame/"
               "start/{}/end/{}/page/{}".format(start_date, end_date, page))
        page_games = scrape_one_page(driver, url)
        if not page_games:
            # No table / empty page: we've run past the available data.
            break
        for g in page_games:
            # Skip catch-all / non-game entries (e.g. Unpublished Prototype),
            # BEFORE ranking, so positions stay dense and correct.
            if g["bgg_id"] in config.EXCLUDED_BGG_IDS:
                continue
            # Guard against the same game appearing twice (shouldn't happen,
            # but cheap insurance).
            if g["bgg_id"] in seen_ids:
                continue
            seen_ids.add(g["bgg_id"])
            collected.append(g)
        time.sleep(PAGE_DELAY)

    # Sort by unique users, descending, and keep the top N.
    collected.sort(key=lambda d: d["unique_users"], reverse=True)
    top = collected[:TOP_N]
    for i, g in enumerate(top):
        g["position"] = i + 1
    return top


# --- Cache helpers ---------------------------------------------------------

def month_cache_path(year, month):
    return config.CACHE_MONTHLY_DIR / "{}-{:02d}.json".format(year, month)


def save_month_cache(year, month, ranked_games):
    """Write one month's ranked list to its cache file."""
    config.CACHE_MONTHLY_DIR.mkdir(parents=True, exist_ok=True)
    payload = {
        "year": year,
        "month": month,
        "games": ranked_games,
    }
    path = month_cache_path(year, month)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(payload, f, ensure_ascii=False, indent=2)


# --- Orchestration ---------------------------------------------------------

def scrape_rankings():
    """Scrape all configured months, skipping those already cached."""
    months = list(month_year_iter(
        config.START_YEAR, config.START_MONTH,
        config.END_YEAR, config.END_MONTH,
    ))
    total = len(months)
    print("Months to cover: {} ({}-{:02d} .. {}-{:02d} exclusive)".format(
        total, config.START_YEAR, config.START_MONTH,
        config.END_YEAR, config.END_MONTH))

    # Figure out which months still need scraping.
    if config.IGNORE_RANKINGS_CACHE:
        todo = list(months)
        print("IGNORE_RANKINGS_CACHE is True: re-scraping all {} months "
              "(existing cache files will be overwritten).".format(len(todo)))
    else:
        todo = [(y, m) for (y, m) in months if not month_cache_path(y, m).exists()]
        print("Already cached: {} | To scrape: {}".format(
            total - len(todo), len(todo)))

    if not todo:
        print("Nothing to do. All months are cached.")
        return

    # Read credentials from .env (via config). Both must be set.
    username = config.BGG_USERNAME
    password = config.BGG_PASSWORD
    if not username or not password:
        raise RuntimeError(
            "BGG_USERNAME and BGG_PASSWORD must be set in your .env file. "
            "See .env.example."
        )

    driver = make_driver(config.SELENIUM_HEADLESS)
    try:
        # Log in once. This handles the consent banner and authenticates the
        # session; the session cookie then applies to all page loads below.
        login(driver, username, password)

        for i, (year, month) in enumerate(todo, start=1):
            print("[{}/{}] Scraping {}-{:02d} ...".format(i, len(todo), year, month),
                  end=" ", flush=True)
            ranked = scrape_month(driver, year, month, config.N_HUNDREDS)
            if len(ranked) < TOP_N:
                print("WARNING: only {} games found (expected {}).".format(
                    len(ranked), TOP_N), end=" ")
            save_month_cache(year, month, ranked)
            print("saved {} games.".format(len(ranked)))
    finally:
        driver.quit()

    print("Done.")


if __name__ == "__main__":
    scrape_rankings()