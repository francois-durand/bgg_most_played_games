/* About page: minimal client.
   We just need the current edition number to render the nav. We get it from
   web_data.json (which is the main page's data and always reflects the
   current edition). */

async function main() {
  let edition = null;
  try {
    const response = await fetch("web_data.json");
    if (response.ok) {
      const payload = await response.json();
      edition = payload.edition;
    }
  } catch (err) {
    /* If web_data.json isn't there for some reason, we still render the nav
       without an edition number — better than nothing. */
  }
  renderNav({ edition, active: "about" });

  /* Fill the dynamic edition placeholders in the article body. We do this
     after the fetch since the value depends on the current data. */
  if (edition != null) {
    const $y1 = document.getElementById("about-edition-year");
    const $y2 = document.getElementById("about-edition-year2");
    if ($y1) $y1.textContent = edition;
    if ($y2) $y2.textContent = edition;
  }

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

main();