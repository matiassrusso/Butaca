# Commands & Skills

Quick reference for all available skills and commands in this project.

## Skills (in XX Skills/)
_No project-specific skills yet._ Workflow particular: coordinación multi-agente vía `TASKS.md` (ver ese archivo antes de tocar código).

## Commands

### Correr local

```powershell
# Backend (puerto 8001 — 8000 suele estar ocupado en esta máquina)
cd backend
py -m pip install -r requirements.txt
py -m uvicorn backend.app.main:app --reload --host 127.0.0.1 --port 8001

# Frontend
cd frontend
npm.cmd install
npm.cmd run dev -- --host 127.0.0.1 --port 4173
```

Requiere `TMDB_API_KEY` y `NVIDIA_API_KEY` en `backend/.env` (ver `docs/tmdb-setup.md` y `docs/nvidia-setup.md`).
