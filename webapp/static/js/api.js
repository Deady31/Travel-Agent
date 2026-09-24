// Appels au serveur local, avec messages d'erreur lisibles.

async function call(path, body) {
  let resp;
  try {
    resp = await fetch(path, body === undefined ? {} : {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(body),
    });
  } catch {
    throw new Error("Serveur injoignable. Est-ce que l'app tourne toujours ?");
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
export const search = (params) => call("/api/search", params);
export const rank = (offerIds, budget) => call("/api/rank", { offer_ids: offerIds, budget_eur: budget });
