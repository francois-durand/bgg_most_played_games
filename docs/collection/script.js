/* My Board Game Collection — single-page client.

   Adapted from the Most Played Games page. Same UI patterns (filters,
   sort, search, expand/collapse), but without rank/delta/points/history
   (which don't apply to a personal collection) and with two additions:
     - my_rating (shown in the extras, used for default sort);
     - expansions (owned expansions are listed inside the card's extras).
*/

const DATA_URL = "collection_data.json";

const $list   = document.getElementById("game-list");
const $status = document.getElementById("status");

const state = {
  allGames: [],
  expanded: new Set(),
};

async function main() {
  let payload;
  try {
    const response = await fetch(DATA_URL);
    if (!response.ok) throw new Error("HTTP " + response.status);
    payload = await response.json();
  } catch (err) {
    $status.textContent = "Could not load data: " + err.message;
    return;
  }

  state.allGames = payload.games || [];
  $status.remove();

  bindControls();
  applyHashFilter();
  applyFiltersAndSort();
}

function applyHashFilter() {
  const hash = window.location.hash || "";
  /* Expected format: #search=<urlencoded text>. We're lenient: anything that
     starts with "#search=" is honored, the rest is ignored. */
  const m = hash.match(/^#search=(.*)$/);
  if (!m) return;
  try {
    const value = decodeURIComponent(m[1]);
    if (!value) return;
    document.getElementById("search-input").value = value;
    /* Open the panel so the user sees the active filter — same UX as
     clicking the magnifier on this page. */
    setFiltersPanelOpen(true);
  } catch (err) {
    /* Bad URI encoding — silently ignore. */
  }
}

/* --- Controls binding ---------------------------------------------------- */

function bindControls() {
  const ids = [
    "search-input", "players-source", "duration-min", "duration-max",
    "age-source", "age-suitable", "age-min", "sort-select",
  ];
  for (const id of ids) {
    const el = document.getElementById(id);
    if (!el) continue;
    /* "input" fires on every keystroke for text/number inputs; "change" fires
       on commit for selects. We listen to both to cover everything. */
    el.addEventListener("input",  applyFiltersAndSort);
    el.addEventListener("change", applyFiltersAndSort);
  }
  // Player count checkboxes (multiple elements, same handler).
  document.querySelectorAll("input[name='players']").forEach(cb => {
    cb.addEventListener("change", applyFiltersAndSort);
  });

  document.getElementById("reset-filters")
      .addEventListener("click", resetFilters);

  // Filters panel: collapsible header.
  document.getElementById("filters-toggle").addEventListener("click", () => {
    setFiltersPanelOpen(!isFiltersPanelOpen());
  });

  // Delegated click for the magnifier icons next to people / match entries:
  // clicking them clears existing filters, sets the search input to that name,
  // expands the Filters panel, and scrolls to the top.
  document.body.addEventListener("click", (event) => {
    const trigger = event.target.closest("[data-search-name]");
    if (!trigger) return;
    event.preventDefault();
    event.stopPropagation();
    setSearchFilter(trigger.dataset.searchName);
  });

  // Back-to-top button: show after the user has scrolled past one viewport,
  // and on click scroll smoothly to the top.
  const $backToTop = document.getElementById("back-to-top");
  const updateBackToTop = () => {
    const showFrom = window.innerHeight;  // one screen down
    $backToTop.hidden = window.scrollY < showFrom;
  };
  /* Listen with passive:true since we never call preventDefault here; this
     lets the browser keep scrolling smooth on mobile even while the handler
     runs. */
  window.addEventListener("scroll", updateBackToTop, { passive: true });
  updateBackToTop();
  $backToTop.addEventListener("click", () => {
    window.scrollTo({ top: 0, behavior: "smooth" });
  });

  // Per-card toggle: delegated click on the list.
  $list.addEventListener("click", (event) => {
    const button = event.target.closest(".card-toggle");
    if (!button) return;
    const card = button.closest(".card");
    if (!card) return;
    const id = Number(card.dataset.bggId);
    const expanded = !card.classList.contains("card-expanded");
    setCardExpanded(card, expanded);
    if (expanded) state.expanded.add(id); else state.expanded.delete(id);
    syncToggleAllLabel();
  });

  // Global expand-all / collapse-all button.
  document.getElementById("toggle-all").addEventListener("click", () => {
    const cards = $list.querySelectorAll(".card");
    const allExpanded = Array.from(cards)
        .every(c => c.classList.contains("card-expanded"));
    const target = !allExpanded;
    cards.forEach(c => {
      setCardExpanded(c, target);
      const id = Number(c.dataset.bggId);
      if (target) state.expanded.add(id); else state.expanded.delete(id);
    });
    syncToggleAllLabel();
  });
}

/* --- Read current filter / sort state ----------------------------------- */

function readFilters() {
  return {
    search: document.getElementById("search-input").value.trim(),
    playersSource: document.getElementById("players-source").value,
    playersChecked: Array.from(
      document.querySelectorAll("input[name='players']:checked")
    ).map(cb => cb.value),
    durationMin: parseIntOrNull(document.getElementById("duration-min").value),
    durationMax: parseIntOrNull(document.getElementById("duration-max").value),
    ageSource: document.getElementById("age-source").value,
    ageSuitable: parseIntOrNull(document.getElementById("age-suitable").value),
    ageMin: parseIntOrNull(document.getElementById("age-min").value),
  };
}

function readSort() {
  return document.getElementById("sort-select").value;
}

function parseIntOrNull(s) {
  if (s === "" || s == null) return null;
  const n = Number(s);
  return Number.isFinite(n) ? n : null;
}

function isFilterActive(f) {
  return Boolean(
    f.search
    || f.playersChecked.length
    || f.durationMin != null || f.durationMax != null
    || f.ageSuitable != null || f.ageMin != null
  );
  /* Note: changing the source selects (players/age) without any value
     attached has no effect, so we don't count them as "active". */
}

/* --- Filtering ----------------------------------------------------------- */

function normalizeQuery(s) {
  /* Same transformation as the Python side applied to search_blob:
     NFKD-decompose, drop combining marks, lowercase, collapse whitespace. */
  return s.normalize("NFKD")
    .replace(/[\u0300-\u036f]/g, "")
    .toLowerCase()
    .replace(/\s+/g, " ")
    .trim();
}

function matchesSearch(game, query) {
  if (!query) return true;
  const blob = game.search_blob || "";
  /* Split query into tokens; each token must appear somewhere in the blob. */
  const tokens = normalizeQuery(query).split(" ").filter(Boolean);
  for (const t of tokens) {
    if (!blob.includes(t)) return false;
  }
  return true;
}

function matchesPlayers(game, source, checked) {
  if (!checked.length) return true;
  const range = game.players && game.players[source];
  if (!range) return false;
  /* For each checked value, the game must support that number of players. */
  for (const v of checked) {
    if (v === "7+") {
      // "7+" means: the game can be played at 7 or more.
      if (range.max == null || range.max < 7) return false;
    } else {
      const n = Number(v);
      if (source === "official") {
        // Official has no `values` list; use the bounded range.
        if (range.min == null || range.max == null) return false;
        if (n < range.min || n > range.max) return false;
      } else {
        // Community / best have a precise `values` list.
        if (!range.values || !range.values.includes(n)) return false;
      }
    }
  }
  return true;
}

function matchesDuration(game, minBound, maxBound) {
  if (minBound == null && maxBound == null) return true;
  const range = game.playing_time;
  if (!range || range.min == null || range.max == null) {
    // No duration info: only match if user set no bound.
    return false;
  }
  /* Interval inclusion: the game's [min, max] must fit inside [minBound, maxBound]
     where each bound is open (no constraint) when null. */
  if (minBound != null && range.min < minBound) return false;
  if (maxBound != null && range.max > maxBound) return false;
  return true;
}

function matchesAge(game, source, suitable, minimum) {
  if (suitable == null && minimum == null) return true;
  const value = game.age && game.age[source];
  if (value == null) return false;  // missing age (rare) -> excluded
  if (suitable != null && value > suitable) return false;  // "Age suitable for X" means age <= X
  if (minimum  != null && value < minimum)  return false;  // "Min age >= Y" means age >= Y
  return true;
}

function filterGames(games, f) {
  return games.filter(g =>
    matchesSearch(g, f.search) &&
    matchesPlayers(g, f.playersSource, f.playersChecked) &&
    matchesDuration(g, f.durationMin, f.durationMax) &&
    matchesAge(g, f.ageSource, f.ageSuitable, f.ageMin)
  );
}

/* --- Sorting ------------------------------------------------------------- */

const SORT_KEYS = {
  "my_rating":      g => g.my_rating,
  "title":          g => (g.title || ""),
  "year":           g => g.year,
  "weight":         g => g.weight,
  "age_official":   g => g.age && g.age.official,
  "age_community":  g => g.age && g.age.community,
};

/* Compare two strings the way humans expect: accented letters sort with
   their unaccented counterparts ("Échecs" between "Echo" and "Edit", not
   after "Zebra"), case-insensitive. Locale "fr" is fine for our content. */
const STRING_COLLATOR = new Intl.Collator("fr", {
  sensitivity: "base",
  numeric: true,
});

function sortGames(games, sortValue) {
  /* sortValue is e.g. "my_rating-desc" or "title-asc". */
  const [key, dir] = sortValue.split("-");
  const getter = SORT_KEYS[key] || SORT_KEYS["my_rating"];
  const sign = dir === "desc" ? -1 : 1;
  const isStringKey = (key === "title");

  /* Stable sort, with null/undefined values always sent to the end regardless
     of direction (so they don't pollute the top of the list when sorting by
     a sparse field). Stable tiebreak is by title (alphabetical) since the
     collection has no rank. */
  return [...games].sort((a, b) => {
    const va = getter(a);
    const vb = getter(b);
    const aMissing = (va == null);
    const bMissing = (vb == null);
    const ta = (a.title || "");
    const tb = (b.title || "");
    if (aMissing && bMissing) return STRING_COLLATOR.compare(ta, tb);
    if (aMissing) return 1;
    if (bMissing) return -1;
    let cmp;
    if (isStringKey) {
      cmp = STRING_COLLATOR.compare(va, vb);
    } else {
      cmp = (va < vb) ? -1 : (va > vb ? 1 : 0);
    }
    if (cmp !== 0) return cmp * sign;
    return STRING_COLLATOR.compare(ta, tb);
  });
}

/* --- Apply --------------------------------------------------------------- */

function applyFiltersAndSort() {
  const f = readFilters();
  const filtered = filterGames(state.allGames, f);
  const sorted   = sortGames(filtered, readSort());
  renderList(sorted);
  updateFooter(sorted.length, isFilterActive(f));
  syncToggleAllLabel();
}

function renderList(games) {
  if (games.length === 0) {
    $list.innerHTML = `
      <p class="status">No games match the current filters.</p>
    `;
    return;
  }
  $list.innerHTML = games.map((g, i) => renderCard(g, i)).join("");
  /* Reapply the expanded state from our Set, so toggling filters doesn't
     collapse the cards the user opened. */
  for (const id of state.expanded) {
    const card = $list.querySelector(`.card[data-bgg-id="${id}"]`);
    if (card) setCardExpanded(card, true);
  }
}

function updateFooter(nResults, active) {
  const total = state.allGames.length;
  const $count = document.getElementById("result-count");
  if (nResults === total) {
    $count.textContent = `${total} games`;
  } else {
    $count.textContent = `${nResults} of ${total} games`;
  }
  document.getElementById("reset-filters").disabled = !active;
}

function resetFilters() {
  document.getElementById("search-input").value = "";
  document.querySelectorAll("input[name='players']").forEach(cb => cb.checked = false);
  document.getElementById("duration-min").value = "";
  document.getElementById("duration-max").value = "";
  document.getElementById("age-suitable").value = "";
  document.getElementById("age-min").value = "";
  /* Source selects (official/community/best) are NOT reset — they're a
     persistent preference, not a filter value. */
  applyFiltersAndSort();
}

/* --- Filters panel open/close ------------------------------------------- */

function isFiltersPanelOpen() {
  return !document.getElementById("filters-body").hidden;
}

function setFiltersPanelOpen(open) {
  const header = document.getElementById("filters-toggle");
  const body = document.getElementById("filters-body");
  body.hidden = !open;
  header.setAttribute("aria-expanded", open ? "true" : "false");
  const title = header.querySelector(".filters-title");
  title.textContent = open ? "Filters \u25B4" : "Filters \u25BE";
}

/* --- Trigger a search filter from a click (e.g. magnifier icon) --------- */

function setSearchFilter(name) {
  /* Used by the magnifier icons next to people / classification entries.
     We replace any existing filter state with just this search, expand the
     panel so the user sees the active filter, and scroll back to the top
     so they can see the new (re-ordered) results from the start. */
  resetFiltersToSearch(name);
  setFiltersPanelOpen(true);
  window.scrollTo({ top: 0, behavior: "smooth" });
}

function resetFiltersToSearch(name) {
  document.getElementById("search-input").value = name;
  document.querySelectorAll("input[name='players']").forEach(cb => cb.checked = false);
  document.getElementById("duration-min").value = "";
  document.getElementById("duration-max").value = "";
  document.getElementById("age-suitable").value = "";
  document.getElementById("age-min").value = "";
  applyFiltersAndSort();
}

/* --- Card rendering ------------------------------------------------------ */

/* Number of cards considered "above the fold" — their images load eagerly
   (no lazy attribute) and the very first one gets fetchpriority=high. The
   rest of the 250 stays lazy and only loads as the user scrolls. */
const EAGER_CARD_COUNT = 4;

function renderCard(g, index = 0) {
  /* loading="lazy" is what we want for the long tail (240+ images that may
     never be scrolled to), BUT the first few must NOT be lazy because they
     ARE the LCP. The browser otherwise defers their fetch and LCP drags. */
  const loadingAttr = index < EAGER_CARD_COUNT ? "" : `loading="lazy"`;
  /* fetchpriority=high on the very first image hints to the browser:
     prioritize this one above other resources. Makes a measurable LCP gain
     on slow networks. */
  const priorityAttr = index === 0 ? `fetchpriority="high"` : "";
  return `
    <article class="card" data-bgg-id="${g.bgg_id}">
      <a class="card-image-link" href="${escapeAttr(g.bgg_url)}" target="_blank" rel="noopener"
         style="background-image: url('${escapeAttr(g.image_url)}');">
        <img class="card-image" src="${escapeAttr(g.image_url)}"
             alt="${escapeAttr(g.title)} cover"
             ${loadingAttr} ${priorityAttr} decoding="async">
      </a>
      <div class="card-body">
        <h2 class="card-title">
          <a href="${escapeAttr(g.bgg_url)}" target="_blank" rel="noopener">${escapeHtml(g.title)}</a>
          ${g.year ? `<span class="card-year">(${g.year})</span>` : ""}
        </h2>
        <div class="card-meta">${renderMetaLine(g)}</div>
        <button type="button" class="card-toggle" aria-expanded="false">
          Show more ▾
        </button>
        ${renderExtras(g)}
      </div>
    </article>
  `;
}

function renderMetaLine(g) {
  const parts = [];
  const players = formatPlayers(g.players && g.players.official);
  if (players) parts.push(players);

  const playtime = formatPlaytime(g.playing_time);
  if (playtime) parts.push(playtime);

  const age = g.age && g.age.official;
  if (age) parts.push(`Age ${age}+`);

  return parts.join(`<span class="meta-sep">·</span>`);
}

/* --- Extras (expanded view) --------------------------------------------- */

function renderExtras(g) {
  /* "Match" row (when search-active) and "My rating" are highlighted with
     their own classes; everything else is a plain row. */
  const rows = [
    { label: "Match",                     value: formatMatchRow(g),               cls: "match-row" },
    { label: "My rating",                 value: formatMyRatingRow(g),            cls: "rating-row" },
    { label: "Expansions I own",          value: formatExpansionsRow(g) },
    { label: "Players (community)",       value: formatPlayersCommunityRow(g) },
    { label: "Age (community)",           value: formatAgeCommunityRow(g) },
    { label: weightLabel(),               value: formatWeightRow(g) },
    { label: designerLabel(g),            value: formatPeople(g.designers) },
    { label: "Solo designer",             value: formatPeople(g.solo_designers) },
    { label: artistLabel(g),              value: formatPeople(g.artists) },
  ];
  const html = rows
    .filter(r => r.value)
    .map(r => {
      const c = r.cls ? ` class="${r.cls}"` : "";
      return `<dt${c}>${r.label}</dt><dd${c}>${r.value}</dd>`;
    })
    .join("");
  return `<dl class="card-extras">${html}</dl>`;
}

function formatMyRatingRow(g) {
  if (typeof g.my_rating !== "number") return null;
  /* BGG ratings are on a 10 scale; show one decimal if non-integer. */
  const r = Number.isInteger(g.my_rating) ? g.my_rating : g.my_rating.toFixed(1);
  return `${r} / 10`;
}

function formatExpansionsRow(g) {
  if (!g.expansions || !g.expansions.length) return null;
  /* One per line — the list reads more clearly than a continuous chain. */
  return g.expansions
    .map(e => `<a href="${escapeAttr(e.bgg_url)}" target="_blank" rel="noopener">${escapeHtml(e.title)}</a>`)
    .join("<br>");
}

/* --- Match disclosure --------------------------------------------------- */

/* When the user types a search query, some games match for reasons that
   aren't visible on the card (a publisher, a mechanic, a family...). We
   list those matches in a "Match" row in the expanded view, so the reader
   can see *why* a given game showed up.

   Visible fields (title, year, designers, artists, solo_designers) are
   excluded — the reader can already see those. Only the hidden fields
   (publishers, mechanics, categories, families) are reported here. */

const MATCH_FIELD_LABELS = {
  publishers: { single: "Publisher", plural: "Publishers" },
  mechanics:  { single: "Mechanic",  plural: "Mechanics"  },
  categories: { single: "Category",  plural: "Categories" },
  families:   { single: "Family",    plural: "Families"   },
};

function findHiddenMatches(g, query) {
  /* Returns { fieldName: [{name, id, type}, ...], ... } restricted to fields
     whose entries contain at least one of the search tokens (token-AND
     across the whole query is enforced at filter time; here we just need
     to know which fields hit). Returns null if no hidden matches. */
  const tokens = normalizeQuery(query).split(" ").filter(Boolean);
  if (!tokens.length || !g.search_index) return null;

  const result = {};
  for (const field of Object.keys(MATCH_FIELD_LABELS)) {
    const entries = g.search_index[field] || [];
    const hits = entries.filter(e => {
      if (!e || !e.name) return false;
      const n = normalizeQuery(e.name);
      return tokens.some(t => n.includes(t));
    });
    if (hits.length) result[field] = hits;
  }
  return Object.keys(result).length ? result : null;
}

function formatMatchRow(g) {
  const query = document.getElementById("search-input").value.trim();
  if (!query) return null;
  const matches = findHiddenMatches(g, query);
  if (!matches) return null;

  const lines = [];
  for (const [field, hits] of Object.entries(matches)) {
    const labels = MATCH_FIELD_LABELS[field];
    const label = hits.length > 1 ? labels.plural : labels.single;
    const linked = hits.map(h => entityLink(h));
    lines.push(`${label}: ${linked.join(", ")}`);
  }
  return lines.join("<br>");
}

function entityLink(entity) {
  /* Render one entity (person or classification) as:
       <a>name</a> <button class="search-by" data-search-name="name">🔍</button>
     The name links to its BGG page (when we have id+type). The magnifier
     button triggers an in-page text filter on that name.
     Used for designers/artists in extras AND for publishers/mechanics/etc.
     in the Match disclosure. */
  if (!entity || !entity.name) return "";
  const name = entity.name;
  let head;
  if (entity.id && entity.type) {
    const url = `https://boardgamegeek.com/${entity.type}/${entity.id}`;
    head = `<a href="${escapeAttr(url)}" target="_blank" rel="noopener">${escapeHtml(name)}</a>`;
  } else {
    head = escapeHtml(name);
  }
  const search = `<button type="button" class="search-by" ` +
                 `data-search-name="${escapeAttr(name)}" ` +
                 `aria-label="Show games with ${escapeAttr(name)}" ` +
                 `title="Show games with ${escapeAttr(name)}">\u{1F50D}</button>`;
  return `<span class="entity">${head}${search}</span>`;
}

function formatPlayersCommunityRow(g) {
  const community = g.players && g.players.community;
  const best = g.players && g.players.best;
  const parts = [];
  const c = formatPlayers(community);
  if (c) parts.push(c);
  if (best && best.values && best.values.length) {
    const r = formatPlayers(best);
    if (r) parts.push(`best ${r.replace(/ players?$/, "")}`);
  }
  if (!parts.length) return null;
  const s = parts.join(", ");
  return s.charAt(0).toUpperCase() + s.slice(1);
}

function formatAgeCommunityRow(g) {
  const a = g.age && g.age.community;
  return a ? `${a}+` : null;
}

function formatWeightRow(g) {
  return typeof g.weight === "number" ? `${g.weight.toFixed(2)} / 5` : null;
}

function weightLabel() {
  return `Complexity (<a href="https://boardgamegeek.com/wiki/page/Weight" ` +
         `target="_blank" rel="noopener">BGG weight</a>)`;
}

function designerLabel(g) {
  return (g.designers && g.designers.length > 1) ? "Designers" : "Designer";
}

function artistLabel(g) {
  return (g.artists && g.artists.length > 1) ? "Artists" : "Artist";
}

function formatPeople(list) {
  if (!list || !list.length) return null;
  /* Each person becomes [BGG link][magnifier search button]. The last name's
     internal spaces are non-breaking so a first-name-only orphan can't end up
     on its own last line; intermediate names keep regular spaces so a long
     list can still wrap naturally between names. */
  const html = list.map(entityLink);
  /* Re-process the last rendered chunk: the "head" portion (the <a>...</a>
     or escaped text) should have its inner spaces become non-breaking. We
     re-render the last entity with that adjustment for tidy line wrapping. */
  const lastIdx = list.length - 1;
  html[lastIdx] = entityLinkLastInList(list[lastIdx]);
  return html.join(", ");
}

function entityLinkLastInList(entity) {
  /* Same as entityLink, but the visible name uses non-breaking spaces so it
     stays solidary on the last line of a wrapped list. */
  if (!entity || !entity.name) return "";
  const nameDisplay = entity.name.replaceAll(" ", "\u00A0");
  let head;
  if (entity.id && entity.type) {
    const url = `https://boardgamegeek.com/${entity.type}/${entity.id}`;
    head = `<a href="${escapeAttr(url)}" target="_blank" rel="noopener">${escapeHtml(nameDisplay)}</a>`;
  } else {
    head = escapeHtml(nameDisplay);
  }
  const search = `<button type="button" class="search-by" ` +
                 `data-search-name="${escapeAttr(entity.name)}" ` +
                 `aria-label="Show games with ${escapeAttr(entity.name)}" ` +
                 `title="Show games with ${escapeAttr(entity.name)}">\u{1F50D}</button>`;
  return `<span class="entity">${head}${search}</span>`;
}

/* --- Players / playtime formatting -------------------------------------- */

function formatPlayers(range) {
  if (!range) return null;
  /* When build_games.py detected a "+" in the source (e.g. "Community: 3-5+"),
     it sets a `display` string we should show verbatim. The numeric min/max
     still drive the filters. */
  if (range.display) return `${range.display} players`;
  const { min, max } = range;
  if (min == null && max == null) return null;
  if (min === max || max == null) return `${min} player${min === 1 ? "" : "s"}`;
  if (min == null) return `up to ${max} players`;
  return `${min}\u2013${max} players`;
}

function formatPlaytime(range) {
  if (!range) return null;
  const { min, max } = range;
  if (min == null && max == null) return null;
  if (min === max || max == null) return `${min} min`;
  if (min == null) return `up to ${max} min`;
  return `${min}\u2013${max} min`;
}

/* --- Expand/collapse helpers -------------------------------------------- */

function setCardExpanded(card, expanded) {
  card.classList.toggle("card-expanded", expanded);
  const button = card.querySelector(".card-toggle");
  if (button) {
    button.textContent = expanded ? "Show less \u25B4" : "Show more \u25BE";
    button.setAttribute("aria-expanded", expanded ? "true" : "false");
  }
}

function syncToggleAllLabel() {
  const $toggleAll = document.getElementById("toggle-all");
  if (!$toggleAll) return;
  const cards = $list.querySelectorAll(".card");
  if (cards.length === 0) {
    $toggleAll.textContent = "Expand all \u25BE";
    return;
  }
  const allExpanded = Array.from(cards)
      .every(c => c.classList.contains("card-expanded"));
  $toggleAll.textContent = allExpanded ? "Collapse all \u25B4" : "Expand all \u25BE";
}

/* --- HTML escaping ------------------------------------------------------- */

function escapeHtml(s) {
  if (s == null) return "";
  return String(s)
    .replaceAll("&", "&amp;")
    .replaceAll("<", "&lt;")
    .replaceAll(">", "&gt;")
    .replaceAll('"', "&quot;")
    .replaceAll("'", "&#39;");
}

function escapeAttr(s) {
  return escapeHtml(s);
}

main();