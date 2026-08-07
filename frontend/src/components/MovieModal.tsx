import { ExternalLink, Film, Loader2 } from "lucide-react";
import { useEffect, useState, type MutableRefObject } from "react";
import { createPortal } from "react-dom";

import { API_BASE_URL } from "@/hooks/useAuth";
import { useLang } from "@/lib/i18n";
import { isUnknownMatch } from "@/lib/match";
import { StarRating } from "@/components/StarRating";

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
  // false cuando el LLM inventó un título fuera de la lista de candidatos y
  // este pick es relleno heurístico tal cual (2026-08-03, TASKS.md)
  refined: boolean;
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
  user_rating: number | null;
  rating_source: "import" | "manual" | "like" | "star" | "game" | null;
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

type SimilarTitle = { title: string; year: number; kind: string; tmdb_id: number | null; poster_path: string | null };

// cuántas opiniones hacen falta para recalcular el match (pedido de Matías,
// 2026-07-31: "que tengas que reunir 6 votos de 6 películas distintas")
const VOTES_NEEDED = 6;

// Panel de "no estoy de acuerdo con el match". Va de a UNA película por vez,
// con su póster, y en dos pasos: primero si la viste, y recién si la viste
// pregunta qué te pareció. Antes era una lista plana sin opción de "no la vi",
// así que un título que no habías visto te trababa el flujo.
function DisagreePanel({
  rec,
  token,
  onRate,
  onEnoughVotes,
}: {
  rec: Recommendation;
  token: string | null;
  onRate: (rating: number, title: string, tmdbId: number | null) => Promise<boolean>;
  onEnoughVotes: () => void;
}) {
  const { t } = useLang();
  const [pool, setPool] = useState<SimilarTitle[] | null>(null);
  const [index, setIndex] = useState(0);
  const [votes, setVotes] = useState(0);
  const [step, setStep] = useState<"seen" | "rating">("seen");
  const [saving, setSaving] = useState(false);
  const [ratingDraft, setRatingDraft] = useState<number | null>(null);

  useEffect(() => {
    if (rec.tmdb_id == null || !token) {
      setPool([]);
      return;
    }
    let cancelled = false;
    fetch(`${API_BASE_URL}/movies/${rec.tmdb_id}/similar?kind=${encodeURIComponent(rec.kind)}`, {
      headers: { Authorization: `Bearer ${token}` },
    })
      .then((response) => (response.ok ? response.json() : null))
      .then((body: { titles: SimilarTitle[] } | null) => {
        if (!cancelled) setPool(body?.titles ?? []);
      })
      .catch(() => {
        if (!cancelled) setPool([]);
      });
    return () => {
      cancelled = true;
    };
  }, [rec.tmdb_id, rec.kind, token]);

  const current = pool?.[index];

  function next() {
    setIndex((i) => i + 1);
    setStep("seen");
    setRatingDraft(null);
  }

  async function vote(rating: number) {
    if (!current) return;
    setRatingDraft(rating);
    setSaving(true);
    const saved = await onRate(rating, current.title, current.tmdb_id);
    setSaving(false);
    if (!saved) {
      setRatingDraft(null);
      return;
    }
    const total = votes + 1;
    setVotes(total);
    if (total >= VOTES_NEEDED) {
      onEnoughVotes();
      return;
    }
    next();
  }

  if (pool === null) {
    return (
      <div className="flex items-center gap-2 font-mono text-[10px] uppercase tracking-widest text-muted-foreground">
        <Loader2 className="w-3.5 h-3.5 animate-spin" />
        {t("modal.similarLoading")}
      </div>
    );
  }

  // check directo sobre `current`, no un booleano derivado: acá `pool` ya no
  // es null (early return de arriba), así que esto es exactamente el mismo
  // caso "me quedé sin títulos" — pero TypeScript solo estrecha el tipo con
  // la forma directa, y con la variable intermedia el build fallaba con
  // "'current' is possibly undefined" en todo el JSX de abajo.
  if (!current) {
    return (
      <div className="space-y-3">
        <p className="text-sm text-muted-foreground">
          {votes === 0
            ? t("modal.noSimilar")
            : votes === 1
              ? t("modal.outOfSimilarOne")
              : t("modal.outOfSimilarMany", { n: votes })}
        </p>
        {votes > 0 && (
          <button
            onClick={onEnoughVotes}
            className="w-full py-2 font-mono text-[10px] uppercase tracking-widest border border-foreground/30 hover:border-accent hover:text-accent transition-colors"
          >
            {t("modal.recalcAnyway")}
          </button>
        )}
      </div>
    );
  }

  return (
    <div className="space-y-3">
      <div className="flex items-center justify-between font-mono text-[9px] uppercase tracking-widest text-muted-foreground">
        <span>{t("modal.adjustMatch")}</span>
        <span className="text-accent">
          {votes}/{VOTES_NEEDED}
        </span>
      </div>

      <div className="flex gap-3">
        {current.poster_path ? (
          <img
            src={current.poster_path}
            alt={current.title}
            className="w-16 aspect-[2/3] object-cover shrink-0 outline outline-1 -outline-offset-1 outline-black/10"
          />
        ) : (
          <div className="w-16 aspect-[2/3] bg-secondary flex items-center justify-center shrink-0">
            <Film className="w-5 h-5 text-muted-foreground/40" />
          </div>
        )}
        <div className="min-w-0">
          <p className="font-medium leading-tight">{current.title}</p>
          <p className="font-mono text-[10px] text-muted-foreground">
            {current.year}
            {current.kind === "series" ? ` · ${t("common.show")}` : ""}
          </p>
        </div>
      </div>

      {step === "seen" ? (
        <>
          <p className="font-mono text-[10px] uppercase tracking-widest text-muted-foreground">
            {t("modal.seenIt")}
          </p>
          <div className="flex gap-2">
            <button
              onClick={() => setStep("rating")}
              className="flex-1 py-2 font-mono text-[10px] uppercase tracking-widest border border-foreground/30 hover:border-accent hover:text-accent transition-colors"
            >
              {t("modal.yesSaw")}
            </button>
            <button
              onClick={next}
              className="flex-1 py-2 font-mono text-[10px] uppercase tracking-widest border border-foreground/30 hover:border-foreground transition-colors"
            >
              {t("modal.notSeen")}
            </button>
          </div>
        </>
      ) : (
        <>
          <p className="font-mono text-[10px] uppercase tracking-widest text-muted-foreground">
            {t("modal.whatDidYouThink")}
          </p>
          <StarRating value={ratingDraft} onChange={vote} disabled={saving} size="sm" />
        </>
      )}
    </div>
  );
}

export function MovieModal({
  rec,
  token,
  feedback,
  seenWhys,
  onClose,
  onFeedback,
  onRate,
  readOnly = false,
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
  // "Ya la vi" ofrece puntuar directo con estrellas, así queda
  // en el perfil para futuras recomendaciones. title/tmdbId opcionales: el
  // botón "no estoy de acuerdo" reusa este mismo callback para votar
  // similares, que no son rec — sin ellos, puntúa rec.title.
  onRate: (rating: number, title?: string, tmdbId?: number | null) => Promise<boolean>;
  readOnly?: boolean;
}) {
  const { t, lang } = useLang();
  const [details, setDetails] = useState<MovieDetails | null>(null);
  const [showRateMenu, setShowRateMenu] = useState(false);
  const [ratingDraft, setRatingDraft] = useState<number | null>(null);
  const [ratingSaving, setRatingSaving] = useState(false);
  const [loadingDetails, setLoadingDetails] = useState(false);

  // "no estoy de acuerdo con el match": después de juntar VOTES_NEEDED
  // opiniones se recalcula contra el perfil ya actualizado. El resultado se
  // guarda acá y pisa lo que muestra el modal, en vez de avisarle a la página
  // que lo abrió — así no hay que tocar los cuatro lugares que lo usan.
  const [showDisagree, setShowDisagree] = useState(false);
  const [recalculated, setRecalculated] = useState<Recommendation | null>(null);
  const [recalculating, setRecalculating] = useState(false);

  const shown = recalculated ?? rec;
  const displayedWhy = useTypewriterWhy(shown.id, shown.why, seenWhys);

  function recalculate() {
    if (rec.tmdb_id == null || !token) return;
    setRecalculating(true);
    fetch(`${API_BASE_URL}/titles/${rec.tmdb_id}/verdict?kind=${encodeURIComponent(rec.kind)}&lang=${lang}`, {
      headers: { Authorization: `Bearer ${token}` },
    })
      .then((response) => (response.ok ? response.json() : null))
      .then((body: (Omit<Recommendation, "id"> & { id: number | null }) | null) => {
        if (body) setRecalculated({ ...body, id: body.id ?? rec.id });
        setShowDisagree(false);
      })
      .catch(() => setShowDisagree(false))
      .finally(() => setRecalculating(false));
  }

  async function saveRating(rating: number) {
    setRatingDraft(rating);
    setRatingSaving(true);
    const saved = await onRate(rating);
    setRatingSaving(false);
    if (saved) {
      onFeedback("seen");
      setShowRateMenu(false);
    } else {
      setRatingDraft(null);
    }
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
    fetch(
      `${API_BASE_URL}/movies/${rec.tmdb_id}/details?kind=${encodeURIComponent(rec.kind)}&title=${encodeURIComponent(rec.title)}`,
      {
        headers: { Authorization: `Bearer ${token}` },
      },
    )
      .then((response) => {
        if (!response.ok) throw new Error();
        return response.json() as Promise<MovieDetails>;
      })
      .then((body) => {
        if (!cancelled) {
          setDetails(body);
          if (body.rating_source === "import" || body.rating_source === "star") {
            setRatingDraft(body.user_rating);
          }
        }
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
              {shown.year}
              {shown.kind === "series" ? ` · ${t("common.show")}` : ""}
              {shown.vote_average != null ? ` · ★ ${shown.vote_average.toFixed(1)}` : ""}
              {" · "}
              {recalculating ? (
                <span className="text-accent">{t("modal.recalculating")}</span>
              ) : isUnknownMatch(shown.match_score) ? (
                t("match.unknown")
              ) : (
                `${shown.match_score}% match`
              )}
              {rec.tmdb_id != null && token && !readOnly && !recalculating && (
                <span className="relative inline-block">
                  <button
                    onClick={() => setShowDisagree((v) => !v)}
                    aria-expanded={showDisagree}
                    className="ml-2 normal-case tracking-normal underline decoration-dotted hover:text-accent"
                  >
                    {t("modal.disagree")}
                  </button>
                  {showDisagree && (
                    <div className="absolute left-0 top-full mt-2 z-10 w-72 p-4 border-2 border-foreground bg-background shadow-2xl normal-case tracking-normal text-foreground">
                      <DisagreePanel
                        rec={rec}
                        token={token}
                        onRate={onRate}
                        onEnoughVotes={recalculate}
                      />
                    </div>
                  )}
                </span>
              )}
            </div>
            <p className="font-serif text-2xl italic leading-snug text-balance mb-6">
              &ldquo;{displayedWhy}
              {displayedWhy.length < shown.why.length && (
                <span className="inline-block w-2 h-5 -mb-0.5 ml-0.5 bg-accent animate-pulse" />
              )}
              &rdquo;
            </p>

            {shown.tags.length > 0 && (
              <div className="flex flex-wrap gap-2 mb-6">
                {shown.tags.map((tag) => (
                  <span key={tag} className="font-mono text-[10px] uppercase px-2 py-1 border border-foreground/20">
                    {tag}
                  </span>
                ))}
              </div>
            )}

            {shown.overview && (
              <p className="text-sm text-muted-foreground leading-relaxed mb-6">{shown.overview}</p>
            )}

            {loadingDetails && (
              <div className="border-t border-foreground/10 pt-4 mb-6 flex items-center gap-2 font-mono text-[10px] uppercase tracking-widest text-muted-foreground">
                <Loader2 className="w-3.5 h-3.5 animate-spin" />
                {t("modal.loadingDetails")}
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
                    {t("modal.watchTrailer")}
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

            {!readOnly && <div className="mt-auto pt-4 border-t border-foreground/10">
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
                  <StarRating
                    value={ratingDraft}
                    onChange={saveRating}
                    disabled={ratingSaving || details?.rating_source === "import"}
                  />
                  {details?.rating_source === "import" && (
                    <p className="mt-2 border border-accent/40 bg-accent/10 p-2 font-mono text-[9px] uppercase leading-relaxed text-accent">
                      Este rating viene de Letterboxd y tiene prioridad. Para cambiarlo,
                      actualizalo ahí y volvé a importar.
                    </p>
                  )}
                </div>
              )}
            </div>}
          </div>
        </div>
      </div>
    </div>,
    document.body,
  );
}
