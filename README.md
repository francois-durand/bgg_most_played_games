# bgg_most_played_games

A yearly ranking of the board games most played on BoardGameGeek since
January 2010, based on monthly play counts rather than ratings.

The current edition is published as an interactive web page on GitHub Pages
and as a geeklist on BoardGameGeek.

## Quick links

- **Interactive version:** <https://francois-durand.github.io/bgg_most_played_games/>
- **BGG geeklist (current):** <https://boardgamegeek.com/geeklist/379049/most-played-games-of-all-time-april-2025-version>
- **About / methodology:** <https://francois-durand.github.io/bgg_most_played_games/about.html>

## Repository layout

```
.
├── docs/                       # GitHub Pages site (interactive ranking)
├── archive/<YEAR>.json         # Frozen rankings per edition (delta source)
├── YYYY_MM_DD_Published_..._/  # Per-edition snapshots of generated artifacts
├── cache/                      # Local-only scrape cache (gitignored)
├── config.py                   # Edition window, paths, credentials loader
├── scrape_*.py                 # BGG scrapers (Selenium)
├── build_*.py                  # Data builders (scores, games, web payload)
├── prepare_geeklist.py         # Generates the BGG geeklist body
├── archive_edition.py          # Freezes one edition (archive + folder move)
├── check_coverage.py           # Sanity report on scraped fields
└── main.py                     # End-to-end pipeline (and manual)
```

## Workflow for one edition

```
1. Edit config.py:  set END_YEAR (and confirm END_MONTH = 5).

2. Run main.py.  It scrapes (resumable), computes scores, builds games.json,
   produces the web payload (docs/web_data.json, docs/credits_data.json),
   and writes geeklist.txt.

3. Review the generated files:
     - scores.json (ranks and points)
     - games.json (full per-game metadata)
     - geeklist.txt (text to paste into BGG)

4. Publish the geeklist on BGG, copy its URL.

5. Update docs/current_geeklist.json with the new URL/id.

6. Commit and push.  GitHub Pages serves docs/* automatically.

7. Run archive_edition.py.  It writes archive/<YEAR>.json (frozen for
   future-edition deltas) and moves scores.json, games.json, geeklist.txt
   into a YYYY_MM_DD_Published_version_April_YYYY/ folder.

8. Commit the new archive file and the published-version folder.
```

Each step is also runnable on its own (the scripts are independent
modules). `main.py` just chains them in the right order.

## How the pieces fit

- **Scrapers** (`scrape_rankings.py`, `scrape_metadata.py`) populate the
  `cache/` folder, fetching only what's missing. They use Selenium because
  BGG requires authentication for the `plays/bygame` pages.

- **Builders** read from `cache/` and the previous edition's `archive/<Y-1>.json`:
  - `build_scores.py` → `scores.json` (rank, points, history, deltas).
  - `build_games.py` → `games.json` (titles, players, time, age, weight,
    designers, artists, mechanics, etc.).
  - `build_web_data.py` → `docs/web_data.json` + `docs/credits_data.json`
    (merged top-N payload served to the browser).

- **`prepare_geeklist.py`** consumes `scores.json` + `games.json` to
  produce `geeklist.txt` — three lines per game in BBCode for manual
  paste into BGG's geeklist form.

- **`archive_edition.py`** freezes the year: writes `archive/<YEAR>.json`
  (the source of truth for next year's deltas — never regenerated) and
  moves the loose artifacts into a dated folder.

- **`check_coverage.py`** reports field coverage on `games.json`. Run it
  to catch regressions when BGG changes its HTML.

## Setup

Requires Python 3.12+ and Chrome (for Selenium).

```
pip install -r requirements.txt
cp .env.example .env
# then edit .env to add your BGG credentials
```

Selenium uses `webdriver-manager` to install a Chrome driver matching your
installed Chrome.

`.env` is gitignored — never commit your credentials.

## Notes on data freshness

- The site shows the latest published edition only. Past editions live in
  `archive/<YEAR>.json` and in the dated `YYYY_MM_DD_Published_...`
  folders, both committed.
- Once published, an edition is frozen. Future-year deltas reference the
  *published* ranking, not what would be computed today from newer data.

## License

[MIT](LICENSE).