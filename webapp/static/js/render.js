// Rendu : cartes d'embarquement (podium), tableau des départs, encarts.
import {
  barcode, fmtDay, fmtDuration, fmtFetched, fmtPrice, fmtShort, h, safeUrl, stopsLabel, timeOf,
} from "./dom.js";

const PLANE = () => {
  const svg = document.createElementNS("http://www.w3.org/2000/svg", "svg");
  svg.setAttribute("viewBox", "0 0 24 24");
  svg.setAttribute("class", "plane");
  svg.setAttribute("aria-hidden", "true");
  const path = document.createElementNS("http://www.w3.org/2000/svg", "path");
  path.setAttribute("fill", "currentColor");
  path.setAttribute("d", "M21 15.5v-2l-8-5V3.8a1.5 1.5 0 0 0-3 0V8.5l-8 5v2l8-2.5V18l-2 1.5V21l3.5-1 3.5 1v-1.5L13 18v-5z");
  svg.append(path);
  return svg;
};

const CATEGORIES = [
  { key: "cheapest", label: "Le moins cher", tilt: "-1.1deg", why: () => "Le prix le plus bas parmi les vols vérifiés." },
  { key: "best_balance", label: "Meilleur compromis", tilt: "0.5deg", why: (s) => `Meilleur équilibre prix, durée, escales et horaires (score ${s}/100).` },
  { key: "most_comfortable", label: "Le plus confortable", tilt: "-0.4deg", why: (s) => `Moins d'escales et de temps porte-à-porte pour un prix raisonnable (score ${s}/100).` },
];

function nextDay(offer) {
  const days = Math.round((new Date(offer.arrival_time.slice(0, 10)) - new Date(offer.departure_time.slice(0, 10))) / 86400000);
  return days > 0 ? ` +${days}` : "";
}

function passField(label, value) {
  return h("div", {}, h("dt", {}, label), h("dd", {}, value));
}

const score = (s) => Math.round(s);

function boardingPass(cat, entry, offer, ctx, index) {
  const url = safeUrl(offer.search_url);
  const stamp = !ctx.withinBudget ? "Hors budget" : offer.bag_warning ? "+ Bagage" : null;
  return h("article", { class: "pass", style: { "--tilt": cat.tilt, "--delay": `${index * 140}ms` }, "aria-label": cat.label },
    h("div", { class: "pass-main" },
      h("div", { class: "pass-band" }, h("span", {}, cat.label), h("span", { class: "tag" }, `Score ${score(entry.score)}`)),
      h("div", { class: "pass-route" },
        h("span", { class: "iata" }, offer.origin), PLANE(), h("span", { class: "iata" }, offer.destination)),
      h("div", { class: "pass-cities" }, h("span", {}, offer.origin_name), h("span", {}, ctx.destLabel || "")),
      h("dl", { class: "pass-grid" },
        passField("Aller", fmtDay(offer.outbound_date)),
        passField("Retour", fmtDay(offer.return_date)),
        passField("Départ", timeOf(offer.departure_time)),
        passField("Arrivée", `${timeOf(offer.arrival_time)}${nextDay(offer)}`),
        passField("Escales", stopsLabel(offer.stops)),
        passField("Durée vol", fmtDuration(offer.duration_min)),
        passField("Vol", offer.flight_numbers.join(" · ")),
        passField("Compagnie", [...new Set(offer.airlines)].join(", ")),
        passField("Accès aéroport", offer.access_min ? `~${fmtDuration(offer.access_min)}` : "Sur place"),
      ),
      h("p", { class: "pass-why" }, cat.why(score(entry.score)), offer.bag_warning ? ` ${offer.bag_warning}` : ""),
    ),
    h("div", { class: "pass-stub" },
      h("div", {},
        h("div", { class: "stub-label" }, "Prix A/R"),
        h("div", { class: "stub-price" }, fmtPrice(offer.price_eur)),
        h("div", { class: "stub-meta" }, "par adulte")),
      h("div", { class: "barcode", style: { backgroundImage: barcode(offer.id) }, "aria-hidden": "true" }),
      h("div", { class: "stub-meta" }, `Google Flights · ${fmtFetched(offer.fetched_at)}`),
      url ? h("a", { class: "stub-link", href: url, target: "_blank", rel: "noopener noreferrer" }, "Voir le vol") : null,
    ),
    stamp ? h("span", { class: "stamp", "aria-hidden": "true" }, stamp) : null,
  );
}

export function renderPodium(root, ranking, byId, ctx) {
  const cards = CATEGORIES.map((cat, i) => {
    const entry = ranking?.[cat.key];
    if (!entry || !byId.has(entry.id)) {
      return h("div", { class: "pass-empty" }, i === 0 ? "Aucun vol à afficher." : "Pas d'autre option distincte.");
    }
    return boardingPass(cat, entry, byId.get(entry.id), { ...ctx, withinBudget: ranking.within_budget }, i);
  });
  root.replaceChildren(...cards);
}

function remarks(offer, ctx) {
  const out = [];
  if (offer.id === ctx.cheapestId) out.push(h("span", { class: "remark remark-best" }, "Meilleur prix "));
  if (ctx.budget && offer.price_eur > ctx.budget * 1.1) out.push(h("span", { class: "remark remark-warn" }, "Hors budget "));
  if (offer.bag_warning) out.push(h("span", { class: "remark remark-warn" }, "+Bagage "));
  if (offer.access_min >= 120) out.push(h("span", { class: "remark t-muted" }, `Accès ~${fmtDuration(offer.access_min)}`));
  return out;
}

function detailRow(offer) {
  const url = safeUrl(offer.search_url);
  return h("tr", { class: "detail" },
    h("td", { colspan: "9" },
      h("div", {}, `${[...new Set(offer.airlines)].join(", ")} · ${offer.flight_numbers.join(" · ")} · arrivée ${offer.arrival_time}`),
      h("div", {}, `Porte-à-porte aller estimé : ${fmtDuration(offer.door_to_door_min)} (dont accès à ${offer.origin_name} ~${fmtDuration(offer.access_min)})`),
      offer.fare_notes.length ? h("ul", {}, offer.fare_notes.map((n) => h("li", {}, n))) : null,
      h("div", {}, `Source : ${offer.source} · données du ${fmtFetched(offer.fetched_at)} · `,
        url ? h("a", { href: url, target: "_blank", rel: "noopener noreferrer" }, "ouvrir la recherche Google Flights") : "lien indisponible"),
    ),
  );
}

export function renderRows(tbody, offers, ctx) {
  const rows = [];
  offers.forEach((o, i) => {
    rows.push(h("tr", {
      "data-id": o.id,
      class: ctx.openId === o.id ? "is-open" : null,
      style: { "--delay": `${Math.min(i, 20) * 35}ms` },
      tabindex: "0",
      "aria-expanded": String(ctx.openId === o.id),
    },
      h("td", { class: "t-amber" }, timeOf(o.departure_time)),
      h("td", {}, o.flight_numbers[0], h("span", { class: "t-muted" }, ` ${o.airlines[0]}`)),
      h("td", {}, o.origin),
      h("td", {}, o.destination),
      h("td", { class: "t-muted" }, `${fmtShort(o.outbound_date)} → ${fmtShort(o.return_date)}`),
      h("td", {}, o.stops === 0 ? "Direct" : String(o.stops)),
      h("td", {}, fmtDuration(o.duration_min)),
      h("td", { class: "num t-price" }, fmtPrice(o.price_eur)),
      h("td", {}, remarks(o, ctx)),
    ));
    if (ctx.openId === o.id) rows.push(detailRow(o));
  });
  tbody.replaceChildren(...rows);
}

const LEVELS = { high: ["élevé", "level-high"], low: ["bas", "level-low"], typical: ["habituel", "level-typical"] };

export function renderInsights(root, insights) {
  root.replaceChildren(...insights.map((pi) => {
    const [word, cls] = LEVELS[pi.price_level] || [pi.price_level || "?", ""];
    const range = pi.typical_price_range ? ` · habituel ${fmtPrice(pi.typical_price_range[0])}–${fmtPrice(pi.typical_price_range[1])}` : "";
    return h("div", { class: "insight" },
      `${fmtShort(pi.outbound_date)} → ${fmtShort(pi.return_date)} : Google juge ce prix `,
      h("strong", { class: cls }, word), range);
  }));
}

export function renderWarnings(root, warnings) {
  root.replaceChildren(...warnings.map((w) => h("li", {}, w)));
}

export function renderHints(section, list, hints) {
  section.hidden = hints.length === 0;
  list.replaceChildren(...hints.map((hint) => {
    const url = safeUrl(hint.link);
    return h("li", {},
      h("span", { class: "t-amber" }, fmtPrice(hint.price_eur)),
      h("span", {}, `${hint.origin} → ${hint.destination}`),
      h("span", { class: "t-muted" }, `${fmtShort(hint.outbound_date)} → ${fmtShort(hint.return_date)} · ${hint.airline} · ${stopsLabel(hint.stops)}`),
      url ? h("a", { href: url, target: "_blank", rel: "noopener noreferrer" }, "voir sur Aviasales") : null);
  }));
}

export function renderChecks(root, values, labelFor, name) {
  root.replaceChildren(...values.map((v) =>
    h("label", {}, h("input", { type: "checkbox", name, value: v, checked: true }), labelFor(v))));
}
