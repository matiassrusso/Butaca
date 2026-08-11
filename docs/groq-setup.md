# Setup de Groq (fallback opcional)

Ya está conectado en código. Esta doc es cómo se configuró y por qué.

## Por qué Groq

Los dos modelos de NVIDIA NIM (`docs/nvidia-setup.md`) comparten host: cuando
NVIDIA free-tier se degrada, los afecta a los dos por igual, y `/recommend`
cae siempre al heurístico (visto en producción el 2026-08-11 — hasta un
prompt trivial tardaba 14-20s). Groq corre en hardware propio (LPU, pensado
para latencia baja) en vez de GPU compartida, así que una degradación de
NVIDIA no debería tocarlo. API compatible con OpenAI, mismo formato de
request que NVIDIA NIM — el fallback reusa `_call_nvidia` con otra URL.

Es el tercer intento de la cadena, después de agotar los dos de NVIDIA. Es
opcional: si `GROQ_API_KEY` no está seteada, `_call_nvidia_with_fallback` lo
salta sin error y el comportamiento es igual al de antes.

## Cómo sacar la API key

1. Entrá a https://console.groq.com/keys con una cuenta (Google/GitHub, sin
   tarjeta para el free tier).
2. Generá una key (empieza con `gsk_`).

## Dónde va

`backend/.env` (gitignored, nunca se commitea):

```
GROQ_API_KEY=tu-key-acá
```

Y en Render: env var del servicio `butaca-backend`, mismo criterio que
`NVIDIA_API_KEY` (cambiarla no dispara redeploy solo, hace falta uno manual).

## Modelo elegido

`llama-3.3-70b-versatile` — tamaño comparable al fallback actual de NVIDIA
(`meta/llama-3.1-70b-instruct`), buen equilibrio calidad/velocidad en el
catálogo de Groq. Si en el futuro Groq deja de ofrecerlo, ver
https://console.groq.com/docs/models por el reemplazo vigente.
