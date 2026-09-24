// Sélecteur de destination : recherche mondiale (villes + aéroports) avec suggestions au clavier.
import * as api from "./api.js";
import { debounce, h } from "./dom.js";

function optionContent(place) {
  const many = place.iata.length > 1;
  const kind = place.kind === "city" ? (many ? `Ville · ${place.iata.length} aéroports` : "Ville") : "Aéroport";
  return [
    h("span", { class: "opt-main" }, place.label, place.country ? h("span", { class: "opt-country" }, ` · ${place.country}`) : null),
    h("span", { class: "opt-meta" }, `${kind} · ${place.iata.join(", ")}`),
  ];
}

export function createDestinationPicker({ input, list, onPick }) {
  let items = [];
  let active = -1;

  function close() {
    list.hidden = true;
    input.setAttribute("aria-expanded", "false");
    input.removeAttribute("aria-activedescendant");
    active = -1;
  }

  function highlight(index) {
    active = index;
    const options = [...list.querySelectorAll('[role="option"]')];
    options.forEach((li, i) => li.setAttribute("aria-selected", String(i === index)));
    if (index >= 0) {
      input.setAttribute("aria-activedescendant", `dest-opt-${index}`);
      options[index]?.scrollIntoView({ block: "nearest" });
    }
  }

  function pick(index) {
    const place = items[index];
    if (!place) return;
    onPick(place);
    input.value = "";
    close();
  }

  function show(places, note) {
    items = places;
    const rows = places.map((p, i) => h("li", {
      id: `dest-opt-${i}`, role: "option", "aria-selected": "false",
      onmousedown: (e) => { e.preventDefault(); pick(i); },
    }, optionContent(p)));
    if (!places.length) rows.push(h("li", { class: "opt-empty", role: "presentation" }, note || "Aucune destination trouvée."));
    else if (note) rows.unshift(h("li", { class: "opt-empty", role: "presentation" }, note));
    list.replaceChildren(...rows);
    list.hidden = false;
    input.setAttribute("aria-expanded", "true");
    highlight(places.length ? 0 : -1);
  }

  const lookup = debounce(async (term) => {
    if (term.length < 2) return close();
    try {
      const { results, online } = await api.places(term);
      if (input.value.trim() !== term) return; // réponse périmée
      show(results, online ? null : "Hors ligne : recherche limitée à la liste locale.");
    } catch (err) {
      show([], err.message);
    }
  }, 180);

  input.addEventListener("input", () => lookup(input.value.trim()));
  input.addEventListener("blur", () => setTimeout(close, 120));
  input.addEventListener("keydown", (e) => {
    if (list.hidden) return;
    if (e.key === "ArrowDown") { e.preventDefault(); highlight(Math.min(active + 1, items.length - 1)); }
    else if (e.key === "ArrowUp") { e.preventDefault(); highlight(Math.max(active - 1, 0)); }
    else if (e.key === "Enter") { e.preventDefault(); pick(active); }
    else if (e.key === "Escape") close();
  });

  return {
    close,
    suggest(places, term) {
      input.value = term || "";
      input.focus();
      show(places, places.length ? "Choisis ta destination :" : null);
    },
  };
}
