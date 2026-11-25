# FAQ — Deadlock Helper

### Est-ce que cet outil peut provoquer un ban VAC ?
Non. L'outil est **100 % externe** : il ne lit pas la mémoire du jeu, n'injecte aucune DLL, ne modifie aucun fichier de Deadlock et n'automatise aucune action en jeu. Il prend uniquement des captures d'écran standard lorsque vous pressez `TAB`.

### Est-ce compatible avec `DeadlockModManager` (skins personnalisés) ?
Oui. Même si vos mods remplacent les portraits 2D des héros sur le scoreboard, la reconnaissance des 12 héros repose sur l'**OCR des noms textuels** (avec dictionnaire FR/EN et fuzzy matching) et non sur les portraits.

### Quel est l'impact sur les FPS ?
Quasi nul. Tant que vous ne maintenez pas `TAB`, l'application est en attente passive (~0 % CPU). Lors d'un appui sur `TAB`, le découpage et l'OCR complet prennent quelques dizaines de millisecondes sur un thread séparé.

### Pourquoi `Matchup direct` affiche parfois d'autres héros que mes adversaires de lane ?
Par défaut, l'ordre des cartes en haut du scoreboard correspond souvent aux lanes initiales (`slots 0-1 vs 6-7`, etc.), mais ce n'est pas garanti si les joueurs échangent. Vous pouvez **cliquer directement sur 1 ou 2 héros ennemis** dans la barre supérieure de l'interface pour épingler votre vrai matchup de lane (`LANE`).

### Pourquoi Valve GSI n'est-il pas utilisé ?
Valve n'a pas encore publié de *Game State Integration* (GSI) pour Deadlock. L'architecture inclut déjà l'interface abstraite `MatchDataProvider` pour basculer vers le GSI dès sa sortie officielle.
