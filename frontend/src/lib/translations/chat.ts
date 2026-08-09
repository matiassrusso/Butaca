import type { Entry } from "./shared";

// Chat con tu perfil de gusto. Lo que ESCRIBE el agente no vive acá: sale del
// LLM del lado del backend, que recibe el idioma por Accept-Language (ver
// backend/app/llm_client.py). Acá va solo el chrome de la pantalla.

export const CHAT: Record<string, Entry> = {
  "chat.tag": { es: "[Charla]", en: "[Chat]" },
  "chat.titlePrefix": { es: "Hablá con ", en: "Talk to " },
  "chat.titleAccent": { es: "Butaca", en: "Butaca" },
  "chat.intro": {
    es: "El mismo agente que escribe tus picks, pero de ida y vuelta. Ya conoce lo que viste y lo que puntuaste.",
    en: "The same agent that writes your picks, only back and forth. It already knows what you've watched and rated.",
  },
  "chat.navLabel": { es: "Charlar", en: "Chat" },
  "chat.navAria": { es: "Charlar con el agente", en: "Chat with the agent" },
  "chat.placeholder": { es: "Escribile algo…", en: "Write something…" },
  "chat.send": { es: "Enviar", en: "Send" },
  "chat.you": { es: "Vos", en: "You" },
  "chat.agent": { es: "Butaca", en: "Butaca" },
  "chat.thinking": { es: "Escribiendo…", en: "Typing…" },
  "chat.error": {
    es: "No pude contestarte esta vez. Probá de nuevo.",
    en: "Couldn't answer this time. Try again.",
  },
  "chat.reset": { es: "Empezar de nuevo", en: "Start over" },
  "chat.starterHint": { es: "Probá con:", en: "Try:" },
  "chat.starter1": {
    es: "Tengo dos horas esta noche, tirame algo",
    en: "I've got two hours tonight, hit me with something",
  },
  "chat.starter2": {
    es: "¿Qué decís de mi gusto? Sé honesto",
    en: "What do you make of my taste? Be honest",
  },
  "chat.starter3": {
    es: "Quiero algo distinto a lo que veo siempre",
    en: "I want something different from my usual",
  },
};
