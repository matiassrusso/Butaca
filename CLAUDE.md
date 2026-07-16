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
5. Todavía sin deploy — se corre y valida local

## Key People

Solo yo (Matías), con posible coordinación multi-agente (Claude, Codex) documentada en `TASKS.md`.

## Folder Structure

- `backend/` — FastAPI + SQLite: auth, catálogo TMDb, agente Gemini, import de Letterboxd
- `frontend/` — React + Vite + Tailwind, tema "cinematic"
- `docs/` — `product-mvp.md`, `design-directions.md`, `architecture.md`, `mvp-status.md`, `api.md`, `tmdb-setup.md`, `gemini-setup.md`, `letterboxd-zip-format.md`, `letterboxd-username-import.md`, `build-log.md`
- `00 System/` — scripts/config reusables de este proyecto (vacío por ahora)
- `01 Skills/` — skills en markdown de este proyecto (vacío por ahora)
- `02 Attachments/` — imágenes/screenshots (vacío por ahora)
- `03 Iteration Logs/` — notas de qué mejorar entre iteraciones (vacío por ahora)

## Rules & Conventions

- **`(C)` prefix** — Archivos creados por Claude llevan prefijo `(C)`
- **Editing rule** — Antes de editar un archivo sin el prefijo `(C)`, pedir permiso primero
- **Skills** — Automatizaciones reusables de este proyecto van en `01 Skills/` como markdown, no como Claude Code skills
- **Workflow multi-agente:** leer `TASKS.md` antes de tocar código; marcar tarea In Progress con nombre de agente; al terminar, mover a Done y resumir archivos tocados; nunca mergear a `main` sin avisar
- Requiere `TMDB_API_KEY` y `GEMINI_API_KEY` en `backend/.env`
- Recuperación de contraseña: el token nunca sale de la respuesta salvo `PELIPICK_DEBUG=1` (no hay proveedor de mail real todavía)

## Current Status

> **Last updated:** 2026-07-15
> **Status:** Activo, MVP funcional local. 128 tests de backend. Import por username de Letterboxd (scraping del diario público vía `curl_cffi`, porque Cloudflare bloquea el stdlib `urllib`/`requests` por fingerprint TLS) commiteado y pusheado. Recién arreglados varios bugs de calidad de recomendación reportados en vivo: un bonus ciego por rating≥4.5 que inflaba "humor/tono liviano" en casi todas las razones sin importar el contenido real, ausencia total de señal de gusto para el import por username, el discover de TMDb ordenado por `popularity.desc` (sesgaba a estrenos), y — la causa de fondo por la que el agente Gemini nunca corría — IPv6 roto en esta red hacia el endpoint de Google, timeout de 15s insuficiente para el modo "thinking" de `gemini-flash-latest` (~19-20s reales), y cupo diario agotado por modelo (ahora con cadena de fallback `gemini-flash-latest` → `gemini-2.5-flash` → `gemini-3-flash` → `gemini-3.1-flash-lite`). Sin commitear todavía.

Detalle completo en `docs/mvp-status.md`. Pendiente: reportar filas descartadas del CSV base, envío real de mail para recuperación de contraseña, observabilidad mínima.
