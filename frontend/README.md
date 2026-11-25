# Frontend Companion UI (React + TypeScript + Vite)

Interface **Second Écran / Mode Overlay compact** connectée au serveur FastAPI + WebSocket (`ws://127.0.0.1:8765/ws`).

## Lancement en une commande (production)

Le frontend compilé dans `frontend/dist/` est servi directement par le backend Python :

```powershell
.\.venv\Scripts\python.exe -m backend.main --server
```

Puis ouvrir `http://127.0.0.1:8765`.

## Développement UI (hot-reload Vite)

Terminal 1 :
```powershell
.\.venv\Scripts\python.exe -m backend.main --server --no-live
```

Terminal 2 :
```powershell
cd frontend
npm run dev
```

Vite sert l'UI sur `http://localhost:5173` avec proxy automatique vers `/api`, `/icons` et `/ws`.
