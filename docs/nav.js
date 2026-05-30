/* Shared navigation bar, used by every page (index, credits, about).

   Renders a single line that's injected into the page's `#site-subtitle`:
     <edition> · Games · Credits · BGG geeklist · About

   The page passes its own identity (one of "games" / "credits" / "about"),
   and the active link is rendered as plain italic text (not a link). The
   "BGG geeklist" link is only included if current_geeklist.json could be
   loaded — otherwise it's silently omitted.

   Usage:
     await renderNav({ edition: 2025, active: "games" });
*/

/* Cache the geeklist info across calls (the page might call renderNav
   more than once, e.g. on hash change in the future). */
let _geeklistPromise = null;

function _loadCurrentGeeklist() {
  if (_geeklistPromise === null) {
    _geeklistPromise = fetch("current_geeklist.json")
      .then(r => r.ok ? r.json() : null)
      .catch(() => null);
  }
  return _geeklistPromise;
}

/* Render the nav line into #site-subtitle.
   `opts`: { edition: number, active: "games" | "credits" | "about" } */
async function renderNav(opts) {
  const $sub = document.getElementById("site-subtitle");
  if (!$sub) return;

  const geeklist = await _loadCurrentGeeklist();

  const parts = [];
  parts.push(_link("Games",   "index.html",   opts.active === "games"));
  parts.push(_link("Credits", "credits.html", opts.active === "credits"));
  parts.push(_link("About",   "about.html",   opts.active === "about"));
  if (geeklist && geeklist.geeklist_url) {
    /* External link to BGG: distinguished from in-site links with a small
       arrow indicator and target=_blank. Placed last because it leaves the
       site. The arrow is part of the link text (with a non-breaking space)
       so the underline is continuous. */
    parts.push(
      `<a class="subtitle-link subtitle-external" ` +
      `href="${escapeAttr(geeklist.geeklist_url)}" ` +
      `target="_blank" rel="noopener">BGG geeklist\u00A0\u2197</a>`
    );
  }

  $sub.innerHTML = parts.join(` <span class="subtitle-sep">\u00B7</span> `);
}

function _link(label, href, isActive) {
  if (isActive) {
    return `<span class="subtitle-current">${escapeHtml(label)}</span>`;
  }
  return `<a class="subtitle-link" href="${escapeAttr(href)}">${escapeHtml(label)}</a>`;
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