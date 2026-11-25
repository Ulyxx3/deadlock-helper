# Architecture Technique — Deadlock Helper

## 1. Principes de conformité VAC

Deadlock Helper n'interagit **jamais** avec le processus `deadlock.exe` :
* Aucune lecture mémoire (`ReadProcessMemory` / RPM).
* Aucune injection de DLL ni hook DirectX/Vulkan.
* Aucune modification des fichiers `.vpk` du jeu.

L'application lit uniquement les pixels affichés à l'écran via l'API système Desktop Duplication / BitBlt (`mss`) lorsque le joueur appuie sur **`TAB`**.

---

## 2. Pipeline d'acquisition (`TAB` → `MatchState`)

```text
Touche TAB (pynput)
   │  délai de stabilisation 120 ms + cooldown 350 ms
   ▼
Capture écran (mss)
   ├── Chrono + 12 cartes joueurs (âmes, pseudo, nom du héros)
   └── Grille d'inventaire 6x2 (bas-gauche) + grilles scoreboard 2x6
   │
   ▼
Vision & OCR
   ├── RapidOCR ONNX (48px + unsharp mask gris) -> âmes + chrono
   ├── HeroMatcher (FR/EN + fuzzy SequenceMatcher, verrouillé par match)
   └── ItemMatcher (vecteurs RGB + Gris + HSV masqués sur les coins)
   │
   ▼
Filtre anti-jitter monotone
   ├── Refuse les baisses impossibles d'âmes (ex: "12400" -> "2400")
   ├── Infère le suffixe "k" manquant en late game (ex: "30" -> 30 000)
   └── Conserve le dernier chrono valide si une frame rate l'horloge
```

### Abstraction `MatchDataProvider`
Valve n'ayant pas encore exposé de *Game State Integration* (GSI) pour Deadlock, `OcrSoulsTracker` implémente `MatchDataProvider` aux côtés d'un stub `GsiProvider`. Si Valve ajoute le GSI plus tard, le reste du moteur (`RecommendationEngine`, serveur WebSocket, frontend) reste inchangé.

---

## 3. Méta & Graphe d'améliorations (`api.deadlock-api.com`)

`DeadlockApiClient` ([backend/meta/deadlock_api_client.py](../backend/meta/deadlock_api_client.py)) consomme les endpoints officiels de Deadlock API avec cache disque TTL (`data/cache/`) et backoff automatique sur `503 Retry-After` :
* `GET /v1/assets/heroes` — Identifiants et noms des héros.
* `GET /v1/assets/items/by-type/upgrade` (`en` et `?language=french`) — Catalogue des items, coûts (`800/1600/3200/6400`), icônes et `component_items`.
* `GET /v1/builds?hero_id=<id>` — Progression complète Early → Mid → Late (jusqu'à 24 items).

---

## 4. Moteur de recommandation (`RecommendationEngine`)

1. **Score Snowball :** `0.65 * (écart_âmes / moyenne_lobby) + 0.25 * puissance_items_clés + 0.10 * modificateur_KD`.
2. **Matchup direct :** Inférence par paires de lane (`slot % 6 // 2 + 1`) ou sélection manuelle en 1 clic (`POST /api/lane-opponents`). Affiche survie/snowball avant 14 min et counters de lane ensuite.
3. **Multi-héros :** Agrège **tous** les ennemis partageant un tag de menace (`lifesteal`, `spirit`, `bullet_carry`, `cc`) et liste chacun d'eux dans l'explication.
4. **Statuts d'amélioration & 12 slots :**
   * `upgrade_ready` (`⬆ AMÉLIO`) : composant déjà dans l'inventaire → coût net affiché (`0 slot en plus`).
   * `owned` (`✔ ACHETÉ`) : item déjà équipé.
   * `evolved` (`✔ ÉVOLUÉ`) : évolution supérieure déjà équipée (fermeture transitive sur `component_items`).
5. **Priorité absolue (`🔥`) :** Sélectionne les 3–4 items les plus rentables à acheter immédiatement selon les menaces fed et le taux de remplissage des 12 slots.
