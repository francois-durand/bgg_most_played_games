/* Most Played Games — credits page.

   Loads credits_data.json and renders two tables: designers and artists,
   each restricted to people credited on at least two games. Each row shows
   the count, a BGG-linked name with a magnifier (filter on the main list),
   and the games the person is credited on (BGG-linked + magnifier each).

   A click on a magnifier navigates back to the main page with a hash like
       index.html#search=...
   which the main page picks up to apply the filter.
*/

const DATA_URL = "credits_data.json";

const $status = document.getElementById("status");
const $sub    = document.getElementById("site-subtitle");

async function main() {
  let payload;
  try {
    const response = await fetch(DATA_URL);
    if (!response.ok) throw new Error("HTTP " + response.status);
    payload = await response.json();
  } catch (err) {
    $status.textContent = "Could not load credits data: " + err.message;
    return;
  }

  $sub.textContent = `${payload.edition} edition`;
  $status.remove();

  renderTable(document.querySelector("#designers-table tbody"), payload.designers);
  renderTable(document.querySelector("#artists-table tbody"), payload.artists);

  // Back-to-top button.
  const $backToTop = document.getElementById("back-to-top");
  const updateBackToTop = () => {
    $backToTop.hidden = window.scrollY < window.innerHeight;
  };
  window.addEventListener("scroll", updateBackToTop, { passive: true });
  updateBackToTop();
  $backToTop.addEventListener("click", () => {
    window.scrollTo({ top: 0, behavior: "smooth" });
  });
}

function renderTable($tbody, people) {
  $tbody.innerHTML = people.map(renderRow).join("");
}

function renderRow(person) {
  const gameLinks = person.games.map(renderGame).join(`<span class="meta-sep">·</span>`);
  return `
    <tr>
      <td class="credits-count">${person.count}<span class="credits-count-label"> games</span></td>
      <td class="credits-name">${entityLink(person)}</td>
      <td class="credits-games">${gameLinks}</td>
    </tr>
  `;
}

function renderGame(g) {
  /* Each game: title linked to BGG, magnifier filters the main list by that
     title (which on BGG groups the family: "7 Wonders" matches "7 Wonders",
     "7 Wonders Duel", "7 Wonders: Architects", etc.). */
  const bggUrl = `https://boardgamegeek.com/boardgame/${g.bgg_id}`;
  const head = `<a href="${escapeAttr(bggUrl)}" target="_blank" rel="noopener">${escapeHtml(g.title)}</a>`;
  const search = `<a href="index.html#search=${encodeURIComponent(g.title)}" ` +
                 `class="search-by" aria-label="Show '${escapeAttr(g.title)}' in the main list" ` +
                 `title="Show '${escapeAttr(g.title)}' in the main list">\u{1F50D}</a>`;
  return `<span class="entity">${head}${search}</span>`;
}

function entityLink(person) {
  /* Name: BGG link + magnifier filtering the main list by name.
     The magnifier is an <a href> pointing to index.html#search=..., so:
       - On the main page, the URL hash is read and the filter is applied.
       - It works as a normal link (right-click, open in tab, share). */
  const name = person.name;
  let head;
  if (person.bgg_id && person.type) {
    const url = `https://boardgamegeek.com/${person.type}/${person.bgg_id}`;
    head = `<a href="${escapeAttr(url)}" target="_blank" rel="noopener">${escapeHtml(name)}</a>`;
  } else {
    head = escapeHtml(name);
  }
  const search = `<a href="index.html#search=${encodeURIComponent(name)}" ` +
                 `class="search-by" aria-label="Show games with ${escapeAttr(name)}" ` +
                 `title="Show games with ${escapeAttr(name)}">\u{1F50D}</a>`;
  return `<span class="entity">${head}${search}</span>`;
}

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