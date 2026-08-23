// Índice del diccionario ES/EN. Cada pantalla trae su propio módulo para que
// se puedan editar por separado; las claves llevan prefijo de pantalla, así
// que no colisionan entre módulos.

import { AUTH } from "./auth";
import { CHAT } from "./chat";
import { FEEDBACK } from "./feedback";
import { GAMES } from "./games";
import { HISTORY } from "./history";
import { HOME } from "./home";
import { MAP } from "./map";
import { MODAL } from "./modal";
import { PROFILE } from "./profile";
import { RATE } from "./rate";
import { RECOMMEND } from "./recommend";
import { SHARED, type Entry } from "./shared";
import { TOGETHER } from "./together";
import { WRAPPED } from "./wrapped";

export type { Entry };

export const DICTIONARY: Record<string, Entry> = {
  ...SHARED,
  ...AUTH,
  ...HOME,
  ...RECOMMEND,
  ...HISTORY,
  ...PROFILE,
  ...RATE,
  ...GAMES,
  ...CHAT,
  ...FEEDBACK,
  ...MAP,
  ...MODAL,
  ...TOGETHER,
  ...WRAPPED,
};
