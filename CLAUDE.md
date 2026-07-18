@AGENTS.md

# PeliPick

Motor de recomendaciones de pelis y series basado en el gusto real de una persona (import completo del export de Letterboxd), no en promedios genéricos.

## Claude's Role

Avanzar el MVP siguiendo la regla práctica del proyecto: cada iteración debería mover calidad real de recomendación o claridad real del flujo de uso — si no, probablemente es complejidad de más. Coordinar con otros agentes vía `TASKS.md` cuando corresponda.

If a session is drifting without moving hacia calidad de recomendación o claridad de flujo, nudge me back: "¿Esto mejora la calidad del pick o la claridad del flujo? Si no, ¿vale la pena ahora?"

## Process

1. Definición corta del alcance (ver `docs/product-mvp.md`)
2. Implementación en `backend` (FastAPI + SQLite) y/o `frontend` (React + Vite + Tailwind)
3. Si hay varios agentes en paralelo: coordinación por `TASKS.md` (worktrees separados, marcar In Progress → Done, nunca mergear a `main` solo)
4. Tests de backend en verde antes de cerrar (128 tests a la fecha)
5. Deployeado: frontend [pelipick.vercel.app](https://pelipick.vercel.app/) (Vercel), backend [pelipick-backend.onrender.com](https://pelipick-backend.onrender.com) (Render, free tier — cold start en la primera request)

## Key People

Solo yo (Matías), con posible coordinación multi-agente (Claude, Codex) documentada en `TASKS.md`.

## Folder Structure

- `backend/` — FastAPI + SQLite/Postgres: auth (con mail de recuperación vía Resend), catálogo TMDb, agente NVIDIA NIM, import de Letterboxd
- `frontend/` — React + Vite + Tailwind, tema "Hybrid critic notebook" (papel/tinta/terracota, dark mode real, portado desde una iteración en Lovable — ver `DESIGN.md`)
- `docs/` — `product-mvp.md`, `design-directions.md`, `architecture.md`, `mvp-status.md`, `api.md`, `tmdb-setup.md`, `nvidia-setup.md`, `letterboxd-zip-format.md`, `letterboxd-username-import.md`, `build-log.md`
- `00 System/` — scripts/config reusables de este proyecto (vacío por ahora)
- `01 Skills/` — skills en markdown de este proyecto (vacío por ahora)
- `02 Attachments/` — imágenes/screenshots (vacío por ahora)
- `03 Iteration Logs/` — notas de qué mejorar entre iteraciones (vacío por ahora)

## Rules & Conventions

- **`(C)` prefix** — Archivos creados por Claude llevan prefijo `(C)`
- **Editing rule** — Antes de editar un archivo sin el prefijo `(C)`, pedir permiso primero
- **Skills** — Automatizaciones reusables de este proyecto van en `01 Skills/` como markdown, no como Claude Code skills
- **Workflow multi-agente:** leer `TASKS.md` antes de tocar código; marcar tarea In Progress con nombre de agente; al terminar, mover a Done y resumir archivos tocados; nunca mergear a `main` sin avisar
- Requiere `TMDB_API_KEY` y `NVIDIA_API_KEY` en `backend/.env` (ver `docs/tmdb-setup.md` y `docs/nvidia-setup.md`); `RESEND_API_KEY` opcional para mail real de recuperación
- Recuperación de contraseña: manda mail real vía Resend si `RESEND_API_KEY` está seteada; si no, el token solo sale de la respuesta con `PELIPICK_DEBUG=1`

## Current Status

> **Last updated:** 2026-07-18
> **Status:** Activo, MVP deployeado, rediseño visual completo ("Hybrid critic notebook", ver `DESIGN.md` y `docs/mvp-status.md`) — frontend [pelipick.vercel.app](https://pelipick.vercel.app/), backend [pelipick-backend.onrender.com](https://pelipick-backend.onrender.com). 158 tests de backend. Cerrados los 3 pendientes de MVP que quedaban: reporte de filas descartadas del CSV base (`discarded_rows` en `/recommend/zip`), observabilidad mínima (`logging.basicConfig` + log INFO por recomendación completada), y mail real de recuperación de contraseña vía Resend (`backend/app/mailer.py`, campo `email` en `users`, flujo completo en el frontend con `ResetPassword.tsx`) — falta que Matías cree la cuenta de Resend y setee `RESEND_API_KEY` para que funcione en producción. Migrado el agente de IA de Gemini a NVIDIA NIM (`nvidia/nemotron-3-super-120b-a12b`, `chat_template_kwargs.enable_thinking=false`): Gemini tenía un modo "thinking" que no se podía desactivar (~20s por call) y forzaba una cadena de 4 modelos de fallback por cuota diaria; NVIDIA da un solo endpoint compatible con OpenAI, +100 modelos gratis con una key, y este modelo (familia Nemotron 3, más nueva que la Llama-Nemotron original) permite apagar el razonamiento vía un parámetro real de la API sin perder calidad de instruction-following.

Detalle completo en `docs/mvp-status.md`.
