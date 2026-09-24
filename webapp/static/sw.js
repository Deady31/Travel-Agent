// Service worker minimal : rend l'app installable. Aucun cache, pour ne jamais afficher de prix périmés.
self.addEventListener("install", () => self.skipWaiting());
self.addEventListener("activate", (event) => event.waitUntil(self.clients.claim()));
