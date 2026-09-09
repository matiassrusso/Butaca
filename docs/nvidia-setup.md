# Setup de NVIDIA NIM

Ya está conectado. Esta doc es cómo se configuró y cómo funciona hoy.

## Por qué NVIDIA y no Gemini

Se usaba Gemini (Google AI Studio) al principio por el free tier sin
tarjeta, pero el modelo "thinking" (`gemini-flash-latest`) tardaba ~20s por
call sin poder desactivar el razonamiento, y la cuota diaria por modelo se
agotaba rápido en testeo — de ahí la cadena de 4 modelos de fallback que
tenía antes. Se migró a NVIDIA NIM (build.nvidia.com): un solo endpoint
compatible con la API de OpenAI, +100 modelos gratis con una sola key.

## Qué modelos se usan y por qué (actualizado 2026-08-11)

El catálogo NIM tiene ~130 modelos. La elección original (Nemotron 3 Super,
120B/12B activos) se descartó tras medir en vivo: junto con el fallback de
entonces (`llama-3.1-70b-instruct`), estaba consistentemente congestionado —
timeouts en producción, hasta 20s en tests directos. Se testearon los 102
modelos con endpoint de chat del catálogo (latencia + el prompt real de
refine, no un "decí OK") y los modelos "famosos" resultaron ser justo los
más pedidos por todo el mundo y por eso los más lentos; variantes más
nuevas o menos conocidas responden rápido con calidad pareja o mejor. Razón
completa del orden elegido y de qué se descartó (con números): comentario
arriba de `NVIDIA_MODELS` en `llm_client.py`.

**Desde el 2026-09-09 NVIDIA está fuera de la cadena sincrónica del LLM**
(`NVIDIA_MODELS = []`): `lightning-30b` timeoutea siempre, `super-120b`
tarda 18-20s, y varios (`nano-30b`, `llama-3.1-8b`, `llama-3.3-70b`) fueron
retirados con 410 Gone. El proveedor primario es Groq (`docs/groq-setup.md`).
La key de NVIDIA sigue haciendo falta para los **embeddings** del mapa de
vibras (`vibes_clustering.py`). Si algún día un modelo NIM vuelve a servir,
basta con listarlo en `NVIDIA_MODELS`: los Nemotron soportan apagar el
razonamiento vía `chat_template_kwargs.enable_thinking=false` (parámetro
real de la API, no un truco de system prompt) y `_call_nvidia` lo manda por
prefijo de nombre — sin eso, un modelo de esta familia puede tardar 15-20s
razonando puertas adentro antes de contestar.

## Cómo sacar la API key

1. Entrá a https://build.nvidia.com/settings/api-keys con una cuenta NVIDIA.
2. Generá una key (empieza con `nvapi-`, no pide tarjeta para el free tier).

## Dónde va

`backend/.env` (gitignored, nunca se commitea):

```
NVIDIA_API_KEY=tu-key-acá
```

Template en `backend/.env.example` (sin key real). Se carga con el mismo
loader chico de `.env` que ya usaba `tmdb_client.py` (stdlib, sin sumar
`python-dotenv`).

## Cómo se usa

- [backend/app/llm_client.py](../backend/app/llm_client.py)
  pega contra `https://integrate.api.nvidia.com/v1/chat/completions`
  (stdlib `urllib`, sin SDK), formato de chat completions estándar de OpenAI.
  Cadena de proveedores: primero `GROQ_MODELS` con `GROQ_API_KEY`
  (`docs/groq-setup.md`), después `NVIDIA_MODELS` (hoy vacía) con
  `NVIDIA_API_KEY` — un intento por modelo, en orden, hasta que alguno
  responda. Con `response_format: json_object` en el body (medido: sin esto,
  ~1 de cada 3 refines devolvía JSON casi-válido y caía al heurístico),
  `chat_template_kwargs: {"enable_thinking": false}` para los Nemotron y
  `reasoning_effort: "low"` para los gpt-oss de Groq. Siempre con header
  `User-Agent` propio (Groq bloquea el default de urllib con 403). `_extract_json` limpia el ```json``` fence si
  el modelo lo agrega igual.
- Recibe el historial parseado del CSV, el mood y los candidatos que ya
  filtró el recomendador heurístico (`recommend()` en
  [recommender.py](../backend/app/recommender.py)).
- Le pide al modelo que elija y ordene como máximo 5 de esos candidatos
  (nunca inventa títulos nuevos — se descarta cualquier pick que no matchee
  por título exacto contra la lista) y que escriba un `taste_summary` y un
  `why` por pick más personalizados que los heurísticos.
- El resto de cada recomendación (score, tags, póster, overview) viene sin
  tocar del heurístico — el LLM solo reordena y reescribe texto, no inventa
  metadata.

## Si NVIDIA falla o no está configurada

`POST /recommend/zip` y `POST /recommend/letterboxd` devuelven la respuesta
heurística sin romper, igual que con TMDb, y el server loggea un
`LLM refine failed: ...` con el motivo. Cae al heurístico si:

- no hay `NVIDIA_API_KEY` seteada
- la call falla (red, timeout, JSON con formato inesperado)
- todos los picks que sugiere el modelo quedan afuera de la lista de
  candidatos

El free tier de NVIDIA NIM comparte un tope de ~40 requests/min entre todos
los modelos de la key — no debería ser un problema para el volumen de este
proyecto. Para congestión (no 429, sino latencia/timeout de un modelo
puntual) ya existe la cadena de fallback descrita arriba.

## Tests

Igual que con TMDb: `backend/tests/conftest.py` limpia `NVIDIA_API_KEY` del
entorno en cada test por default, así que nunca pegan contra la API real.
Los tests de `llm_client` mockean `_call_nvidia` a mano.
