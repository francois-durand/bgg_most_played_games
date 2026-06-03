"""Scrape per-game RAW metadata from BGG game pages, using Selenium.

Design principle: this script only CAPTURES data, it does not INTERPRET it.
For each field we store the rawest useful form (text as shown on BGG, or the
value of a dedicated microdata tag). Turning '3–7' into {min:3,max:7}, deciding
what '30+' means, etc. is deferred to a separate post-processing step
(build_dataset.py), so that interpretation can be iterated on WITHOUT
re-scraping every game.

For every game appearing in the cached monthly rankings we load its
/boardgame/<id>/credits page and capture:
  - image_url
  - players_official: {min_raw, max_raw}      (from <meta itemprop=min/maxValue>)
  - players_secondary_text                     (full text, e.g. "Community: 3–7 — Best: 4–5")
  - players_secondary_spans                    (each <span> text, as a backup)
  - playtime_primary_text                      (e.g. "30 Min")
  - age_official_raw                           (from <span itemprop=suggestedMinAge>)
  - age_secondary_text                         (e.g. "Community: 10+")
  - weight_primary_text                        (e.g. "Weight: 2.31 / 5")
  - credits_table: every row of the detailed credits table (ul.outline),
    keyed by snake_case title. Link rows (designers, artist, publishers,
    categories, mechanisms, family, and any person-role rows) become lists of
    {name, id, type}; text rows (primary_name, alternate_names, year_released)
    become strings; empty/N/A rows become null. Captured exhaustively so new
    BGG fields are picked up automatically.

We scrape the /credits page because it keeps the same top gameplay banner
(players/time/age/weight) AND adds a clean, complete detail table.

Results are cached one file per game: cache/game_metadata/<bgg_id>.json .
The script is resumable: cached games are skipped unless IGNORE_METADATA_CACHE.
Set TEST_SINGLE_GAME_ID in config to scrape just one game (cache untouched).

Run scrape_rankings.py first so the rankings cache exists. Run from PyCharm.
"""

import json
import re
import time

from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.common.exceptions import TimeoutException

import config
import bgg_selenium


# --- Local parameters ------------------------------------------------------

# Seconds to wait for the gameplay panel to render before giving up.
PAGE_LOAD_TIMEOUT = 20

# Polite pause between game pages (seconds).
PAGE_DELAY = 1.5


# --- Small DOM helpers -----------------------------------------------------

def _safe_text(element):
    """Visible text of an element, with collapsed whitespace; '' on failure."""
    try:
        return re.sub(r"\s+", " ", element.text).strip()
    except Exception:
        return ""


def _find_or_none(scope, by, selector):
    try:
        return scope.find_element(by, selector)
    except Exception:
        return None


def _attr_or_none(scope, by, selector, attr):
    el = _find_or_none(scope, by, selector)
    if el is None:
        return None
    try:
        return el.get_attribute(attr)
    except Exception:
        return None


def _gameplay_li(gameplay_scope, h3_label):
    """Return the <li class=gameplay-item> whose <h3> contains h3_label."""
    for li in gameplay_scope.find_elements(By.CSS_SELECTOR, "li.gameplay-item"):
        h3 = _find_or_none(li, By.TAG_NAME, "h3")
        if h3 is not None and h3_label in _safe_text(h3):
            return li
    return None


# --- Raw field extractors --------------------------------------------------

def extract_image(driver):
    """Return the main cover image URL, or None."""
    src = _attr_or_none(driver, By.CSS_SELECTOR, "img[itemprop='image']", "src")
    if not src:
        src = _attr_or_none(driver, By.CSS_SELECTOR, "img[itemprop='image']", "ng-src")
    return src


def extract_players_raw(gameplay_scope):
    """Capture raw player-count info (no interpretation).

    Returns dict with:
      - official: {min_raw, max_raw} from <meta itemprop=minValue/maxValue>
      - secondary_text: full text of the secondary block (community/best)
      - secondary_spans: list of each <span> text in the secondary block
    """
    out = {"official": None, "secondary_text": None, "secondary_spans": []}
    li = _gameplay_li(gameplay_scope, "Number of Players")
    if li is None:
        return out

    min_v = _attr_or_none(li, By.CSS_SELECTOR, "meta[itemprop='minValue']", "content")
    max_v = _attr_or_none(li, By.CSS_SELECTOR, "meta[itemprop='maxValue']", "content")
    if min_v is not None or max_v is not None:
        out["official"] = {"min_raw": min_v, "max_raw": max_v}

    secondary = _find_or_none(li, By.CSS_SELECTOR, ".gameplay-item-secondary")
    if secondary is not None:
        out["secondary_text"] = _safe_text(secondary)
        spans = secondary.find_elements(By.TAG_NAME, "span")
        out["secondary_spans"] = [_safe_text(s) for s in spans if _safe_text(s)]
    return out


def extract_playtime_raw(gameplay_scope):
    """Capture the raw playing-time text, e.g. '30 Min' or '30 – 45 Min'."""
    li = _gameplay_li(gameplay_scope, "Play Time")
    if li is None:
        return None
    primary = _find_or_none(li, By.CSS_SELECTOR, ".gameplay-item-primary")
    return _safe_text(primary) if primary is not None else None


def extract_age_raw(gameplay_scope):
    """Capture raw age info: official (from itemprop) and secondary text."""
    out = {"official_raw": None, "secondary_text": None}
    li = _gameplay_li(gameplay_scope, "Suggested Age")
    if li is None:
        return out
    off = _find_or_none(li, By.CSS_SELECTOR, "[itemprop='suggestedMinAge']")
    if off is not None:
        out["official_raw"] = _safe_text(off)
    secondary = _find_or_none(li, By.CSS_SELECTOR, ".gameplay-item-secondary")
    if secondary is not None:
        out["secondary_text"] = _safe_text(secondary)
    return out


def extract_weight_raw(gameplay_scope):
    """Capture the raw weight/complexity text, e.g. 'Weight: 2.31 / 5'."""
    li = _gameplay_li(gameplay_scope, "Complexity")
    if li is None:
        return None
    primary = _find_or_none(li, By.CSS_SELECTOR, ".gameplay-item-primary")
    return _safe_text(primary) if primary is not None else None


def _normalize_key(title):
    """Turn a row title like 'Graphic Designer' into a snake_case key."""
    key = title.strip().lower()
    key = re.sub(r"[^a-z0-9]+", "_", key).strip("_")
    return key


def _links_from_li(li):
    """Return all {name, id, type} links found in an outline-item li.

    type is the BGG link type, e.g. 'boardgamedesigner'. Reads textContent so
    that hidden ('+ N more') entries are included. De-duplicated.
    """
    results = []
    seen = set()
    for a in li.find_elements(By.CSS_SELECTOR, "a[href]"):
        href = a.get_attribute("href") or ""
        m = re.search(r"/(boardgame[a-z]+)/(\d+)", href)
        if not m:
            continue  # not a person/classification link (e.g. /browse/...)
        link_type = m.group(1)
        link_id = int(m.group(2))
        raw_name = a.get_attribute("textContent") or ""
        name = re.sub(r"\s+", " ", raw_name).strip()
        key = (link_type, link_id, name)
        if name and key not in seen:
            seen.add(key)
            results.append({"name": name, "id": link_id, "type": link_type})
    return results


def _find_credits_outline(driver):
    """Return the ul.outline that is the credits table, among several on the page.

    The /credits page has multiple <ul class="outline"> blocks (e.g. collection
    stats: Own/Wishlist/For Trade — AND the actual credits table). We pick the
    one containing the most /boardgame<type>/<id> links (designers, publishers,
    mechanics, ...). Returns None if none has any such link.
    """
    best = None
    best_count = 0
    for ul in driver.find_elements(By.CSS_SELECTOR, "ul.outline"):
        good = 0
        for a in ul.find_elements(By.CSS_SELECTOR, "a[href*='/boardgame']"):
            href = a.get_attribute("href") or ""
            if re.search(r"/boardgame[a-z]+/\d+", href):
                good += 1
        if good > best_count:
            best = ul
            best_count = good
    return best


def extract_credits(driver):
    """Capture the entire detailed credits table (ul.outline), exhaustively.

    For every row we store, under a snake_case key derived from its title:
      - if the row has person/classification links: a list of {name, id, type}
      - otherwise: the text value (with 'N/A' treated as None)

    This captures everything BGG offers (Designers, Artist, Publishers,
    Developer, Graphic Designer, Sculptor, Editor, Writer, Insert Designer,
    Categories, Mechanisms, Family, Primary Name, Alternate Names, Year
    Released, and anything new BGG might add) without having to enumerate them.

    Returns a dict: {"credits_table": {key: value, ...}}.
    """
    table = {}
    ul = _find_credits_outline(driver)
    if ul is None:
        return {"credits_table": table}

    for li in ul.find_elements(By.CSS_SELECTOR, "li.outline-item"):
        title_el = _find_or_none(li, By.CSS_SELECTOR, ".outline-item-title")
        if title_el is None:
            continue
        title = _safe_text(title_el)
        if not title:
            continue
        key = _normalize_key(title)

        links = _links_from_li(li)
        if links:
            table[key] = links
        else:
            # Text-valued row: li text minus the title.
            full = _safe_text(li)
            val = full[len(title):].strip() if full.startswith(title) else full
            if val and val.upper() != "N/A":
                table[key] = val
            else:
                table[key] = None
    return {"credits_table": table}


# --- Per-game scraping -----------------------------------------------------

def _slug_from_url(url, bgg_id):
    """Extract the slug from a canonical URL .../boardgame/<id>/<slug>[/...].

    Returns the slug string, or None if not found.
    """
    m = re.search(r"/boardgame/{}/([^/?#]+)".format(bgg_id), url or "")
    return m.group(1) if m else None


def scrape_game(driver, bgg_id):
    """Load a game's /credits page and return its raw metadata dict.

    BGG requires the slug in the URL: /boardgame/<id>/<slug>/credits . Without
    the slug, /boardgame/<id>/credits silently redirects to the game's main
    page (which lacks the clean credits table). So we first load /boardgame/<id>,
    let BGG redirect to the canonical /boardgame/<id>/<slug>, read that slug
    from the resulting URL, then navigate to the credits page.

    Returns the metadata dict, or None on failure.
    """
    # Step 1: resolve the canonical slug. Also harvest "expandsboardgame"
    # from the JSON preload while we're here — it's only on the main page.
    driver.get("https://boardgamegeek.com/boardgame/{}".format(bgg_id))
    try:
        WebDriverWait(driver, PAGE_LOAD_TIMEOUT).until(
            EC.presence_of_element_located((By.CSS_SELECTOR, "ul.gameplay"))
        )
    except TimeoutException:
        print("\n  [debug] main page gameplay not found for id {}".format(bgg_id))
        _debug_dump(driver, "metadata_no_gameplay")
        return None

    slug = _slug_from_url(driver.current_url, bgg_id)
    main_page_source = driver.page_source
    expands_boardgames = _extract_expands_boardgames(main_page_source)

    # Step 2: load the real credits page (with slug).
    if slug:
        credits_url = "https://boardgamegeek.com/boardgame/{}/{}/credits".format(
            bgg_id, slug)
    else:
        # Fallback: try without slug (may redirect, but better than nothing).
        credits_url = "https://boardgamegeek.com/boardgame/{}/credits".format(bgg_id)
    driver.get(credits_url)

    # Wait for the gameplay panel (players/time/age/weight live here too).
    try:
        WebDriverWait(driver, PAGE_LOAD_TIMEOUT).until(
            EC.presence_of_element_located((By.CSS_SELECTOR, "ul.gameplay"))
        )
    except TimeoutException:
        print("\n  [debug] credits-page gameplay not found for id {}".format(bgg_id))
        _debug_dump(driver, "metadata_no_gameplay")
        return None

    gameplay = _find_or_none(driver, By.CSS_SELECTOR, "ul.gameplay")

    # Wait for the credits detail table (ul.outline) to render.
    try:
        WebDriverWait(driver, PAGE_LOAD_TIMEOUT).until(
            EC.presence_of_element_located(
                (By.CSS_SELECTOR, "ul.outline a[href*='/boardgamedesigner/']"))
        )
    except TimeoutException:
        print("\n  [debug] credits table not found in time for id {} "
              "(continuing).".format(bgg_id))

    data = {
        "bgg_id": bgg_id,
        "image_url": extract_image(driver),
        "expands_boardgames": expands_boardgames,
        "players_official": None,
        "players_secondary_text": None,
        "players_secondary_spans": [],
        "playtime_primary_text": extract_playtime_raw(gameplay),
        "age_official_raw": None,
        "age_secondary_text": None,
        "weight_primary_text": extract_weight_raw(gameplay),
    }

    players = extract_players_raw(gameplay)
    data["players_official"] = players["official"]
    data["players_secondary_text"] = players["secondary_text"]
    data["players_secondary_spans"] = players["secondary_spans"]

    age = extract_age_raw(gameplay)
    data["age_official_raw"] = age["official_raw"]
    data["age_secondary_text"] = age["secondary_text"]

    data.update(extract_credits(driver))

    # A game with no designer is unusual but legitimate. Check by link TYPE
    # (boardgamedesigner), not by a title-derived key, because BGG's row title
    # may be 'Designer' or 'Designers' depending on the game.
    if not _has_link_type(data.get("credits_table", {}), "boardgamedesigner"):
        print("\n  [note] no designers found for id {}.".format(bgg_id), end=" ")

    return data


def _extract_expands_boardgames(page_source):
    """Extract the list of boardgames that this item is an expansion of.

    BGG embeds the relationship in a JSON literal on the main /boardgame/<id>
    page: a `GEEK.geekitemPreload = { ... }` assignment that contains, among
    other things, an `expandsboardgame` array. We don't need a full JSON
    parser for this; a regex finds the array slice, then we parse just that.

    Returns a list of {name, bgg_id} dicts (possibly empty for standalones).
    """
    # Find the JSON array literal after the "expandsboardgame": key. We grab
    # the bracket-balanced slice without trying to parse the whole preload.
    m = re.search(r'"expandsboardgame"\s*:\s*(\[)', page_source)
    if not m:
        return []
    start = m.start(1)
    depth = 0
    i = start
    while i < len(page_source):
        ch = page_source[i]
        if ch == "[":
            depth += 1
        elif ch == "]":
            depth -= 1
            if depth == 0:
                end = i + 1
                break
        i += 1
    else:
        return []  # unbalanced; defensive
    array_text = page_source[start:end]
    try:
        items = json.loads(array_text)
    except json.JSONDecodeError:
        return []
    out = []
    for it in items or []:
        if not isinstance(it, dict):
            continue
        try:
            out.append({
                "name": it.get("name") or "",
                "bgg_id": int(it.get("objectid")),
            })
        except (TypeError, ValueError):
            continue
    return out


def _has_link_type(credits_table, link_type):
    """True if any row in credits_table contains a link of the given type."""
    return _count_link_type(credits_table, link_type) > 0


def _count_link_type(credits_table, link_type):
    """Count links of the given type across all rows of credits_table."""
    n = 0
    for value in credits_table.values():
        if isinstance(value, list):
            for item in value:
                if isinstance(item, dict) and item.get("type") == link_type:
                    n += 1
    return n


def _debug_dump(driver, tag):
    if not getattr(config, "DEBUG_DUMP", False):
        return
    config.CACHE_DIR.mkdir(parents=True, exist_ok=True)
    try:
        with open(config.CACHE_DIR / "debug_{}.html".format(tag),
                  "w", encoding="utf-8") as f:
            f.write(driver.page_source)
        driver.save_screenshot(str(config.CACHE_DIR / "debug_{}.png".format(tag)))
        print("  [debug] dumped page to cache/debug_{}.html/.png".format(tag))
    except Exception as e:
        print("  [debug] dump failed: {}".format(e))


# --- Cache helpers ---------------------------------------------------------

def metadata_cache_path(bgg_id):
    return config.CACHE_METADATA_DIR / "{}.json".format(bgg_id)


def save_metadata_cache(bgg_id, data):
    config.CACHE_METADATA_DIR.mkdir(parents=True, exist_ok=True)
    with open(metadata_cache_path(bgg_id), "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)


# --- Collect the set of games from the rankings cache ----------------------

def collect_game_ids():
    """Read the rankings cache; return {bgg_id: title} for all games seen."""
    games = {}
    if not config.CACHE_MONTHLY_DIR.exists():
        raise RuntimeError(
            "No rankings cache found at {}. Run scrape_rankings.py first.".format(
                config.CACHE_MONTHLY_DIR))
    for path in sorted(config.CACHE_MONTHLY_DIR.glob("*.json")):
        with open(path, encoding="utf-8") as f:
            payload = json.load(f)
        for g in payload.get("games", []):
            games[g["bgg_id"]] = g.get("title", "")
    return games


# --- Orchestration ---------------------------------------------------------

def scrape_metadata():
    # --- Single-game test mode --------------------------------------------
    test_id = getattr(config, "TEST_SINGLE_GAME_ID", None)
    if test_id:
        print("TEST_SINGLE_GAME_ID is set: scraping only game {} "
              "(cache not touched).".format(test_id))
        driver = bgg_selenium.make_logged_in_driver()
        try:
            data = scrape_game(driver, test_id)
        finally:
            driver.quit()
        print("\n--- Result for game {} ---".format(test_id))
        print(json.dumps(data, ensure_ascii=False, indent=2))
        return

    all_games = collect_game_ids()
    print("Distinct games across all rankings: {}".format(len(all_games)))

    if config.IGNORE_METADATA_CACHE:
        todo = list(all_games.items())
        print("IGNORE_METADATA_CACHE is True: re-scraping all {} games.".format(
            len(todo)))
    else:
        todo = [(gid, title) for gid, title in all_games.items()
                if not metadata_cache_path(gid).exists()]
        print("Already cached: {} | To scrape: {}".format(
            len(all_games) - len(todo), len(todo)))

    if not todo:
        print("Nothing to do. All game metadata is cached.")
        return

    driver = bgg_selenium.make_logged_in_driver()
    try:
        for i, (bgg_id, title) in enumerate(todo, start=1):
            print("[{}/{}] {} (id {}) ...".format(i, len(todo), title, bgg_id),
                  end=" ", flush=True)
            data = scrape_game(driver, bgg_id)
            if data is None:
                print("FAILED.")
                continue
            save_metadata_cache(bgg_id, data)
            n_designers = _count_link_type(
                data.get("credits_table", {}), "boardgamedesigner")
            print("saved ({} designer(s)).".format(n_designers))
            time.sleep(PAGE_DELAY)
    finally:
        driver.quit()

    print("Done.")


if __name__ == "__main__":
    scrape_metadata()