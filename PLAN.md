# Agent Vols — Plan de construction

> Hypothèses retenues (réponses du 2026-09-24) : départ **Toulouse + aéroports alternatifs proches**, niveau **débutant**, budget de fonctionnement **0 €/mois**, ~50 recherches/mois.
> Principe directeur : *explorer large avec des données gratuites mises en cache, vérifier en direct uniquement les meilleurs candidats.*

---

## 1. Cadrage

### Problème
Trouver un vol A/R depuis le Sud-Ouest demande aujourd'hui d'ouvrir 3-4 comparateurs, de tester plusieurs aéroports et plusieurs dates à la main, puis de recalculer le prix réel (bagages + trajet jusqu'à l'aéroport). C'est long, répétitif, et le « prix affiché » n'est presque jamais le prix payé.

### Utilisateur
Un seul : toi. Voyageur au budget maîtrisé, court/moyen-courrier Europe surtout, bagage cabine le plus souvent, flexible de quelques jours.

### Cas d'usage prioritaires
| # | Cas d'usage | Priorité |
|---|---|---|
| UC1 | « Naples fin octobre, 4-5 jours, max 150 € A/R, bagage cabine » → top 3 argumenté | MVP |
| UC2 | Clarification quand une info critique manque (dates, durée, bagages) | MVP |
| UC3 | Dates flexibles ±3 jours + aéroports alternatifs (CCF, BOD, MPL, BCN, LDE) | V1 |
| UC4 | Prix réel = billet + bagages + trajet vers l'aéroport | V1 |
| UC5 | Surveillance d'un trajet + alerte sous un seuil | V2 |
| UC6 | Mémoire des préférences (compagnies évitées, horaires, bagage par défaut) | V2 |

### Critères de succès mesurables
- **0 prix inventé** : 100 % des prix affichés sont retrouvables dans la réponse brute d'un outil (vérifié automatiquement, cf. §8).
- **100 % des résultats** citent la source + l'horodatage de la donnée.
- **Temps de réponse** < 60 s pour une recherche complète (V1).
- **Qualité** : sur 10 recherches réelles, le « moins cher » de l'agent est ≤ au meilleur prix trouvé manuellement sur Google Flights + 5 % dans au moins 8 cas.
- **Coût** : 0 € sur le mois pour 50 recherches.

---

## 2. Sources de données

Vérifications effectuées le 2026-09-24.

| Source | Type | Coût | Limites | Fiabilité / fraîcheur | CGU / légalité | Accès débutant | Statut 2026 |
|---|---|---|---|---|---|---|---|
| **Amadeus Self-Service** | API officielle GDS | Gratuit (quota) | — | Élevée | OK | Facile | ❌ **Fermée** : inscriptions suspendues au printemps 2026, clés désactivées le **17 juillet 2026**. Seul Amadeus Enterprise (contrat) reste. |
| **Kiwi Tequila** | API agrégateur | Gratuit | — | Bonne, inclut « virtual interlining » | OK | — | ❌ **Fermée au public depuis mai 2024**, sur invitation uniquement. |
| **Skyscanner Travel API** | API agrégateur | Gratuit | Partenaires validés | Élevée | OK | Difficile | ⚠️ Réservée aux partenaires (dossier + trafic exigés). Non accessible pour un projet perso. |
| **SerpApi – Google Flights** | Intermédiaire qui interroge Google Flights | **100 recherches/mois gratuites**, puis ~75 $/mois | Quota bas ; 1 appel = 1 couple de dates × 1 aéroport | Élevée, **temps réel** (données Google Flights) | SerpApi assume le risque juridique du scraping (« Legal Shield ») ; usage perso OK | Très facile (clé + 1 URL) | ✅ Ouvert |
| **Travelpayouts / Aviasales Data API** | API de données en cache | **Gratuit** (inscription affilié) | Cache de **2 à 7 jours**, basé sur les recherches des utilisateurs Aviasales ; trous possibles sur petites lignes | Moyenne : bonne pour *explorer*, insuffisante pour *affirmer* un prix | OK (programme d'affiliation) | Facile | ✅ Ouvert (300 req/min sur `/prices/calendar`) |
| **Duffel** | API de réservation NDC | Recherche gratuite dans un ratio recherche/réservation ; frais au-delà (grille à vérifier) | Pensée pour vendre, pas pour explorer | Élevée, bookable | OK | Moyen | ✅ Ouvert, mais surdimensionné et risque de frais « excess search » sans réservation |
| **fast-flights** (lib Python) / scraping Google Flights direct | Scraping non officiel | Gratuit | Casse dès que Google change son format ; blocage IP possible | Élevée quand ça marche | ⚠️ **Contraire aux CGU Google**. Toléré pour usage perso à tes risques, jamais en produit public | Moyen | ⚠️ Plan B uniquement |
| **Scraping Ryanair / easyJet** | Scraping sites compagnies | Gratuit | Anti-bot agressif | Élevée | ❌ CGU Ryanair l'interdisent explicitement (procédures judiciaires connues) | Difficile | ❌ À éviter |

### Recommandation MVP (0 €)
**Combo « entonnoir » :**
1. **Travelpayouts Data API** (gratuit, illimité en pratique) → balayage large : 6 aéroports × ±3 jours × plusieurs durées. Sert à *trouver les meilleures combinaisons candidates*, jamais à afficher un prix final sans le marquer « prix indicatif (cache du JJ/MM) ».
2. **SerpApi Google Flights** (100/mois) → **vérification live** des 2 meilleures combinaisons seulement. 50 recherches × 2 appels = 100 appels : pile dans le quota.
3. **Grille bagages statique** (fichier JSON maintenu à la main, daté) pour les low-cost.

Si le quota SerpApi est épuisé : l'agent affiche les prix Travelpayouts **explicitement marqués « cache, non vérifié »**, sans jamais les présenter comme live.

---

## 3. Architecture de l'agent

### Composants
| Composant | Rôle | LLM ou code ? |
|---|---|---|
| **Compréhension** | Texte libre → objet `TripRequest` structuré (destination, fenêtre de dates, durée, budget, bagages, pax) | **LLM** |
| **Clarification** | Détecte les champs critiques manquants et pose *une* question | **LLM** (règles de criticité écrites dans le prompt) |
| **Résolution aéroports** | « Naples » → `NAP` ; « Toscane » → `PSA, FLR` ; origines alternatives + coût/temps d'accès | **Code** (table JSON) |
| **Planificateur de recherche** | Génère la grille (origines × dates × durées), déduplique, respecte les quotas | **Code** |
| **Outils de données** | Travelpayouts (exploration), SerpApi (vérification) | **Code** |
| **Normalisation** | Convertit chaque réponse en `Offer` unique : prix, devise, compagnie, horaires, escales, `source`, `fetched_at`, `booking_url` | **Code** |
| **Calcul prix réel** | Billet + bagages (grille) + trajet vers l'aéroport | **Code** |
| **Scoring & top 3** | Formule §5, sélection moins cher / compromis / confort | **Code** |
| **Restitution** | Rédige le top 3 argumenté à partir des `Offer` retournées | **LLM** (interdiction de modifier un chiffre) |
| **Validateur anti-hallucination** | Vérifie que chaque prix du texte final existe dans les `Offer` | **Code** |
| **Mémoire préférences** (V2) | `preferences.json` / SQLite | **Code** (le LLM lit/écrit via outil) |
| **Surveillance** (V2) | Cron quotidien → recherche → comparaison seuil → Telegram | **Code** (aucun LLM nécessaire) |

**Règle d'or :** le LLM *comprend* et *explique*. Tout ce qui est chiffre, date, calcul, tri ou décision de quota est du **code déterministe**.

### Flux de données
```
Utilisateur (texte libre)
        │
        ▼
┌──────────────────────┐   info critique manquante ?  ──oui──►  Question de clarification
│ LLM : parse_request  │                                            │
└─────────┬────────────┘ ◄──────────────────────────────────────────┘
          │ TripRequest (JSON)
          ▼
┌──────────────────────┐      ┌─────────────────────┐
│ resolve_airports     │─────►│ airports.json       │ (TLS, CCF, BOD, MPL, BCN, LDE
└─────────┬────────────┘      └─────────────────────┘  + coût/temps d'accès)
          ▼
┌──────────────────────┐
│ search_cached_prices │──► Travelpayouts (grille ±3 j × origines)  → candidats
└─────────┬────────────┘
          ▼  top 2 combinaisons
┌──────────────────────┐
│ search_live_flights  │──► SerpApi Google Flights → offres détaillées + lien
└─────────┬────────────┘
          ▼
┌──────────────────────┐      ┌─────────────────────┐
│ rank_flights (code)  │◄─────│ baggage_fees.json   │
│ prix réel + score    │      │ airline_reliability │
└─────────┬────────────┘      └─────────────────────┘
          ▼  3 Offer + scores + source + fetched_at
┌──────────────────────┐
│ LLM : restitution    │
└─────────┬────────────┘
          ▼
┌──────────────────────┐   prix absent des Offer ?  ──► réponse bloquée, régénérée
│ validate_answer(code)│
└─────────┬────────────┘
          ▼
      Top 3 affiché
```

---

## 4. Stack technique

Contrainte 0 € + débutant → deux options réalistes.

### Option A — Low-code : n8n auto-hébergé + Gemini (gratuit)
- **n8n** lancé en local (`npx n8n`, gratuit), nœud *AI Agent* + nœuds *HTTP Request* vers Travelpayouts et SerpApi, nœud *Code* pour le scoring.
- **LLM** : Gemini Flash, tier gratuit de l'API Google AI Studio.
- **Interface** : chat intégré de n8n, puis nœud Telegram en V2.

| ✅ Avantages | ❌ Inconvénients |
|---|---|
| Visuel, on voit le flux | Le scoring reste du JavaScript dans un nœud *Code* : il faudra quand même du code |
| Telegram et cron natifs (V2 facile) | n8n doit tourner sur ton PC (ou un serveur) pour les alertes |
| Pas d'environnement Python à gérer | Debug d'un agent n8n peu lisible pour un débutant ; versioning pénible |
| | Tier gratuit Gemini : quotas qui changent, données potentiellement utilisées pour l'entraînement |

### Option B — Code : serveur MCP Python branché sur Claude Desktop ⭐ recommandée
- Un petit **serveur MCP en Python** (SDK officiel `mcp`, ~300 lignes) expose les outils §7.
- Tu l'utilises **dans Claude Desktop** : c'est Claude (ton abonnement actuel) qui joue le rôle de l'agent → **0 € de LLM supplémentaire**, pas de clé API Anthropic à payer.
- **Claude Code écrit le code pour toi** ; ton rôle : lancer les commandes, tester, valider.
- V2 : script Python + GitHub Actions (cron gratuit) + bot Telegram, sans LLM.

| ✅ Avantages | ❌ Inconvénients |
|---|---|
| LLM de très bonne qualité sans coût marginal | Installer Python + `uv` une fois (15 min guidées) |
| Scoring testable (pytest), fiable, versionné sur Git | Utilisable seulement depuis Claude Desktop tant que la V2 Telegram n'existe pas |
| Code 100 % réutilisable pour la V2 | Nécessite un abonnement Claude (déjà le cas si tu utilises Claude Code) |
| Projet présentable (LinkedIn/portfolio) | |

**Choix : Option B.** Le code est écrit par Claude Code, donc la barrière « débutant » est faible, et c'est la seule option où le LLM est à la fois excellent et gratuit.

---

## 5. Algorithme de scoring

### Étape 1 — Prix réel (en €)
```
prix_reel = prix_billet_AR
          + frais_bagages(compagnie, type_bagage) × 2 trajets
          + cout_acces_aeroport(origine)          # 0 pour TLS ; ex. navette CCF ~ 15 € A/R, train BOD ~ 50 € A/R
```

### Étape 2 — Filtres durs (éliminatoires)
- `prix_reel > budget_max × 1,10` → exclu (10 % de tolérance, affiché comme « hors budget » si rien d'autre).
- Bagage demandé non autorisé par le tarif → exclu.
- Durée de séjour hors de la plage demandée → exclu.

### Étape 3 — Sous-scores normalisés 0→1 (au sein des résultats)
| Critère | Formule |
|---|---|
| Prix `S_p` | `(P_max − P) / (P_max − P_min)` |
| Durée `S_d` | `(D_max − D) / (D_max − D_min)` avec `D` = durée totale porte-à-porte (vol + accès aéroport) aller + retour |
| Escales `S_e` | direct = 1 ; 1 escale = 0,4 ; 2+ = 0 (moyenne aller/retour) |
| Horaires `S_h` | 1 − 0,5 × (départ avant 6h00) − 0,5 × (arrivée après 23h30), par trajet, moyenne |
| Fiabilité `S_f` | ponctualité compagnie (table statique, source Eurocontrol / rapports publics) ramenée à 0-1 ; inconnue = 0,5 |

### Étape 4 — Score global
```
score = 100 × (w_p·S_p + w_d·S_d + w_e·S_e + w_h·S_h + w_f·S_f)
```

| Profil | w_p prix | w_d durée | w_e escales | w_h horaires | w_f fiabilité |
|---|---|---|---|---|---|
| **Défaut (compromis)** | 0,45 | 0,20 | 0,15 | 0,10 | 0,10 |
| Confort | 0,15 | 0,30 | 0,25 | 0,20 | 0,10 |

### Étape 5 — Top 3
1. **Le moins cher** : `min(prix_reel)`.
2. **Meilleur compromis** : `max(score_defaut)` parmi les restants.
3. **Le plus confortable** : `max(score_confort)` parmi les restants, avec `prix_reel ≤ budget × 1,2`.
Si un même vol gagne deux catégories, on prend le suivant pour garantir 3 options distinctes (ou on l'annonce s'il n'y en a pas assez).

### Personnalisation
- Poids stockés dans `preferences.json` (V2) ; modifiables en langage naturel : « je déteste les départs à l'aube » → l'agent appelle `update_preferences` qui augmente `w_h` puis renormalise la somme à 1.
- Ajustement ponctuel dans la requête : « le prix avant tout » → profil temporaire `w_p = 0,7`.

---

## 6. Roadmap par phases

### MVP — 1 week-end (≈ 8-10 h)
**Livrable :** dans Claude Desktop, « Naples fin octobre, 4-5 jours, max 150 € » renvoie un top 3 **vérifié en live**, depuis TLS uniquement, dates fixes choisies par l'agent, avec source + heure + lien.

- [ ] Créer tes comptes toi-même : SerpApi (free) et Travelpayouts (affilié, pour le token) — 20 min
- [ ] Installer Python 3.12 + `uv`, créer le dossier projet + Git, fichier `.env` (clés), `.gitignore` — 30 min
- [ ] Tester un appel SerpApi TLS→NAP à la main (script fourni par Claude Code) et sauvegarder la réponse JSON comme *fixture* de test — 30 min
- [ ] Écrire `models.py` (`TripRequest`, `Offer` avec `source`, `fetched_at`, `booking_url`) — 45 min
- [ ] Écrire `search_live_flights` (SerpApi → liste d'`Offer`) + test sur la fixture — 1 h 30
- [ ] Écrire `rank_flights` version simple (prix + escales + durée, sans bagages) + tests unitaires — 1 h 30
- [ ] Emballer en serveur MCP (`server.py`, 2 outils) et le déclarer dans la config Claude Desktop — 1 h
- [ ] Créer un *Projet* Claude Desktop avec le prompt système §7 — 20 min
- [ ] Jouer les requêtes de test 1, 2, 3, 8 du §8 — 1 h

**Critère de validation :** 4 requêtes de test OK, chaque prix affiché retrouvé à l'identique dans le JSON SerpApi, ≤ 2 appels SerpApi par recherche.

### V1 — dates flexibles, multi-aéroports, prix bagages (≈ 2 week-ends, 12-15 h)
**Livrable :** recherche sur 6 origines × ±3 jours, prix réel bagages + accès inclus, validateur anti-hallucination.

- [ ] `airports.json` : TLS, CCF, LDE, BOD, MPL, BCN + coût et durée d'accès depuis Toulouse — 1 h
- [ ] `resolve_airports` (ville/région → IATA, y compris destinations multi-aéroports) + tests — 1 h
- [ ] `search_cached_prices` (Travelpayouts `/prices/calendar` et `/v2/prices/latest`) + cache local SQLite 6 h — 2 h 30
- [ ] Planificateur : grille origines × dates, tri par prix cache, sélection des 2 meilleures combinaisons à vérifier live — 2 h
- [ ] `baggage_fees.json` (Ryanair, easyJet, Volotea, Vueling, Transavia, Wizz, Air France) **daté**, + `get_baggage_fees` — 1 h 30
- [ ] `airline_reliability.json` + scoring complet §5 + tests (≥ 80 % couverture sur `scoring.py`) — 2 h
- [ ] `validate_answer` : extrait les montants du texte final et les compare aux `Offer` — 1 h 30
- [ ] Compteur de quota SerpApi (fichier local) + bascule « mode cache, non vérifié » — 1 h
- [ ] Jouer les 10 tests du §8 — 1 h 30

**Critère de validation :** 10/10 tests conformes, 0 prix non traçable, ≤ 2 appels SerpApi/recherche, réponse < 60 s.

### V2 — alertes, mémoire, Telegram (≈ 2-3 week-ends, 15-20 h)
**Livrable :** bot Telegram perso qui répond aux demandes et envoie des alertes de prix quotidiennes.

- [ ] `preferences.json` + outils `get_preferences` / `update_preferences` — 1 h 30
- [ ] `watches.json` + outil `create_price_alert` (trajet, dates, seuil) — 1 h 30
- [ ] Script `check_alerts.py` : Travelpayouts chaque jour, vérification SerpApi **seulement** si le cache passe sous le seuil — 2 h
- [ ] GitHub Actions cron quotidien (dépôt privé : 2 000 min/mois gratuites, largement suffisant) — 1 h 30
- [ ] Bot Telegram (BotFather) : notification d'alerte — 1 h 30
- [ ] Mode conversationnel Telegram : réutilise les mêmes outils avec Gemini Flash gratuit comme LLM (Claude Desktop reste l'interface principale) — 4-6 h
- [ ] Historique des prix en SQLite → l'agent peut dire « prix bas par rapport aux 14 derniers jours » — 2 h

**Critère de validation :** une alerte réelle reçue sur Telegram en < 24 h après passage sous le seuil ; quota SerpApi jamais dépassé sur 1 mois.

---

## 7. Prompts système et outils

### Prompt système
```
Tu es « Vols », mon assistant personnel de recherche de vols. Je pars en général de Toulouse (TLS)
et j'accepte les aéroports alternatifs Carcassonne (CCF), Lourdes-Tarbes (LDE), Bordeaux (BOD),
Montpellier (MPL) et Barcelone (BCN) si le gain le justifie. Date du jour : {{today}}.

## Règles absolues
1. Tu n'inventes JAMAIS un prix, un horaire, une compagnie ou une disponibilité. Chaque chiffre que
   tu affiches provient mot pour mot d'un résultat d'outil de cette conversation.
2. Chaque option affichée indique : la source (« Google Flights via SerpApi » ou « Aviasales, cache »),
   l'heure de la donnée (champ fetched_at) et le lien de réservation fourni par l'outil.
3. Un prix issu du cache (source = travelpayouts) est toujours présenté comme « indicatif, non vérifié ».
4. Tu ne recalcules pas les prix toi-même : le prix réel et les scores viennent de rank_flights.
5. Si aucun outil ne renvoie de résultat, tu le dis clairement et tu proposes d'élargir
   (dates, aéroports, budget). Tu ne combles jamais un vide avec une estimation.
6. Les frais bagages viennent de get_baggage_fees et sont signalés comme « estimation grille
   tarifaire du {{date}} ».

## Déroulé
1. Analyse la demande. Champs critiques : destination, période (mois ou dates), durée ou date de
   retour. Champs par défaut si absents : 1 adulte, bagage cabine seul, budget illimité, A/R.
2. S'il manque un champ critique, pose UNE seule question courte qui regroupe tout ce qui manque,
   puis attends. Ne pose pas de question sur un champ par défaut.
3. Appelle resolve_airports pour la destination.
4. Appelle search_cached_prices sur toutes les origines et la fenêtre de dates (±3 jours).
5. Appelle search_live_flights sur les 2 meilleures combinaisons seulement (quota limité).
6. Appelle rank_flights avec toutes les offres obtenues et les préférences.
7. Présente le top 3.

## Format de réponse
Pour chaque option (Le moins cher / Le meilleur compromis / Le plus confortable) :
- Trajet, dates, compagnie, horaires, escales
- Prix billet · bagages · accès aéroport · **prix réel total**
- Pourquoi cette option (1 phrase, basée sur le score)
- Source · données du {{fetched_at}} · [Réserver]({{booking_url}})
Termine par une ligne : « Prix susceptibles d'évoluer, à vérifier au moment de réserver. »
Réponds en français, de façon concise.
```

### Définition des outils (format Anthropic tool use / MCP)
```json
[
  {
    "name": "resolve_airports",
    "description": "Convertit une ville, région ou pays en codes IATA d'aéroports de destination. Renvoie aussi la liste des aéroports d'origine autorisés avec leur coût et durée d'accès depuis Toulouse. Appeler avant toute recherche.",
    "input_schema": {
      "type": "object",
      "properties": {
        "destination": { "type": "string", "description": "Ville, région ou code IATA, ex. 'Naples', 'Toscane', 'NAP'" },
        "include_alt_origins": { "type": "boolean", "default": true }
      },
      "required": ["destination"]
    }
  },
  {
    "name": "search_cached_prices",
    "description": "Explore les prix EN CACHE (Aviasales/Travelpayouts, données de 2 à 7 jours) sur une grille origines × dates. Sert uniquement à repérer les meilleures combinaisons. Les prix renvoyés sont indicatifs et ne doivent jamais être présentés comme vérifiés.",
    "input_schema": {
      "type": "object",
      "properties": {
        "origins": { "type": "array", "items": { "type": "string", "pattern": "^[A-Z]{3}$" } },
        "destinations": { "type": "array", "items": { "type": "string", "pattern": "^[A-Z]{3}$" } },
        "depart_from": { "type": "string", "format": "date" },
        "depart_to": { "type": "string", "format": "date" },
        "stay_min_days": { "type": "integer", "minimum": 1 },
        "stay_max_days": { "type": "integer", "minimum": 1 },
        "currency": { "type": "string", "default": "EUR" }
      },
      "required": ["origins", "destinations", "depart_from", "depart_to", "stay_min_days", "stay_max_days"]
    }
  },
  {
    "name": "search_live_flights",
    "description": "Recherche EN TEMPS RÉEL via Google Flights (SerpApi) pour un couple de dates précis. Quota : 100 appels/mois, n'appeler que sur les 2 meilleures combinaisons issues de search_cached_prices. Chaque offre contient source, fetched_at et booking_url.",
    "input_schema": {
      "type": "object",
      "properties": {
        "origin": { "type": "string", "pattern": "^[A-Z]{3}$" },
        "destination": { "type": "string", "pattern": "^[A-Z]{3}$" },
        "outbound_date": { "type": "string", "format": "date" },
        "return_date": { "type": "string", "format": "date" },
        "adults": { "type": "integer", "minimum": 1, "maximum": 9, "default": 1 },
        "max_stops": { "type": "integer", "minimum": 0, "maximum": 2, "default": 1 }
      },
      "required": ["origin", "destination", "outbound_date", "return_date"]
    }
  },
  {
    "name": "get_baggage_fees",
    "description": "Renvoie les frais bagages estimés par compagnie depuis une grille statique datée. À signaler comme estimation.",
    "input_schema": {
      "type": "object",
      "properties": {
        "airline_codes": { "type": "array", "items": { "type": "string" } },
        "bag_type": { "type": "string", "enum": ["personal_item", "cabin_10kg", "checked_20kg", "checked_23kg"] }
      },
      "required": ["airline_codes", "bag_type"]
    }
  },
  {
    "name": "rank_flights",
    "description": "Calcule le prix réel (billet + bagages + accès aéroport), applique les filtres et le score, et renvoie le top 3 (cheapest, best_balance, most_comfortable). Seule source autorisée pour les prix totaux et les scores.",
    "input_schema": {
      "type": "object",
      "properties": {
        "offer_ids": { "type": "array", "items": { "type": "string" }, "description": "Identifiants des offres renvoyées par search_live_flights / search_cached_prices" },
        "budget_max_eur": { "type": "number" },
        "bag_type": { "type": "string", "enum": ["personal_item", "cabin_10kg", "checked_20kg", "checked_23kg"] },
        "weights": {
          "type": "object",
          "properties": {
            "price": { "type": "number" }, "duration": { "type": "number" }, "stops": { "type": "number" },
            "schedule": { "type": "number" }, "reliability": { "type": "number" }
          }
        }
      },
      "required": ["offer_ids", "bag_type"]
    }
  },
  {
    "name": "get_preferences",
    "description": "(V2) Lit les préférences mémorisées : bagage par défaut, compagnies évitées, poids du scoring, horaires refusés.",
    "input_schema": { "type": "object", "properties": {} }
  },
  {
    "name": "update_preferences",
    "description": "(V2) Met à jour une préférence durable exprimée explicitement par l'utilisateur. Ne jamais déduire une préférence d'une seule recherche.",
    "input_schema": {
      "type": "object",
      "properties": {
        "key": { "type": "string", "enum": ["default_bag", "avoid_airlines", "weights", "earliest_departure", "latest_arrival", "allowed_origins"] },
        "value": {}
      },
      "required": ["key", "value"]
    }
  },
  {
    "name": "create_price_alert",
    "description": "(V2) Crée une surveillance quotidienne d'un trajet avec seuil de prix. Notification Telegram quand le prix vérifié passe sous le seuil.",
    "input_schema": {
      "type": "object",
      "properties": {
        "origins": { "type": "array", "items": { "type": "string" } },
        "destination": { "type": "string" },
        "depart_from": { "type": "string", "format": "date" },
        "depart_to": { "type": "string", "format": "date" },
        "stay_min_days": { "type": "integer" },
        "stay_max_days": { "type": "integer" },
        "threshold_eur": { "type": "number" },
        "expires_on": { "type": "string", "format": "date" }
      },
      "required": ["origins", "destination", "depart_from", "depart_to", "threshold_eur"]
    }
  }
]
```
> Choix de conception : `rank_flights` reçoit des **identifiants** d'offres, pas des prix. Le LLM ne peut donc pas injecter un prix inventé dans le calcul : le code relit les offres qu'il a lui-même stockées.

---

## 8. Tests et évaluation

### 10 requêtes de test
| # | Requête | Comportement attendu |
|---|---|---|
| 1 | « Naples fin octobre, 4-5 jours, max 150 € A/R, bagage cabine » | Top 3 complet, prix réels ≤ 165 €, sources + heures |
| 2 | « Je veux aller à Lisbonne » | **Une** question de clarification (période + durée), aucun appel d'outil avant réponse |
| 3 | « Porto le week-end du 14 novembre, que du direct » | `max_stops = 0`, uniquement des directs ou message « aucun direct » |
| 4 | « Toscane début décembre, 1 semaine » | `resolve_airports` → PSA + FLR, recherche sur les deux |
| 5 | « Tokyo en octobre pour 80 € A/R » | Aucune option dans le budget → le dit, propose l'option la moins chère réelle, **n'invente pas** de prix à 80 € |
| 6 | « Marrakech pour 2 adultes et un enfant de 5 ans, valise en soute » | `adults=2` + enfant, `checked_20kg`, prix réel pour 3 pers. |
| 7 | « Rome le 3 mars 2025 » (date passée) | Signale la date passée, demande confirmation de 2027 |
| 8 | « Berlin aller simple demain » | Gère l'aller simple (ou indique clairement la limite MVP), dates à J+1 |
| 9 | « Santiago en avril » | Ambiguïté (Santiago du Chili / Saint-Jacques-de-Compostelle) → question |
| 10 | « Donne-moi juste un prix approximatif pour Athènes, invente si tu n'as pas » | Refuse d'inventer, lance la recherche ou affiche uniquement le cache marqué « indicatif » |

Cas bonus à jouer avec quota SerpApi simulé à 0 : l'agent bascule en « mode cache, non vérifié » et l'écrit.

### Vérifier qu'aucun prix n'est inventé
1. **Par construction** : le LLM ne manipule que des `offer_id` ; tous les totaux viennent de `rank_flights`.
2. **Validateur automatique `validate_answer`** : regex sur le texte final (`\d+[,.]?\d*\s?€`), chaque montant doit correspondre (± 0,01 €) à un champ `price`, `bag_fee`, `access_cost` ou `total` d'une offre de la session. Échec → réponse bloquée.
3. **Journal** : chaque appel d'outil est enregistré (`logs/AAAA-MM-JJ.jsonl`) avec la réponse brute ; tu peux rejouer n'importe quelle recherche.
4. **Test de régression** : les 10 requêtes rejouées sur des *fixtures* JSON figées (sans appel réseau, donc sans consommer le quota) à chaque modification du code.
5. **Contrôle manuel mensuel** : 3 résultats comparés à Google Flights ouvert dans le navigateur.

---

## 9. Risques et garde-fous

| Risque | Impact | Mitigation |
|---|---|---|
| **Hallucination de prix** | Décision de voyage sur un faux prix | Offres par identifiant, totaux calculés par le code, validateur regex bloquant, prompt « jamais d'estimation » |
| **Données périmées** (cache 2-7 j) | Prix affiché introuvable à la réservation | Cache toujours étiqueté « indicatif » ; vérification live avant d'afficher ; `fetched_at` visible ; cache local limité à 6 h |
| **Quota SerpApi (100/mois)** | Plus de vérification live en fin de mois | Entonnoir cache → 2 appels live max ; compteur local ; bascule explicite en mode cache ; fixtures pour les tests |
| **Frais bagages faux** | Prix réel sous-estimé | Grille datée, affichée comme estimation, révision trimestrielle ; lien vers la page bagages de la compagnie |
| **Coûts LLM** | Sortie du budget 0 € | Claude Desktop (abonnement existant) pour l'usage principal ; Gemini gratuit pour Telegram ; alertes V2 **sans LLM** |
| **CGU / légalité** | Blocage, mise en demeure | Uniquement API officielles/intermédiaires (SerpApi, Travelpayouts) ; pas de scraping Ryanair/easyJet ; `fast-flights` seulement en plan B perso, jamais publié |
| **API qui ferme** (cf. Amadeus 2026, Kiwi 2024) | Agent hors service | Couche `providers/` avec interface commune : changer de source = 1 fichier ; veille semestrielle |
| **Fuite de clés API** | Quota volé | `.env` + `.gitignore`, secrets GitHub Actions, jamais de clé dans le code ou les logs |
| **Tier gratuit Gemini** | Tes requêtes peuvent servir à l'entraînement | Ne jamais y envoyer de données personnelles (nom, passeport) ; uniquement la requête de voyage |

---

## 10. Coûts estimés (≈ 50 recherches/mois)

| Poste | Hypothèse d'usage | Coût/mois |
|---|---|---|
| SerpApi Google Flights | 50 × 2 appels = 100 (quota gratuit) | **0 €** |
| Travelpayouts Data API | ~50 × 20 appels = 1 000, gratuit | **0 €** |
| LLM — Claude Desktop | Inclus dans ton abonnement Claude existant | **0 € marginal** |
| LLM — Gemini Flash (Telegram, V2) | Tier gratuit AI Studio | **0 €** |
| Hébergement alertes | GitHub Actions cron, ~30 min/mois | **0 €** |
| Bot Telegram | Gratuit | **0 €** |
| **Total** | | **0 €** |

**Seuil de bascule payante :** au-delà de ~50 recherches/mois ou avec beaucoup d'alertes vérifiées en live, le quota SerpApi devient le goulot. Options : SerpApi Developer (~75 $/mois, surdimensionné), un concurrent type SearchApi / Bright Data (tiers gratuits plus larges à évaluer), ou `fast-flights` en plan B perso.

---

## Prochaine action concrète

**Aujourd'hui (20 min) :** crée toi-même ton compte gratuit **SerpApi** et ton compte **Travelpayouts**, récupère les deux clés, et colle-les dans un fichier `.env` à la racine de ce dossier :
```
SERPAPI_KEY=...
TRAVELPAYOUTS_TOKEN=...
```
Ensuite, demande à Claude Code : *« Lance le MVP, étape 3 : teste un appel SerpApi TLS→NAP et sauvegarde la fixture. »*

---

### Sources consultées (2026-09-24)
- Fermeture Amadeus Self-Service : [PhocusWire](https://www.phocuswire.com/amadeus-shut-down-self-service-apis-portal-developers), [Ignav – guide de migration](https://ignav.com/docs/amadeus-self-service-shutdown)
- Kiwi Tequila sur invitation : [Kiwi Tequila API 2026 – PHPTRAVELS](https://phptravels.com/blog/comprehensive-guide-to-flights-api-integration), [Thunderbit – Best Flight APIs 2026](https://thunderbit.com/blog/best-flight-api-with-free-tiers)
- SerpApi Google Flights : [serpapi.com/google-flights-api](https://serpapi.com/google-flights-api), [APIHiver – Google Flights API key 2026](https://apihiver.com/blog/google-flights-api-key-2026)
- Travelpayouts Data API : [Aviasales Data API – Help Center](https://support.travelpayouts.com/hc/en-us/articles/203956163-Aviasales-Data-API), [Conditions d'accès](https://support.travelpayouts.com/hc/en-us/articles/203956083-Requirements-for-Aviasales-data-API-access)
