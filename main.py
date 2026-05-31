"""End-to-end pipeline for one edition of the most-played-games ranking.

This script is both an executable and a manual. Each step is documented in
the function calls below; the inline comments explain what to do between
automated stages (the manual ones — reviewing artifacts, publishing the
geeklist, updating the geeklist URL).

Workflow per edition:
  1. Set END_YEAR (and confirm END_MONTH = 5) in config.py.
  2. Run main.py. It will scrape (resumable, incremental), compute scores,
     build the merged web payload, and generate geeklist.txt.
  3. Review scores.json, games.json, and geeklist.txt.
  4. Publish the geeklist on BGG using geeklist.txt.
  5. Update docs/current_geeklist.json with the new geeklist URL/id.
  6. Commit & push (docs/* goes live via GitHub Pages).
  7. When everything checks out, run archive_edition.py to freeze this
     edition into archive/<year>.json AND move the artifacts to a dated
     'Published_version_April_YYYY' folder.

You don't have to run main.py as one shot — every step is also runnable
on its own from PyCharm. main.py mostly documents the order and skips
nothing.
"""

import scrape_rankings
import scrape_metadata
import build_scores
import build_games
import build_web_data
import prepare_geeklist


def main():
    # 1. Scrape BGG. Both scrapers are resumable and cache aware: if the
    #    cache already has a month / game, the corresponding file isn't
    #    re-fetched. Re-running is cheap.
    print("\n=== 1. Scrape monthly rankings ===")
    scrape_rankings.scrape_rankings()

    print("\n=== 2. Scrape game metadata ===")
    scrape_metadata.scrape_metadata()

    # 2. Compute the per-game scores and metadata for the current edition.
    print("\n=== 3. Build scores.json ===")
    build_scores.build_scores()

    print("\n=== 4. Build games.json ===")
    build_games.build_games()

    # 3. Merge scores + games for the web UI, and generate the geeklist
    #    text for manual paste into BGG.
    print("\n=== 5. Build web payload (docs/web_data.json, docs/credits_data.json) ===")
    build_web_data.build_web_data()

    print("\n=== 6. Generate geeklist.txt ===")
    prepare_geeklist.main()

    # 4. Manual steps from here on.
    print()
    print("=" * 70)
    print("Automated steps done. Manual steps remaining:")
    print("=" * 70)
    print("  1. Review scores.json / games.json / geeklist.txt at the project root.")
    print("  2. Publish the geeklist on BGG using geeklist.txt.")
    print("  3. Update docs/current_geeklist.json with the new BGG URL/id.")
    print("  4. Commit & push (GitHub Pages will pick up docs/* automatically).")
    print()
    print("Then, once everything is published and verified:")
    print("  5. Run archive_edition.py to freeze this edition.")
    print()


if __name__ == "__main__":
    main()