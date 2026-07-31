import { ExternalLink, Film, Loader2 } from "lucide-react";
import { useEffect, useState, type MutableRefObject } from "react";
import { createPortal } from "react-dom";

import { API_BASE_URL } from "@/hooks/useAuth";
import { isUnknownMatch } from "@/lib/match";

export type FeedbackStatus = "interested" | "not_interested" | "seen";

export type Recommendation = {
  id: number;
  tmdb_id: number | null;
  title: string;
  year: number;
  kind: string;
  why: string;
  match_score: number;
  tags: string[];
  // director solo lo trae /recommend; /history no, por eso es opcional
  director?: string | null;
  poster_path: string | null;
  backdrop_path: string | null;
  overview: string;
  vote_average: number | null;
};

type Provider = { name: string; logo_path: string | null };

export type MovieDetails = {
  cast: { name: string; character: string; profile_path: string | null }[];
  trailer_key: string | null;
  providers: {
    link: string | null;
    flatrate: Provider[];
    rent: Provider[];
    buy: Provider[];
  } | null;
};

// pedido de Matías: revelar el "why" con efecto máquina de escribir, pero
// solo la primera vez que se abre CADA poster en la sesión — reabrir el
// mismo (o que el "why" no haya cambiado) muestra el texto completo directo.
// El deps array es [recId, why] a propósito: el propio setDisplayed dispara
// re-renders en cada tick, y si el effect dependiera de algo que cambia en
// esos re-renders (ej. un booleano derivado del ref en cada render) el
// typewriter se cortaría al primer caracter.
function useTypewriterWhy(
  recId: number,
  why: string,
  seenWhys?: MutableRefObject<Map<number, string>>
): string {
  const [displayed, setDisplayed] = useState(why);

  useEffect(() => {
    const alreadySeen = seenWhys?.current.get(recId) === why;
    const reducedMotion =
      typeof window !== "undefined" && window.matchMedia?.("(prefers-reduced-motion: reduce)").matches;

    if (alreadySeen || reducedMotion || !seenWhys) {
      setDisplayed(why);
      return;
    }

    setDisplayed("");
    let shown = 0;
    const id = setInterval(() => {
      shown += 1;
      setDisplayed(why.slice(0, shown));
      if (shown >= why.length) {
        clearInterval(id);
        // se marca "visto" al terminar, no al empezar: StrictMode corre este
        // effect 2 veces en dev (monta → cleanup → monta de nuevo) — si se
        // marcara al empezar, la 2da pasada ya lo encontraría "visto" y
        // saltearía la animación real entera (interrumpirlo cerrando el
        // modal a mitad de camino sí puede hacer que se re-anime al
        // reabrir — aceptable, mejor que perder la animación siempre)
        seenWhys.current.set(recId, why);
      }
    }, 18);
    return () => clearInterval(id);
  }, [recId, why, seenWhys]);

  return displayed;
}

// mismo vocabulario que el modo manual "Sin cuenta" (Recommend.tsx) — un
// rating sintético elegido de un menú, no un puntaje preciso que el usuario
// haya tipeado
const RATE_OPTIONS: { label: string; value: number }[] = [
  { label: "Me encantó", value: 4.5 },
  { label: "Bien", value: 3.5 },
  { label: "No me gustó", value: 1.5 },
];

type SimilarTitle = { title: string; year: number; kind: string; tmdb_id: number | null; poster_path: string | null };

export function MovieModal({
  rec,
  token,
  feedback,
  seenWhys,
  onClose,
  onFeedback,
  onRate,
}: {
  rec: Recommendation;
  token: string | null;
  feedback?: FeedbackStatus;
  // ref compartida entre pósters (vive en la página que abre el modal) con
  // el último "why" ya mostrado por rec.id — sin esto (ej. Home.tsx) el
  // modal muestra el texto completo directo, sin animación, como antes
  seenWhys?: MutableRefObject<Map<number, string>>;
  onClose: () => void;
  onFeedback: (status: FeedbackStatus) => void;
  // pedido de Matías (2026-07-31): "Ya la vi" ahora ofrece puntuar directo
  // (me encantó/bien/no me gustó) en vez de solo marcarla vista, así queda
  // en el perfil para futuras recomendaciones. title/tmdbId opcionales: el
  // botón "no estoy de acuerdo" reusa este mismo callback para votar
  // similares, que no son rec — sin ellos, puntúa rec.title.
  onRate: (rating: number, title?: string, tmdbId?: number | null) => void;
}) {
  const [details, setDetails] = useState<MovieDetails | null>(null);
  const [showRateMenu, setShowRateMenu] = useState(false);
  const [loadingDetails, setLoadingDetails] = useState(false);
  const displayedWhy = useTypewriterWhy(rec.id, rec.why, seenWhys);

  // pedido de Matías (2026-07-31): "no estoy de acuerdo con el match" — si
  // el motivo es no tener nada puntuado de esa saga/género (ej. ama a
  // Spider-Man pero nunca votó nada de esa franquicia), esto le muestra
  // similares de TMDb para votar y arreglar esa laguna en el perfil.
  const [showDisagree, setShowDisagree] = useState(false);
  const [similar, setSimilar] = useState<SimilarTitle[] | null>(null);
  const [loadingSimilar, setLoadingSimilar] = useState(false);
  const [votedSimilar, setVotedSimilar] = useState<Set<string>>(new Set());

  function toggleDisagree() {
    setShowDisagree((v) => !v);
    if (similar !== null || rec.tmdb_id == null || !token) return;
    setLoadingSimilar(true);
    fetch(`${API_BASE_URL}/movies/${rec.tmdb_id}/similar?kind=${encodeURIComponent(rec.kind)}`, {
      headers: { Authorization: `Bearer ${token}` },
    })
      .then((response) => (response.ok ? response.json() : null))
      .then((body: { titles: SimilarTitle[] } | null) => setSimilar(body?.titles ?? []))
      .catch(() => setSimilar([]))
      .finally(() => setLoadingSimilar(false));
  }

  useEffect(() => {
    const previousOverflow = document.body.style.overflow;
    document.body.style.overflow = "hidden";
    return () => {
      document.body.style.overflow = previousOverflow;
    };
  }, []);

  useEffect(() => {
    let cancelled = false;
    setDetails(null);

    if (rec.tmdb_id == null || !token) {
      setLoadingDetails(false);
      return;
    }

    setLoadingDetails(true);
    fetch(`${API_BASE_URL}/movies/${rec.tmdb_id}/details?kind=${encodeURIComponent(rec.kind)}`, {
      headers: { Authorization: `Bearer ${token}` },
    })
      .then((response) => {
        if (!response.ok) throw new Error();
        return response.json() as Promise<MovieDetails>;
      })
      .then((body) => {
        if (!cancelled) setDetails(body);
      })
      .catch(() => undefined)
      .finally(() => {
        if (!cancelled) setLoadingDetails(false);
      });

    return () => {
      cancelled = true;
    };
  }, [rec.tmdb_id, rec.kind, token]);

  const btn = "flex-1 py-3 font-mono text-[10px] uppercase tracking-widest border transition-colors";

  return createPortal(
    <div
      className="fixed inset-0 z-[100] bg-foreground/60 backdrop-blur-sm flex items-start justify-center p-6 overflow-y-auto"
      onClick={onClose}
    >
      <div
        className="bg-background max-w-4xl w-full mt-12 mb-12 border-2 border-foreground"
        onClick={(e) => e.stopPropagation()}
      >
        <div className="flex justify-between items-baseline border-b-2 border-foreground px-6 py-4">
          <span className="font-mono text-[10px] uppercase tracking-widest">
            [Detail] · {rec.id}
          </span>
          <button onClick={onClose} className="font-mono text-xs hover:text-accent">
            [close ×]
          </button>
        </div>
        <div className="grid grid-cols-1 md:grid-cols-5 gap-8 p-6">
          <div className="md:col-span-2">
            {rec.poster_path ? (
              <img
                src={rec.poster_path}
                alt={rec.title}
                className="w-full aspect-[2/3] object-cover outline outline-1 -outline-offset-1 outline-black/10"
              />
            ) : (
              <div className="w-full aspect-[2/3] bg-secondary flex items-center justify-center">
                <Film className="w-10 h-10 text-muted-foreground/40" />
              </div>
            )}
          </div>
          <div className="md:col-span-3 flex flex-col">
            <h2 className="text-4xl md:text-5xl font-black uppercase tracking-tighter leading-[0.9] mb-4">
              {rec.title}
            </h2>
            <div className="font-mono text-xs text-muted-foreground uppercase tracking-widest mb-6">
              {rec.year}
              {rec.kind === "series" ? " · Serie" : ""}
              {rec.vote_average != null ? ` · ★ ${rec.vote_average.toFixed(1)}` : ""}
              {" · "}
              {isUnknownMatch(rec.match_score) ? "Match desconocido" : `${rec.match_score}% match`}
              {rec.tmdb_id != null && token && (
                <button
                  onClick={toggleDisagree}
                  className="ml-2 normal-case tracking-normal underline decoration-dotted hover:text-accent"
                >
                  ¿No estás de acuerdo?
                </button>
              )}
            </div>
            <p className="font-serif text-2xl italic leading-snug text-balance mb-6">
              &ldquo;{displayedWhy}
              {displayedWhy.length < rec.why.length && (
                <span className="inline-block w-2 h-5 -mb-0.5 ml-0.5 bg-accent animate-pulse" />
              )}
              &rdquo;
            </p>

            {rec.tags.length > 0 && (
              <div className="flex flex-wrap gap-2 mb-6">
                {rec.tags.map((tag) => (
                  <span key={tag} className="font-mono text-[10px] uppercase px-2 py-1 border border-foreground/20">
                    {tag}
                  </span>
                ))}
              </div>
            )}

            {rec.overview && (
              <p className="text-sm text-muted-foreground leading-relaxed mb-6">{rec.overview}</p>
            )}

            {showDisagree && (
              <div className="border-t border-foreground/10 pt-4 mb-6">
                <p className="font-mono text-[10px] uppercase tracking-widest text-muted-foreground mb-3">
                  Votá similares para que el match mejore
                </p>
                {loadingSimilar ? (
                  <div className="flex items-center gap-2 font-mono text-[10px] uppercase tracking-widest text-muted-foreground">
                    <Loader2 className="w-3.5 h-3.5 animate-spin" />
                    Buscando similares...
                  </div>
                ) : similar && similar.length > 0 ? (
                  <div className="space-y-3">
                    {similar.map((item) => (
                      <div key={item.tmdb_id ?? item.title} className="flex items-center justify-between gap-3">
                        <span className="text-sm">
                          {item.title} <span className="text-muted-foreground">({item.year})</span>
                        </span>
                        {votedSimilar.has(item.title) ? (
                          <span className="font-mono text-[10px] uppercase text-accent">¡Gracias!</span>
                        ) : (
                          <div className="flex gap-1 shrink-0">
                            {RATE_OPTIONS.map((opt) => (
                              <button
                                key={opt.label}
                                onClick={() => {
                                  onRate(opt.value, item.title, item.tmdb_id);
                                  setVotedSimilar((prev) => new Set(prev).add(item.title));
                                }}
                                className="px-2 py-1 font-mono text-[9px] uppercase border border-foreground/30 hover:border-accent hover:text-accent transition-colors"
                              >
                                {opt.label}
                              </button>
                            ))}
                          </div>
                        )}
                      </div>
                    ))}
                  </div>
                ) : (
                  <p className="text-sm text-muted-foreground">No encontré similares para votar.</p>
                )}
              </div>
            )}

            {loadingDetails && (
              <div className="border-t border-foreground/10 pt-4 mb-6 flex items-center gap-2 font-mono text-[10px] uppercase tracking-widest text-muted-foreground">
                <Loader2 className="w-3.5 h-3.5 animate-spin" />
                Cargando reparto y tráiler...
              </div>
            )}

            {details && (details.cast.length > 0 || details.trailer_key) && (
              <div className="border-t border-foreground/10 pt-4 mb-6">
                {details.trailer_key && (
                  <a
                    href={`https://www.youtube.com/watch?v=${details.trailer_key}`}
                    target="_blank"
                    rel="noreferrer"
                    className="mb-4 inline-flex items-center gap-2 px-4 py-2 border border-foreground/30 font-mono text-[10px] uppercase tracking-widest hover:border-accent hover:text-accent transition-colors"
                  >
                    <Film className="w-3.5 h-3.5" />
                    Ver tráiler
                    <ExternalLink className="w-3 h-3" />
                  </a>
                )}
                {details.cast.length > 0 && (
                  <>
                    <div className="font-mono text-[10px] uppercase tracking-widest text-muted-foreground mb-2">
                      Cast
                    </div>
                    <div className="text-sm">
                      {details.cast.map((c) => c.name).join(" · ")}
                    </div>
                  </>
                )}
              </div>
            )}

            {details?.providers && (
              <div className="border-t border-foreground/10 pt-4 mb-6">
                <div className="font-mono text-[10px] uppercase tracking-widest text-muted-foreground mb-2 flex items-center gap-2">
                  Dónde verla
                  {details.providers.link && (
                    <a
                      href={details.providers.link}
                      target="_blank"
                      rel="noreferrer"
                      className="inline-flex items-center gap-1 hover:text-accent"
                    >
                      <ExternalLink className="w-3 h-3" />
                    </a>
                  )}
                </div>
                {details.providers.flatrate.length > 0 || details.providers.rent.length > 0 || details.providers.buy.length > 0 ? (
                  <>
                    {details.providers.flatrate.length > 0 && (
                      <div className="flex flex-wrap gap-2 mb-2">
                        {details.providers.flatrate.map((prov) => (
                          <span
                            key={prov.name}
                            className="inline-flex items-center gap-1.5 font-mono text-[10px] uppercase px-2 py-1 border border-foreground/20"
                          >
                            {prov.logo_path && <img src={prov.logo_path} alt="" className="w-4 h-4" />}
                            {prov.name}
                          </span>
                        ))}
                      </div>
                    )}
                    {[...new Set([...details.providers.rent, ...details.providers.buy].map((p) => p.name))].length > 0 && (
                      <div className="font-mono text-[10px] text-muted-foreground">
                        Alquiler/compra:{" "}
                        {[...new Set([...details.providers.rent, ...details.providers.buy].map((p) => p.name))].join(" · ")}
                      </div>
                    )}
                  </>
                ) : (
                  <div className="font-mono text-[10px] text-muted-foreground">
                    No está en streaming en Argentina ahora.
                  </div>
                )}
                <div className="font-mono text-[9px] text-muted-foreground/50 mt-2">Datos de JustWatch</div>
              </div>
            )}

            <div className="mt-auto pt-4 border-t border-foreground/10">
              <p className="font-mono text-[10px] uppercase tracking-widest text-muted-foreground mb-3">
                ¿Qué te parece este pick?
              </p>
              <div className="flex gap-2">
                <button
                  onClick={() => onFeedback("interested")}
                  className={`${btn} ${feedback === "interested" ? "bg-foreground text-background border-foreground" : "border-foreground/30 hover:border-foreground"}`}
                >
                  Me interesa
                </button>
                <button
                  onClick={() => setShowRateMenu((v) => !v)}
                  className={`${btn} ${feedback === "seen" ? "bg-secondary border-foreground" : "border-foreground/30 hover:border-foreground"}`}
                >
                  Ya la vi
                </button>
                <button
                  onClick={() => onFeedback("not_interested")}
                  className={`${btn} ${feedback === "not_interested" ? "bg-accent text-accent-foreground border-accent" : "border-foreground/30 hover:border-foreground"}`}
                >
                  No me interesa
                </button>
              </div>
              {showRateMenu && (
                <div className="mt-3 border-t border-foreground/10 pt-3">
                  <p className="font-mono text-[10px] uppercase tracking-widest text-muted-foreground mb-2">
                    ¿Qué te pareció?
                  </p>
                  <div className="flex gap-2">
                    {RATE_OPTIONS.map((opt) => (
                      <button
                        key={opt.label}
                        onClick={() => {
                          onRate(opt.value);
                          onFeedback("seen");
                          setShowRateMenu(false);
                        }}
                        className={`${btn} border-foreground/30 hover:border-accent hover:text-accent`}
                      >
                        {opt.label}
                      </button>
                    ))}
                  </div>
                </div>
              )}
            </div>
          </div>
        </div>
      </div>
    </div>,
    document.body,
  );
}
