import type { Entry } from "./shared";

// Chat con tu perfil de gusto. Lo que ESCRIBE el agente no vive acá: sale del
// LLM del lado del backend, que recibe el idioma por Accept-Language (ver
// backend/app/llm_client.py). Acá va solo el chrome de la pantalla.

export const CHAT: Record<string, Entry> = {
  "chat.tag": { es: "[Charla]", en: "[Chat]" },
  "chat.titlePrefix": { es: "Hablá con ", en: "Talk to " },
  "chat.titleAccent": { es: "Butaca", en: "Butaca" },
  "chat.intro": {
    es: "Tu experto de cine: preguntale qué ver, detalles, contenido, datos curiosos o discutí una película. También conoce tu gusto.",
    en: "Your film expert: ask what to watch, details, content, trivia, or debate a movie. It also knows your taste.",
  },
  "chat.navLabel": { es: "Charlar", en: "Chat" },
  "chat.navAria": { es: "Charlar con el agente", en: "Chat with the agent" },
  "chat.placeholder": { es: "Preguntá por cualquier película o serie…", en: "Ask about any movie or show…" },
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
    es: "¿Tiene escenas de sexo o violencia Oppenheimer?",
    en: "Does Oppenheimer have sex or violent scenes?",
  },
  "chat.starter2": {
    es: "Contame algo curioso de Parasite sin spoilear",
    en: "Tell me something interesting about Parasite without spoilers",
  },
  "chat.starter3": {
    es: "Tengo dos horas esta noche, tirame algo",
    en: "I've got two hours tonight, hit me with something",
  },
};
