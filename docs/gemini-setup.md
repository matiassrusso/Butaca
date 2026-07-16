# Setup de Gemini

Ya está conectado. Esta doc es cómo se configuró y cómo funciona hoy.

## Por qué Gemini y no OpenAI

Se evaluó pagar $5 de créditos en OpenAI. Se optó por arrancar gratis con
Gemini (Google AI Studio): free tier real, sin tarjeta, límites razonables
para un MVP. Si en algún momento
la calidad no alcanza o se pega el límite, ahí sí tiene sentido pagar.

## Cómo sacar la API key

1. Entrá a https://aistudio.google.com/apikey con tu cuenta de Google.
2. `Create API key` (no pide tarjeta para el free tier).

Fuente oficial: [Gemini API — Get an API key](https://ai.google.dev/gemini-api/docs/api-key)

## Dónde va

`backend/.env` (gitignored, nunca se commitea):

```
GEMINI_API_KEY=tu-key-acá
```

Template en `backend/.env.example` (sin key real). Se carga con el mismo
loader chico de `.env` que ya usaba `tmdb_client.py` (stdlib, sin sumar
`python-dotenv`).

## Cómo se usa

- [backend/app/llm_client.py](../backend/app/llm_client.py)
  pega contra `:generateContent` (stdlib `urllib`, sin SDK) con
  `responseSchema` para forzar JSON estructurado. Prueba una cadena de
  modelos en orden (`GEMINI_MODELS`: `gemini-flash-latest` →
  `gemini-2.5-flash` → `gemini-3-flash` → `gemini-3.1-flash-lite`) y cae al
  siguiente ante cualquier error del anterior — el free tier de Google AI
  Studio da cuota diaria (RPD) **separada por modelo concreto**, no por el
  alias `-latest`, así que agotar el mejor modelo en un rato de testeo ya no
  tira todo al heurístico: sigue probando modelos con cuota disponible antes
  de rendirse. El último de la cadena (`gemini-3.1-flash-lite`) tiene un
  colchón bastante más grande (500 RPD vs. 20 de los demás) para justamente
  ese caso.
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

## Si Gemini falla o no está configurada

`POST /recommend/zip` y `POST /recommend/letterboxd` devuelven la respuesta
heurística sin romper, igual que con TMDb, y el server loggea un
`Gemini refine failed: ...` con el motivo (antes era un fallback 100%
silencioso — costó una sesión entera de debugging diagnosticar por qué el
"why" nunca variaba). Cae al heurístico si:

- no hay `GEMINI_API_KEY` seteada
- los 4 modelos de la cadena fallan (caídos, timeout, JSON con formato
  inesperado, o cuota diaria agotada en los 4 al mismo tiempo)
- todos los picks que sugiere el modelo que sí respondió quedan afuera de la
  lista de candidatos

Encontrado en vivo: en una red donde la ruta IPv6 hacia
`generativelanguage.googleapis.com` está rota (cuelga sin error hasta el
timeout, en vez de fallar rápido), `llm_client.py` fuerza IPv4 solo para
esta llamada (`_force_ipv4_dns`). Además `gemini-flash-latest` "piensa"
antes de responder (`thoughtSignature` en la respuesta cruda) y tarda
~19-20s incluso en un prompt trivial, por eso `REQUEST_TIMEOUT` es 30s y no
algo más ajustado.

## Tests

Igual que con TMDb: `backend/tests/conftest.py` limpia `GEMINI_API_KEY` del
entorno en cada test por default, así que nunca pegan contra la API real.
Los tests de `llm_client` mockean `_call_gemini` a mano.
