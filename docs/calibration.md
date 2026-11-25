# Guide de calibration (`rois.json`)

Les coordonnées par défaut dans [backend/config/rois.json](../backend/config/rois.json) sont normalisées entre `0.0` et `1.0` pour un écran **16:9** (`1920×1080`, `2560×1440`, etc.).

## Vérifier votre alignement sur une capture réelle

1. Lancez une partie (ou le mode Entraînement), maintenez **`TAB`** et prenez une capture d'écran PNG dans `images/test.png`.
2. Exécutez :
   ```powershell
   .\.venv\Scripts\python.exe -m backend.main --image images\test.png --player VotrePseudo --dump-rois data\debug_captures
   ```
3. Ouvrez `data\debug_captures\scoreboard_rois_overlay.png` :
   * Les boîtes **ambre/bleues** doivent encadrer uniquement les chiffres d'âmes (sans mordre sur la bordure verticale du badge).
   * La boîte **verte** en haut au centre doit encadrer le chronomètre (`MM:SS`).
   * Les boîtes en bas à gauche doivent encadrer les icônes `6×2` de votre inventaire.

## Ajuster manuellement un écran ultrawide (21:9) ou un changement de HUD

Modifiez les valeurs normalisées (`x`, `y`, `w`, `h`) dans [backend/config/rois.json](../backend/config/rois.json), puis relancez `--image ... --dump-rois data\debug_captures` pour valider le cadrage.

## Mettre à jour le cache d'icônes après un patch Deadlock

```powershell
.\.venv\Scripts\python.exe -m backend.main --sync-assets
```
