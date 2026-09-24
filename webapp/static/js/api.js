// Appels au serveur, avec messages d'erreur lisibles et retour à l'écran de connexion si la session expire.

async function call(path, body) {
  let resp;
  try {
    resp = await fetch(path, body === undefined ? {} : {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(body),
    });
  } catch {
    throw new Error("Serveur injoignable. Vérifie ta connexion.");
  }
  if (resp.status === 401 && path !== "/api/login") {
    window.location.href = "/login";
    throw new Error("Connexion requise.");
  }
  const data = await resp.json().catch(() => ({}));
  if (!resp.ok) {
    const detail = Array.isArray(data.detail)
      ? data.detail.map((d) => `${(d.loc || []).slice(-1)[0]} : ${d.msg}`).join(" · ")
      : data.detail;
    throw new Error(detail || `Erreur ${resp.status}`);
  }
  return data;
}

export const getConfig = () => call("/api/config");
export const parseCommand = (text) => call("/api/parse", { text });
export const places = (term) => call(`/api/places?q=${encodeURIComponent(term)}`);
export const search = (params) => call("/api/search", params);
export const rank = (offers, budget) => call("/api/rank", { offers, budget_eur: budget });
export const login = (password) => call("/api/login", { password });
export const logout = () => call("/api/logout", {});
