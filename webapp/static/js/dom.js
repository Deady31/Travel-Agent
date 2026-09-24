// Petits utilitaires DOM et formatage. Tout le texte passe par textContent : pas d'injection HTML.

export function h(tag, attrs = {}, ...children) {
  const el = document.createElement(tag);
  for (const [key, value] of Object.entries(attrs)) {
    if (value === null || value === undefined || value === false) continue;
    if (key === "class") el.className = value;
    else if (key === "style") {
      for (const [prop, v] of Object.entries(value)) {
        if (prop.startsWith("--")) el.style.setProperty(prop, v);
        else el.style[prop] = v;
      }
    }
    else if (key.startsWith("on")) el.addEventListener(key.slice(2), value);
    else el.setAttribute(key, value === true ? "" : value);
  }
  for (const child of children.flat()) {
    if (child === null || child === undefined || child === false) continue;
    el.append(child instanceof Node ? child : document.createTextNode(String(child)));
  }
  return el;
}

const ALLOWED_HOSTS = ["www.google.com", "www.aviasales.com"];

export function safeUrl(url) {
  try {
    const u = new URL(url);
    return u.protocol === "https:" && ALLOWED_HOSTS.includes(u.hostname) ? u.href : null;
  } catch {
    return null;
  }
}

const euro = new Intl.NumberFormat("fr-FR", { style: "currency", currency: "EUR", maximumFractionDigits: 0 });
export const fmtPrice = (v) => euro.format(v);

export function fmtDuration(min) {
  const hours = Math.floor(min / 60);
  const rest = String(min % 60).padStart(2, "0");
  return hours ? `${hours} h ${rest}` : `${min} min`;
}

const dayFmt = new Intl.DateTimeFormat("fr-FR", { weekday: "short", day: "numeric", month: "short" });
export const fmtDay = (iso) => dayFmt.format(new Date(`${iso}T12:00:00`));
export const fmtShort = (iso) => `${iso.slice(8, 10)}/${iso.slice(5, 7)}`;
export const timeOf = (dt) => dt.slice(11, 16);
export const hourOf = (dt) => Number(dt.slice(11, 13));

export function fmtFetched(fetchedAt) {
  // "2026-09-24 07:38:08 UTC" -> "24/09 07:38 UTC"
  const m = /^(\d{4})-(\d{2})-(\d{2}) (\d{2}):(\d{2})/.exec(fetchedAt || "");
  return m ? `${m[3]}/${m[2]} ${m[4]}:${m[5]} UTC` : fetchedAt || "heure inconnue";
}

export const stopsLabel = (n) => (n === 0 ? "Direct" : `${n} escale${n > 1 ? "s" : ""}`);

function hash(str) {
  let x = 2166136261;
  for (const c of str) x = Math.imul(x ^ c.charCodeAt(0), 16777619);
  return x >>> 0;
}

export function barcode(seed) {
  // Décoratif : barres déterministes dérivées de l'identifiant, en une seule image SVG (léger à peindre).
  let x = hash(seed);
  const rects = [];
  let pos = 0;
  while (pos < 96) {
    x = Math.imul(x ^ (x >>> 13), 1274126177) >>> 0;
    const bar = 1 + (x % 3);
    rects.push(`<rect x='${pos}' width='${bar}' height='34'/>`);
    pos += bar + 1 + ((x >>> 4) % 3);
  }
  const svg = `<svg xmlns='http://www.w3.org/2000/svg' viewBox='0 0 ${pos} 34' preserveAspectRatio='none'><g fill='%231d2430'>${rects.join("")}</g></svg>`;
  return `url("data:image/svg+xml,${svg}")`;
}

export function debounce(fn, ms) {
  let t;
  return (...args) => {
    clearTimeout(t);
    t = setTimeout(() => fn(...args), ms);
  };
}
