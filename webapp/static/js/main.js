import * as api from "./api.js";
import { debounce, fmtDuration, fmtPrice, h, hourOf } from "./dom.js";
import { flapTo } from "./flap.js";
import {
  renderChecks, renderHints, renderInsights, renderPodium, renderRows, renderWarnings,
} from "./render.js";

const $ = (id) => document.getElementById(id);
const EXAMPLES = [
  "naples fin oct 4-5j 150€",
  "lisbonne du 12 au 16 novembre",
  "porto le 14/11 flexible 3 jours direct",
  "toscane début décembre une semaine",
];
const MISSING_LABELS = {
  destination: "destination", destination_choice: "précise la destination", period: "période", stay: "durée du séjour",
};
const LOADING = ["Consultation du cache", "Choix des meilleures dates", "Vérification live", "Impression des cartes"];

const state = {
  config: null,
  destLabel: "",
  results: null,
  byId: new Map(),
  sort: "price",
  openId: null,
};

/* ---------- Tableau du haut ---------- */

function startClock() {
  const tick = () => {
    const now = new Date();
    const text = `${String(now.getHours()).padStart(2, "0")}:${String(now.getMinutes()).padStart(2, "0")}`;
    if ($("clock").getAttribute("aria-label") !== text) flapTo($("clock"), text, { spins: 3 });
  };
  tick();
  setInterval(tick, 10_000);
}

function showQuota(remaining) {
  flapTo($("quota"), `${remaining}/${state.config.quota_limit}`);
  $("cost-note").textContent = `Consomme jusqu'à 2 vérifications live (${remaining} restantes ce mois-ci). Filtrer ensuite est gratuit.`;
}

function message(text, { error = false } = {}) {
  const el = $("board-message");
  el.classList.toggle("is-error", error);
  el.textContent = text;
}

/* ---------- Fiche d'enregistrement ---------- */

function renderOrigins(origins) {
  $("f-origins").replaceChildren(...Object.entries(origins).map(([code, info]) =>
    h("label", { class: "origin-chip" },
      h("input", { type: "checkbox", name: "origin", value: code, checked: true }),
      h("span", {}, h("b", {}, code), info.name, h("small", {}, info.access_min ? `~${fmtDuration(info.access_min)}` : "sur place")))));
}

function setRadio(name, value) {
  const input = document.querySelector(`input[name="${name}"][value="${value}"]`);
  if (input) input.checked = true;
}

function setDestination(label, iata) {
  state.destLabel = label || "";
  $("f-dest-label").value = label || "Destination ?";
  $("f-dest-iata").value = (iata || []).join(",");
  $("dest-choices").hidden = true;
}

function fillCheckin(req) {
  setDestination(req.destination_label, req.destination_iata);
  if (req.destination_choices.length) {
    $("dest-choices").hidden = false;
    $("dest-choices").replaceChildren(...req.destination_choices.map((c) =>
      h("button", { type: "button", onclick: () => setDestination(c.label, c.iata) }, c.label)));
  }
  $("f-from").value = req.depart_from || "";
  $("f-to").value = req.depart_to || "";
  $("f-stay-min").value = req.stay_min ?? "";
  $("f-stay-max").value = req.stay_max ?? "";
  $("f-budget").value = req.budget_eur ?? "";
  $("f-adults").value = req.adults;
  setRadio("bag", req.bag);
  setRadio("stops", req.max_stops);
  $("f-from").min = $("f-to").min = state.config.today;
  $("checkin").hidden = false;
}

async function onCommand(event) {
  event.preventDefault();
  const text = $("command").value.trim();
  if (!text) return;
  try {
    const req = await api.parseCommand(text);
    fillCheckin(req);
    if (req.missing.length) {
      message(`Information manquante : ${req.missing.map((m) => MISSING_LABELS[m] || m).join(", ")}`);
      const focus = { destination: "f-dest-iata", period: "f-from", stay: "f-stay-min" }[req.missing[0]];
      if (focus) $(focus).focus();
    } else {
      message("Fiche prête. Vérifie et embarque.");
      $("btn-search").focus();
    }
  } catch (err) {
    message(err.message, { error: true });
  }
}

function readCheckin() {
  const num = (id) => ($(id).value === "" ? null : Number($(id).value));
  const iata = $("f-dest-iata").value.toUpperCase().split(",").map((s) => s.trim()).filter(Boolean);
  const origins = [...document.querySelectorAll('input[name="origin"]:checked')].map((i) => i.value);
  const errors = [];
  if (!iata.length || iata.some((c) => !/^[A-Z]{3}$/.test(c))) errors.push("code(s) IATA de destination");
  if (!$("f-from").value || !$("f-to").value) errors.push("période de départ");
  if (!num("f-stay-min") || !num("f-stay-max")) errors.push("durée du séjour");
  if (!origins.length) errors.push("au moins un aéroport de départ");
  if (errors.length) throw new Error(`À compléter : ${errors.join(", ")}`);
  const stayMin = num("f-stay-min");
  const stayMax = num("f-stay-max");
  return {
    destination_iata: iata,
    origins,
    depart_from: $("f-from").value,
    depart_to: $("f-to").value < $("f-from").value ? $("f-from").value : $("f-to").value,
    stay_min: Math.min(stayMin, stayMax),
    stay_max: Math.max(stayMin, stayMax),
    budget_eur: num("f-budget"),
    adults: num("f-adults") || 1,
    bag: document.querySelector('input[name="bag"]:checked').value,
    max_stops: Number(document.querySelector('input[name="stops"]:checked').value),
  };
}

async function onSearch(event) {
  event.preventDefault();
  let params;
  try {
    params = readCheckin();
  } catch (err) {
    message(err.message, { error: true });
    return;
  }
  const btn = $("btn-search");
  btn.disabled = true;
  let step = 0;
  message(`${LOADING[0]}…`);
  const loader = setInterval(() => message(`${LOADING[++step % LOADING.length]}…`), 1600);
  try {
    const results = await api.search(params);
    state.results = { ...results, budget: params.budget_eur };
    state.byId = new Map(results.offers.map((o) => [o.id, o]));
    state.openId = null;
    showQuota(results.quota_remaining);
    setupFilters(results.offers);
    renderAll();
    $("results").hidden = false;
    const n = results.offers.length;
    message(n ? `${n} vol${n > 1 ? "s" : ""} vérifié${n > 1 ? "s" : ""}. Bon voyage.` : "Aucun vol vérifié. Élargis la recherche.");
    $("podium").scrollIntoView({ behavior: "smooth", block: "start" });
  } catch (err) {
    message(err.message, { error: true });
  } finally {
    clearInterval(loader);
    btn.disabled = false;
  }
}

/* ---------- Filtres (gratuits : ne relancent pas de recherche live) ---------- */

function setupFilters(offers) {
  const maxPrice = Math.max(0, ...offers.map((o) => o.price_eur));
  const slider = $("c-price");
  slider.max = String(Math.ceil(maxPrice / 10) * 10 || 1000);
  slider.value = slider.max;
  $("c-hour-min").value = "0";
  $("c-hour-max").value = "24";
  setRadio("c-stops", "9");
  $("c-bags").checked = false;
  const origins = [...new Set(offers.map((o) => o.origin))].sort();
  renderChecks($("c-origins"), origins, (c) => `${c} · ${state.config.origins[c]?.name || ""}`, "c-origin");
  const airlines = [...new Set(offers.map((o) => o.airlines[0]))].sort();
  renderChecks($("c-airlines"), airlines, (a) => a, "c-airline");
  syncOutputs();
}

function syncOutputs() {
  $("c-price-out").textContent = fmtPrice(Number($("c-price").value));
  $("c-hour-min-out").textContent = `${$("c-hour-min").value} h`;
  $("c-hour-max-out").textContent = `${$("c-hour-max").value} h`;
}

function filtered() {
  if (!state.results) return [];
  const priceMax = Number($("c-price").value);
  const stopsMax = Number(document.querySelector('input[name="c-stops"]:checked').value);
  const hMin = Number($("c-hour-min").value);
  const hMax = Number($("c-hour-max").value);
  const origins = new Set([...document.querySelectorAll('input[name="c-origin"]:checked')].map((i) => i.value));
  const airlines = new Set([...document.querySelectorAll('input[name="c-airline"]:checked')].map((i) => i.value));
  const hideBags = $("c-bags").checked;
  const sorters = {
    price: (a, b) => a.price_eur - b.price_eur,
    door: (a, b) => a.door_to_door_min - b.door_to_door_min,
    time: (a, b) => a.departure_time.localeCompare(b.departure_time),
  };
  return state.results.offers
    .filter((o) => o.price_eur <= priceMax && o.stops <= stopsMax)
    .filter((o) => hourOf(o.departure_time) >= hMin && hourOf(o.departure_time) < hMax)
    .filter((o) => origins.has(o.origin) && airlines.has(o.airlines[0]))
    .filter((o) => !(hideBags && o.bag_warning))
    .sort(sorters[state.sort]);
}

function renderTable(list) {
  renderRows($("rows"), list, {
    openId: state.openId,
    budget: state.results.budget,
    cheapestId: state.results.ranking?.cheapest?.id,
  });
  $("empty").hidden = list.length > 0;
  $("c-count").textContent = `${list.length} / ${state.results.offers.length} vols`;
}

const rerankPodium = debounce(async (list) => {
  if (!list.length) {
    renderPodium($("podium"), null, state.byId, { destLabel: state.destLabel });
    return;
  }
  try {
    const ranking = await api.rank(list.map((o) => o.id), state.results.budget);
    state.results.ranking = ranking;
    renderPodium($("podium"), ranking, state.byId, { destLabel: state.destLabel });
    renderTable(filtered());
  } catch (err) {
    message(err.message, { error: true });
  }
}, 250);

function onFilterChange() {
  syncOutputs();
  const list = filtered();
  renderTable(list);
  rerankPodium(list);
}

function renderAll() {
  const r = state.results;
  renderInsights($("insights"), r.price_insights);
  renderWarnings($("warnings"), r.warnings);
  renderPodium($("podium"), r.ranking, state.byId, { destLabel: state.destLabel });
  renderHints($("hints"), $("hints-list"), r.cache_hints);
  renderTable(filtered());
}

function onRowToggle(event) {
  if (event.type === "keydown" && event.key !== "Enter" && event.key !== " ") return;
  const row = event.target.closest("tr[data-id]");
  if (!row) return;
  event.preventDefault();
  state.openId = state.openId === row.dataset.id ? null : row.dataset.id;
  renderTable(filtered());
}

function onSort(event) {
  const btn = event.target.closest("button[data-sort]");
  if (!btn) return;
  state.sort = btn.dataset.sort;
  document.querySelectorAll(".sort button").forEach((b) => b.setAttribute("aria-pressed", String(b === btn)));
  renderTable(filtered());
}

/* ---------- Démarrage ---------- */

async function init() {
  flapTo(document.querySelector(".board-title .flap-line"), "DÉPARTS");
  startClock();
  $("examples").replaceChildren(...EXAMPLES.map((ex) =>
    h("button", { type: "button", class: "example", onclick: () => { $("command").value = ex; $("command-form").requestSubmit(); } }, ex)));
  try {
    state.config = await api.getConfig();
  } catch (err) {
    message(err.message, { error: true });
    return;
  }
  renderOrigins(state.config.origins);
  showQuota(state.config.quota_remaining);
  if (state.config.demo) message("Mode démo : les résultats rejouent une recherche enregistrée, sans quota.");
  else if (!state.config.has_live_key) message("Clé SerpApi absente : ajoute SERPAPI_KEY dans .env", { error: true });

  $("command-form").addEventListener("submit", onCommand);
  $("search-form").addEventListener("submit", onSearch);
  document.querySelector(".controls").addEventListener("input", onFilterChange);
  $("c-reset").addEventListener("click", () => { setupFilters(state.results.offers); onFilterChange(); });
  $("rows").addEventListener("click", onRowToggle);
  $("rows").addEventListener("keydown", onRowToggle);
  document.querySelector(".sort").addEventListener("click", onSort);

  // Lien partageable : ?q=naples+fin+oct+4-5j&go=1 remplit la commande (et lance la recherche si go=1).
  const url = new URLSearchParams(location.search);
  const q = url.get("q");
  if (q) {
    $("command").value = q.slice(0, 300);
    await onCommand(new Event("submit"));
    if (url.get("go") === "1") $("search-form").requestSubmit();
  }
}

init();
