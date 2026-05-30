/* Most Played Games — single-page client.

   On load, fetches docs/web_data.json (rank/games merged by build_web_data.py),
   then renders the list of cards. The UI supports:
     - text search (matches on the precomputed search_blob)
     - players checkboxes (1, 2, 3, ..., 7+) with AND semantics
     - duration min/max (interval inclusion)
     - age suitable-for / min-age-at-least (with official/community source)
     - sort by rank/title/year/weight/age (asc or desc)
     - per-card "Show more" toggle to reveal details
     - "Expand all" / "Collapse all" global toggle

   Filtering and sorting are pure client-side over the in-memory game list.
   The expanded state of cards is preserved across re-renders via a Set of
   bgg_ids.
*/

const DATA_URL = "web_data.json";

const $list   = document.getElementById("game-list");
const $status = document.getElementById("status");
const $sub    = document.getElementById("site-subtitle");

const state = {
  allGames: [],        // populated once from web_data.json
  expanded: new Set(), // bgg_ids of cards currently expanded
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
  $sub.textContent = `${payload.edition} edition`;
  const topN = payload.top_n || state.allGames.length;
  document.getElementById("intro-top-n").textContent = topN;
  $status.remove();

  bindControls();
  applyFiltersAndSort();
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
    const header = document.getElementById("filters-toggle");
    const body = document.getElementById("filters-body");
    const isOpen = !body.hidden;
    body.hidden = isOpen;
    header.setAttribute("aria-expanded", isOpen ? "false" : "true");
    /* Update the chevron in the title. */
    const title = header.querySelector(".filters-title");
    title.textContent = isOpen ? "Filters \u25BE" : "Filters \u25B4";
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
  "rank":           g => g.rank,
  /* For delta sorting, treat "NEW" as +Infinity: a brand-new entry to the
     published list is conceptually the biggest possible climb. So:
       delta-desc (biggest climbers first) → NEWs come first
       delta-asc  (biggest drops first)    → NEWs come last
     null rank_delta (e.g. missing) falls under the "missing -> end" rule
     handled in sortGames below. */
  "delta":          g => g.rank_delta === "NEW" ? Infinity : g.rank_delta,
  "title":          g => (g.title || "").toLowerCase(),
  "year":           g => g.year,
  "weight":         g => g.weight,
  "age_official":   g => g.age && g.age.official,
  "age_community":  g => g.age && g.age.community,
};

function sortGames(games, sortValue) {
  /* sortValue is e.g. "rank-asc" or "title-desc". */
  const [key, dir] = sortValue.split("-");
  const getter = SORT_KEYS[key] || SORT_KEYS["rank"];
  const sign = dir === "desc" ? -1 : 1;

  /* Stable sort, with null/undefined values always sent to the end regardless
     of direction (so they don't pollute the top of the list when sorting by
     a sparse field like weight or age_official). */
  return [...games].sort((a, b) => {
    const va = getter(a);
    const vb = getter(b);
    const aMissing = (va == null);
    const bMissing = (vb == null);
    if (aMissing && bMissing) return a.rank - b.rank;  // stable fallback
    if (aMissing) return 1;
    if (bMissing) return -1;
    if (va < vb) return -1 * sign;
    if (va > vb) return  1 * sign;
    return a.rank - b.rank;  // stable tiebreak
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
  $list.innerHTML = games.map(renderCard).join("");
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

/* --- Card rendering ------------------------------------------------------ */

function renderCard(g) {
  return `
    <article class="card" data-bgg-id="${g.bgg_id}">
      <a class="card-image-link" href="${escapeAttr(g.bgg_url)}" target="_blank" rel="noopener"
         style="background-image: url('${escapeAttr(g.image_url)}');">
        <img class="card-image" src="${escapeAttr(g.image_url)}"
             alt="${escapeAttr(g.title)} cover"
             loading="lazy" decoding="async">
      </a>
      <div class="card-body">
        <div class="card-rank-line">
          <span class="card-rank">#${g.rank}</span>
          ${renderDelta(g.rank_delta)}
        </div>
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

function renderDelta(delta) {
  if (delta === "NEW") {
    return `<span class="delta delta-new">new</span>`;
  }
  if (typeof delta !== "number") {
    return "";
  }
  if (delta > 0) {
    return `<span class="delta delta-up">↑${delta}</span>`;
  }
  if (delta < 0) {
    return `<span class="delta delta-down">↓${-delta}</span>`;
  }
  return `<span class="delta delta-zero">=</span>`;
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
  /* The "match" row gets a dedicated CSS class so it can be visually
     distinguished. All other rows render with no class. */
  const rows = [
    { label: "Match",                     value: formatMatchRow(g),               cls: "match-row" },
    { label: "Score",                     value: formatScoreRow(g) },
    { label: "History",                   value: formatHistoryRow(g) },
    { label: "Status",                    value: formatStatusRow(g) },
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

function formatScoreRow(g) {
  if (typeof g.points !== "number") return null;
  return `${g.points.toFixed(1)} points`;
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
    const linked = hits.map(h => bggLink(h));
    lines.push(`${label}: ${linked.join(", ")}`);
  }
  return lines.join("<br>");
}

function bggLink(entity) {
  /* Build a link to the BGG entity page from its {name, id, type}.
     The 'type' field is BGG's slug (boardgamepublisher, boardgamemechanic,
     boardgamecategory, boardgamefamily). */
  if (!entity || !entity.id || !entity.type) {
    return escapeHtml(entity && entity.name || "");
  }
  const url = `https://boardgamegeek.com/${entity.type}/${entity.id}`;
  return `<a href="${escapeAttr(url)}" target="_blank" rel="noopener">${escapeHtml(entity.name)}</a>`;
}

function formatHistoryRow(g) {
  const parts = [];
  if (g.months_in_top_100)
    parts.push(`${g.months_in_top_100} months in BGG's monthly top 100 ` +
               `by distinct players`);
  if (g.months_in_top_10)
    parts.push(`${g.months_in_top_10} months in BGG's monthly top 10 ` +
               `by distinct players`);
  if (g.peak_position)
    parts.push(`Peak #${g.peak_position} in BGG's monthly top ` +
               `by distinct players`);
  return parts.length ? parts.join("<br>") : null;
}

function formatStatusRow(g) {
  if (g.current_position_in_top_100 != null) {
    return `Currently #${g.current_position_in_top_100} in BGG's monthly ` +
           `top 100 by distinct players`;
  }
  if (g.months_since_leaving_top_100 != null) {
    const n = g.months_since_leaving_top_100;
    return `Out of BGG's monthly top 100 by distinct players for ` +
           `${n}\u00A0month${n === 1 ? "" : "s"}`;
  }
  return null;
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
  return `<a href="https://boardgamegeek.com/wiki/page/Weight" ` +
         `target="_blank" rel="noopener">Weight</a> (\u201Ccomplexity\u201D)`;
}

function designerLabel(g) {
  return (g.designers && g.designers.length > 1) ? "Designers" : "Designer";
}

function artistLabel(g) {
  return (g.artists && g.artists.length > 1) ? "Artists" : "Artist";
}

function formatPeople(list) {
  if (!list || !list.length) return null;
  const names = list.map(p => escapeHtml(p.name));
  const last = names.length - 1;
  names[last] = names[last].replaceAll(" ", "\u00A0");
  return names.join(", ");
}

/* --- Players / playtime formatting -------------------------------------- */

function formatPlayers(range) {
  if (!range) return null;
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