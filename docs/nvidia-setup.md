# Setup de NVIDIA NIM

Ya está conectado. Esta doc es cómo se configuró y cómo funciona hoy.

## Por qué NVIDIA y no Gemini

Se usaba Gemini (Google AI Studio) al principio por el free tier sin
tarjeta, pero el modelo "thinking" (`gemini-flash-latest`) tardaba ~20s por
call sin poder desactivar el razonamiento, y la cuota diaria por modelo se
agotaba rápido en testeo — de ahí la cadena de 4 modelos de fallback que
tenía antes. Se migró a NVIDIA NIM (build.nvidia.com): un solo endpoint
compatible con la API de OpenAI, +100 modelos gratis con una sola key.

## Por qué Nemotron 3 Super y no otro modelo del catálogo

El catálogo NIM tiene tres tamaños de Nemotron 3 (arquitectura MoE híbrida
Mamba-Transformer, propia de NVIDIA, más nueva que la familia
Llama-Nemotron basada en Llama 3.3): Nano (30B total / 3B activos, más
rápido), Super (120B total / 12B activos, el elegido) y Ultra (550B total /
55B activos, frontier). Se priorizó calidad de razonamiento/coherencia sobre
velocidad pura, así que se descartó Nano; y Ultra corre el mismo riesgo de
latencia que tuvo Gemini para una call sincrónica dentro de un request HTTP.
Los tres soportan apagar el razonamiento explícito vía
`chat_template_kwargs.enable_thinking=false` (parámetro real de la API, no
un truco de system prompt) — con eso apagado, ninguno debería acercarse a
los ~20s que costó diagnosticar con Gemini.

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
  Modelo fijo: `nvidia/nemotron-3-super-120b-a12b`, con
  `chat_template_kwargs: {"enable_thinking": false}` en el body para que
  responda directo sin razonar puertas adentro. No usa un modo de JSON
  estructurado (no está garantizado para todos los modelos del catálogo
  NIM) — en cambio, el prompt le pide explícitamente devolver *solo* JSON, y
  `_extract_json` limpia el ```json``` fence si el modelo lo agrega igual.
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
proyecto, pero si empieza a pegar 429 seguido, ahí sí valdría la pena una
cadena de fallback como la que tenía Gemini.

## Tests

Igual que con TMDb: `backend/tests/conftest.py` limpia `NVIDIA_API_KEY` del
entorno en cada test por default, así que nunca pegan contra la API real.
Los tests de `llm_client` mockean `_call_nvidia` a mano.
