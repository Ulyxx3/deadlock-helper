# Deadlock Helper

[![CI](https://github.com/Ulyxx3/deadlock-helper/actions/workflows/ci.yml/badge.svg)](https://github.com/Ulyxx3/deadlock-helper/actions/workflows/ci.yml)
[![License: MIT](https://img.shields.io/badge/License-MIT-e6b35a.svg)](LICENSE)
[![Python 3.11+](https://img.shields.io/badge/Python-3.11%2B-3776ab.svg)](requirements.txt)
[![React + TypeScript](https://img.shields.io/badge/UI-React%20%2B%20TypeScript-61dafb.svg)](frontend/)
[![VAC-Safe](https://img.shields.io/badge/Anti--Cheat-100%25%20VAC--Safe-5db868.svg)](docs/faq.md)
[![GitHub Pages](https://img.shields.io/badge/Docs-GitHub%20Pages-7cf0d8.svg)](https://ulyxx3.github.io/deadlock-helper/)

**Assistant compagnon en temps réel pour Deadlock (Valve)** — 100 % externe (aucune lecture mémoire, aucune injection DLL, aucune modification des fichiers du jeu).

**[🌐 Site vitrine & Documentation GitHub Pages](https://ulyxx3.github.io/deadlock-helper/)**

---

## Fonctionnalités clés

* **100 % VAC-Safe & Zéro lag :** Déclenchement événementiel uniquement lorsque tu maintiens **`TAB`** (`pynput` + capture ciblée `mss` + `RapidOCR` ONNX). ~0 % CPU pendant les teamfights.
* **Compatible skins custom (`DeadlockModManager`) :** Reconnaissance des 12 héros par OCR sur les noms (FR/EN + fuzzy matching) et verrouillage en début de partie — insensible aux portraits moddés.
* **Détection des items & suivi des 12 slots :** Reconnaissance vectorisée d'icônes (masquage des badges de palier `II`/`III`/`IV`) sur ta grille d'inventaire `6×2` et sur le scoreboard `2×6`.
* **Arbre d'améliorations officiel & Builds évolutifs (`api.deadlock-api.com`) :**
  * Charge les vrais builds **Early → Mid → Late** de ton héros et le graphe complet des `component_items`.
  * Badges **`⬆ AMÉLIO`** (affiche le coût net et signale `0 slot en plus`), **`✔ ACHETÉ`** et **`✔ ÉVOLUÉ`**.
* **Moteur Snowball & Multi-héros :**
  * Identifie les ennemis *fed* via l'écart d'âmes à la moyenne et leurs power spikes.
  * Chaque counter liste **tous les héros adverses ciblés** (`Contre Pocket (+1 602), Paradox, Lady Geist...`).
  * Barre **`🔥 Priorité absolue`** tout en haut pour savoir immédiatement quoi acheter ensuite.
* **Interface Second Écran / Mode Overlay sans scroll (`FR 🇫🇷 / EN 🇬🇧`) :** 4 colonnes compactes sur `100vh`, clic direct sur un ennemi pour épingler ton matchup de lane, et switch instantané Français / Anglais.

---

## Installation rapide (Windows)

```powershell
git clone https://github.com/Ulyxx3/deadlock-helper.git
cd deadlock-helper

# 1. Backend Python
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.txt

# 2. Frontend React (compilé dans frontend/dist)
cd frontend
npm install
npm run build
cd ..
```

## Lancement

```powershell
.\.venv\Scripts\python.exe -m backend.main --server
```

Ouvre ensuite **`http://127.0.0.1:8765`** dans ton navigateur (sur ton second écran ou en fenêtre compacte **Overlay**).

### Autres modes CLI

* **Synchroniser les icônes d'items en cache local :**
  ```powershell
  .\.venv\Scripts\python.exe -m backend.main --sync-assets
  ```
* **Tester sur une capture d'écran avec export de calibration :**
  ```powershell
  .\.venv\Scripts\python.exe -m backend.main --image images\ta_capture.png --player TonPseudo --dump-rois data\debug_captures
  ```
* **Lancer la suite de tests :**
  ```powershell
  .\.venv\Scripts\python.exe -m pytest -v
  ```

---

## Documentation détaillée (`/docs`)

* [Architecture technique & Pipeline OCR / Snowball](docs/architecture.md)
* [Guide de calibration des ROIs (`rois.json`)](docs/calibration.md)
* [FAQ (VAC, Skins DeadlockModManager, Performances)](docs/faq.md)

---

*Projet communautaire non officiel. Non affilié à Valve Corporation. Deadlock™ est une marque de Valve Corporation.*
