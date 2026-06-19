// list.js — online deals + failed-geocode physical deals render as cards.
// Pure helper first; rendering wired in after the node assertion passes.

// belongsInList(deal) -> bool. A deal belongs in the list view if it is online,
// OR if it is a physical deal we could not geocode (so it is never lost).
function belongsInList(deal) {
  return deal.placement === "online" || deal.geocode_status === "failed";
}

// renderList(deals, state, container) — DOM rendering, browser-only.
function renderList(deals, state, container) {
  const items = deals
    .filter(belongsInList)
    .filter((d) => window.matchesFilters(d, state));
  container.innerHTML = "";
  if (items.length === 0) {
    const empty = document.createElement("p");
    empty.className = "list-empty";
    empty.textContent = "No matching deals.";
    container.appendChild(empty);
    return;
  }
  for (const d of items) {
    const card = document.createElement("article");
    card.className = "deal-card" + (d.status === "stale" ? " stale" : "");
    const h = document.createElement("h3");
    h.textContent = d.title;
    const meta = document.createElement("p");
    meta.className = "deal-meta";
    meta.textContent = `${d.deal_type} · ${d.category} · ${d.status}`;
    const link = document.createElement("a");
    link.href = d.url;
    link.target = "_blank";
    link.rel = "noopener";
    link.textContent = "View deal";
    card.appendChild(h);
    card.appendChild(meta);
    card.appendChild(link);
    container.appendChild(card);
  }
}

if (typeof module !== "undefined" && module.exports) {
  module.exports = { belongsInList };
}
if (typeof window !== "undefined") {
  window.belongsInList = belongsInList;
  window.renderList = renderList;
}
