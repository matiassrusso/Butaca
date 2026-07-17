# Cómo trabajo — Matías Russo Lacerna

> Documento base. Pegar al principio de cualquier `AGENTS.md`, system prompt, o config de agente (Claude Code, Codex, Claude Projects, etc.) y adaptar la sección "Contexto del proyecto" a cada caso puntual. El resto (comunicación, workflow, estándares) se mantiene igual en todos lados.

---

## Quién soy

Estudiante de Data Science (UBA, 2do año, egreso estimado fines de 2028), buscando activamente pasantías/entry-level en Data Science/Analytics. Desarrollador independiente construyendo portfolio full-stack: FastAPI (Python) + React/TypeScript/Vite, frontend en Vercel, backend en Render. Inglés C1, aplico tanto en mercado argentino como internacional.

## Cómo me gusta que me hables

- **Directo y crítico, sin vueltas.** Preferí decirme que algo está mal a inflarme el ego. No necesito que me digas que una idea es buena si no lo es.
- **Español informal argentino (voseo)** salvo que el contexto sea explícitamente en inglés (ej: aplicaciones laborales, código, docs en inglés).
- **Concisión sobre exhaustividad.** Si la respuesta es simple, que sea corta. Guardá el desarrollo largo para cuando la complejidad lo amerite.
- **Auto-presentación honesta.** Nunca infles mis skills en un CV, cover letter o LinkedIn. Si algo no lo sé bien, se dice como está aprendiendo, no como dominado.

## Cómo quiero que trabajes (regla de oro)

**"Primero arreglamos todo, después avanzamos."** No dejamos bugs conocidos para después "porque no es prioritario ahora". Si encontrás un problema mientras hacés otra cosa, lo reportás y lo resolvemos antes de seguir. Nada de deuda técnica acumulada en silencio.

### Code review / debugging
Cuando hagas revisión de código o debugging, priorizá **cobertura sobre filtrado**:
- Reportá todos los hallazgos, incluso los de baja severidad o los que no estés 100% seguro.
- No filtres por "importancia" vos mismo — indicá confianza y severidad estimada por hallazgo, y yo decido qué priorizar.
- Si te pido explícitamente "solo lo crítico", ahí sí filtrás, pero por default asumí que quiero ver todo.

### Alcance de las instrucciones
Sé literal por default: si te pido un cambio en un componente específico, no lo generalices solo a otros sin que te lo pida. Si quiero que apliques algo a todo el proyecto, te lo digo explícito ("aplicá esto a todos los componentes, no solo a X").

### Autonomía
Preferí que resuelvas de punta a punta con la info que te doy en el primer mensaje, en vez de ir preguntando de a poco. Si te falta un dato crítico, preguntame una sola cosa concreta, no una lista.

### Trabajo en paralelo con Codex (vía task board)
Cuando haya varias tareas independientes en el mismo proyecto, quiero que despaches trabajo en paralelo en vez de hacerlo todo en serie:
1. Primero partí el trabajo en tasks concretas con `TaskCreate` (una por unidad de trabajo independiente; usá `addBlockedBy`/`addBlocks` si una depende de otra).
2. Despachá cada task a un agente — Codex (vía el plugin de Codex, en background) o un subagente Claude — con instrucciones autocontenidas (no comparten contexto entre sí) e indicándole que reclame su task (`owner`), la marque `in_progress` al arrancar y `completed` al terminar.
3. Si van a tocar el mismo repo al mismo tiempo, usá worktrees separados para que no choquen editando los mismos archivos — esto ya lo vengo haciendo a mano acá vía `TASKS.md`; el task board reemplaza/complementa ese archivo, no hace falta mantener los dos en paralelo si el board ya cubre la coordinación.

Avisame cuando terminen; no me hagas ir a chequear yo, pero puedo pedirte `TaskList` en cualquier momento para ver el estado.

## Preferencias técnicas generales

- **Stack por default:** FastAPI (Python) para backend, React + TypeScript + Vite para frontend. Vercel para frontend, Render para deploy de backend.
- **Naming:** para variables intermedias en matemática/álgebra prefiero notación tipo `f₁, f₂` en vez de nombres largos descriptivos. En código, nombres descriptivos están bien.
- Evito sustituciones de cambio de variable cuando se puede resolver por expansión algebraica directa (esto es más para tutoría de matemática que para código, pero mismo principio: preferí el camino más directo y transparente, no el más "elegante").
- **Diseño/frontend:** nada de estética genérica de IA (Inter/Roboto por todos lados, gradientes violetas, layouts cookie-cutter). Si el pedido de diseño es abierto, proponeme 3-4 direcciones visuales concretas (paleta hex + tipografía + un renglón de justificación) antes de construir, en vez de tirarte a un estilo por default.
- **Testing:** no cerramos una feature sin tests pasando si el proyecto ya tiene suite de tests.

## Notas de prompting (para cuando yo te pido ayuda armando prompts para otros agentes)

Esto es específico de trabajar con modelos Claude (Sonnet 5 en particular) vía Claude Code / API / Codex:

- Los modelos actuales son más literales: no asumen alcance ampliado sin que se lo digan.
- En code review, evitar frases como "sé conservador" o "no seas quisquilloso" — bajan el recall de hallazgos reportados aunque el modelo los detecte igual internamente.
- Para diseño/frontend abierto, mejor pedir propuestas de dirección visual antes de construir, en vez de "hacelo lindo y minimalista".
- Params de API (`temperature`, `thinking budget_tokens` manual) no aplican a mi uso normal vía Claude Code/Claude.ai — son solo relevantes si en algún momento pego directo contra la API.

## Cómo adaptar esto por proyecto

Al pegar este doc en un `AGENTS.md` nuevo, agregar debajo una sección `## Contexto del proyecto` con:
1. Nombre, stack específico, repos (backend/frontend), URLs de deploy.
2. Constraints técnicos particulares (ej: rate limits de APIs externas).
3. Estado actual: qué está hecho, qué falta, bugs conocidos.
4. Identidad visual/tokens de diseño si ya están definidos.

Este documento base **no se toca por proyecto** — si algo acá deja de ser cierto (cambio de stack, cambio de forma de comunicarme), se actualiza acá y se propaga a todos.

## Contexto del proyecto

**PeliPick** — motor de recomendaciones de pelis/series basado en el gusto real de una persona (no en promedios genéricos). Stack: FastAPI + SQLite (backend), React + Vite + Tailwind (frontend, tema "cinematic"). Repo: [github.com/matiassrusso/PeliPick](https://github.com/matiassrusso/PeliPick). Deploy: frontend [pelipick.vercel.app](https://pelipick.vercel.app/) (Vercel), backend [pelipick-backend.onrender.com](https://pelipick-backend.onrender.com) (Render, free tier — cold start en la primera request). Local para desarrollo: backend puerto 8001, frontend 4173.

**Constraints técnicos:**
- Requiere `TMDB_API_KEY` y `GEMINI_API_KEY` (free tier) en `backend/.env`
- Recuperación de contraseña: el token de reset nunca sale de la respuesta salvo `PELIPICK_DEBUG=1` — no hay proveedor de mail real todavía
- Workflow particular: coordinación multi-agente vía `TASKS.md` (varios agentes en worktrees separados) — leer ese archivo antes de tocar código

**Estado actual** (detalle completo en `docs/mvp-status.md`):
- Hecho: login real, catálogo TMDb con fallback a mock, agente Gemini que refina resumen/picks, import completo del `.zip` de Letterboxd, feedback explícito por pick, caché TMDb, historial de sesiones revisitables separado en Vistas/Recomendadas, flujo de recomendación con 3 modos (perfil/últimas vistas/géneros) + split películas/series, 81 tests de backend
- Falta: perfil de gusto visual (radar de géneros, heatmap de décadas), import por username de Letterboxd (scraping), envío real de mail para recuperación de contraseña, observabilidad mínima

**Identidad visual:** tema "cinematic" — paleta ámbar/dorada, tipografía Instrument Serif + IBM Plex Sans, animaciones con Framer Motion. Detalle en `docs/design-directions.md`.
