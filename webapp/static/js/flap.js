// Effet « palettes » des tableaux d'aéroport (Solari).

const GLYPHS = "ABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789";
const reduced = window.matchMedia("(prefers-reduced-motion: reduce)").matches;

export function flapTo(el, text, { speed = 38, spins = 6 } = {}) {
  const target = String(text).toUpperCase();
  el.setAttribute("aria-label", target);
  el.replaceChildren();
  const cells = [...target].map((ch) => {
    const span = document.createElement("span");
    span.className = "flap-char";
    span.setAttribute("aria-hidden", "true");
    span.textContent = ch === " " ? " " : reduced ? ch : GLYPHS[Math.floor(Math.random() * GLYPHS.length)];
    el.append(span);
    return { span, ch };
  });
  if (reduced) return Promise.resolve();

  return new Promise((resolve) => {
    let tick = 0;
    const timer = setInterval(() => {
      tick += 1;
      let done = true;
      cells.forEach(({ span, ch }, i) => {
        if (ch === " ") return;
        const settleAt = spins + i;
        if (tick < settleAt) {
          done = false;
          span.textContent = GLYPHS[(tick * 7 + i * 13) % GLYPHS.length];
          span.classList.remove("is-flipping");
          void span.offsetWidth; // relance l'animation
          span.classList.add("is-flipping");
        } else {
          span.textContent = ch;
        }
      });
      if (done) {
        clearInterval(timer);
        resolve();
      }
    }, speed);
  });
}
