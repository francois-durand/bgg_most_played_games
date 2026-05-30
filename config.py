"""Shared configuration for the BGG most-played-games project.

All scripts in this project import their shared parameters from here.
Parameters that are specific to a single script live in that script.

Edit the values below as needed, then run the scripts from PyCharm
(or any IDE) without command-line arguments.
"""

import os
from pathlib import Path

from dotenv import load_dotenv

# --- Time window for the monthly rankings ----------------------------------
# We scrape the monthly top-100 of plays for each month in [START, END).
# END_MONTH is the first month NOT taken into account.

START_YEAR = 2010
START_MONTH = 1
END_YEAR = 2025
END_MONTH = 5

# Number of "hundreds" of games to look at each month, before sorting by
# distinct users and keeping only the top 100. We oversample because BGG no
# longer lets us sort by # distinct users directly on the website.
N_HUNDREDS = 1

# Board games to exclude from the rankings entirely (by bgg_id). These are
# catch-all / non-game entries on BGG. They are removed BEFORE positions are
# assigned, so the remaining games get dense, correct ranks 1..100.
#   18291 = "Unpublished Prototype"
EXCLUDED_BGG_IDS = {18291}

# --- Paths -----------------------------------------------------------------

# Project root = directory containing this config.py.
PROJECT_ROOT = Path(__file__).resolve().parent

# Cache directory: intermediate results, robust to crashes and resumable.
CACHE_DIR = PROJECT_ROOT / 'cache'
CACHE_MONTHLY_DIR = CACHE_DIR / 'monthly_rankings'   # one file per (year, month)
CACHE_METADATA_DIR = CACHE_DIR / 'game_metadata'     # one file per bgg_id

# Final outputs.
RAW_DATA_JSON = PROJECT_ROOT / 'raw_data.json'
GAMES_JSON = PROJECT_ROOT / 'games.json'
IMAGES_DIR = PROJECT_ROOT / 'images'

# --- BGG API ---------------------------------------------------------------

# Load .env file (in the project root) into os.environ.
load_dotenv(PROJECT_ROOT / '.env')

# Application token required by the BGG XML API since fall 2025.
# Get one by registering at boardgamegeek.com and store it in .env.
BGG_API_TOKEN = os.environ.get('BGG_API_TOKEN')

# BGG account credentials, used to log in for scraping the plays pages (which
# now require authentication). Both are read from .env (which is git-ignored).
BGG_USERNAME = os.environ.get('BGG_USERNAME')
BGG_PASSWORD = os.environ.get('BGG_PASSWORD')

# Polite delay between successive BGG API requests (seconds).
BGG_API_DELAY = 2.0

# --- Cache behavior --------------------------------------------------------

# Each scraping stage has its own cache and its own "ignore" flag, so you can
# (for instance) keep the hard-won monthly rankings while re-scraping game
# metadata over and over during development.
#
# When True, ignore the existing cache for that stage and re-scrape everything
# (overwriting cached files). Leave False for normal runs so that scraping is
# resumable after a crash.

# Cache of monthly rankings (used by scrape_rankings.py).
IGNORE_RANKINGS_CACHE = False

# Cache of per-game metadata (used by scrape_metadata.py).
IGNORE_METADATA_CACHE = False

# Debugging aid for scrape_metadata.py: if set to a bgg_id (int), the metadata
# scraper processes ONLY that game (ignoring the rankings cache and the
# metadata cache), prints the result, and does not touch the cache. Set to
# None for normal runs.
TEST_SINGLE_GAME_ID = None

# --- Selenium --------------------------------------------------------------

# Run Chrome without opening a window. Set to False for debugging.
SELENIUM_HEADLESS = True

# When True, dump page HTML + a screenshot to the cache dir whenever a page
# yields no games, to help diagnose selector/timing problems. Test-only.
DEBUG_DUMP = True