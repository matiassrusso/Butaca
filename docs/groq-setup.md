# Setup de Groq (proveedor LLM primario desde 2026-09-09)

Ya está conectado en código. Esta doc es cómo se configuró, por qué, y qué
se creyó mal durante un mes.

## Por qué Groq va primero

Medido el 2026-09-09 con el prompt real de refine (perfil de ~40 títulos +
12 candidatos, ~2.500 tokens), 3 corridas por modelo:

| Modelo | Latencia | Picks válidos | Español |
|---|---|---|---|
| Groq `qwen/qwen3.8-27b` | 2-3s | 6/6 | el mejor rioplatense por lejos |
| Groq `openai/gpt-oss-120b` (`reasoning_effort: low`) | 1,6-1,8s | 6/6 | bueno; a veces cita candidatos como "ya vistos" |
| Groq `openai/gpt-oss-20b` (low) | 1,1s | 6/6 | tutea, repite plantillas |
| NVIDIA `nemotron-3-super-120b` | 18-20s (1 timeout) | 6/6 | Spanglish |
| NVIDIA `nemotron-3.5-lightning-30b` (el de prod hasta ese día) | timeout 3/3 | — | — |

Groq corre en hardware propio (LPU) pensado para latencia baja; NVIDIA NIM
free-tier es GPU compartida y los modelos conocidos viven congestionados. La
cadena real es `GROQ_MODELS` en `llm_client.py` (qwen → gpt-oss-120b →
gpt-oss-20b); `NVIDIA_MODELS` quedó vacía a propósito, y la key de NVIDIA
sigue haciendo falta para los embeddings del mapa de vibras
(`vibes_clustering.py`).

## El 403 que costó un mes: era el User-Agent

Desde el 2026-08-11 Groq devolvía `403 Forbidden` desde producción y se lo
atribuyó a un bloqueo de IPs de hosting (Cloudflare filtrando Render). Era
mentira: `urllib.request` sin header `User-Agent` manda `Python-urllib/3.x`, y
Cloudflare de Groq lo bloquea desde **cualquier** IP. Verificado con la misma
key y el mismo request: `curl` con UA default → 200, `curl -A
"Python-urllib/3.14"` → 403. Nadie lo vio porque en los sandboxes se probaba
con curl/requests, que mandan un UA aceptable. `_call_nvidia` ahora manda
`User-Agent: butaca/1.0`. Regla: cualquier cliente HTTP nuevo con urllib en
este proyecto setea `User-Agent`, y antes de decir "X bloquea a Render" hay
que reproducir desde local con el MISMO cliente.

Aparte, `llama-3.3-70b-versatile` (el modelo que estaba configurado) ya no
existe en Groq (404 `model_not_found`). Catálogo vigente:
https://console.groq.com/docs/models.

## Cuotas del free tier (medidas en headers, 2026-09-09)

Por modelo, y cada modelo es un bucket **independiente** con la misma key:
30 RPM, 8K TPM, 1K RPD, 200K TPD. Un refine son ~3K tokens → ~2 por minuto y
~65 por día por modelo, ~190/día entre los tres. `qwen3.8-27b` tiene además
un límite no documentado de 1.000 tokens de salida por minuto → un refine
por minuto; el segundo da 429 y la cadena pasa a gpt-oss-120b en 0,1s. El
uso real de Butaca hoy es 30-50 refines/día, así que entra sobrado; el tope
teórico del producto (20/día × todos los usuarios) no.

Si algún día aprieta: Groq Dev Tier (pago por uso, estimado ~USD 4/mes para
10 usuarios × 20 rec/día) mantiene el mismo código y la calidad ya medida —
conviene antes que sumar OpenAI.

## Detalles de request que importan

- `response_format: {"type": "json_object"}` anda en los tres modelos.
- gpt-oss son modelos con razonamiento: `reasoning_effort: "low"` (lo manda
  `_call_nvidia` por prefijo de nombre) y **sin `max_tokens` chico** — el
  razonamiento consume el presupuesto y json_object falla con 400
  `json_validate_failed`.
- Un 429 vuelve en 0,1s: no se duerme ni se reintenta el mismo modelo, se
  pasa al siguiente bucket.
- Timeout 6s (`REQUEST_TIMEOUT`): Groq responde en 1-3s o falla rápido.

## Cómo sacar la API key

1. Entrá a https://console.groq.com/keys con una cuenta (Google/GitHub, sin
   tarjeta para el free tier).
2. Generá una key (empieza con `gsk_`).

## Dónde va

`backend/.env` (gitignored, nunca se commitea):

```
GROQ_API_KEY=tu-key-acá
```

Y en Render: env var del servicio, mismo criterio que `NVIDIA_API_KEY`
(cambiarla no dispara redeploy solo, hace falta uno manual). Sin
`GROQ_API_KEY` y con `NVIDIA_MODELS` vacía no hay proveedor: `/recommend`
sigue andando con el why heurístico y loguea `no hay proveedor LLM
configurado`.
