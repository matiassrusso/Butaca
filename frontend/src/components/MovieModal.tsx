import { ExternalLink, Film, Loader2 } from "lucide-react";
import { useEffect, useState } from "react";
import { createPortal } from "react-dom";

import { API_BASE_URL } from "@/hooks/useAuth";

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

export function MovieModal({
  rec,
  token,
  feedback,
  onClose,
  onFeedback,
}: {
  rec: Recommendation;
  token: string | null;
  feedback?: FeedbackStatus;
  onClose: () => void;
  onFeedback: (status: FeedbackStatus) => void;
}) {
  const [details, setDetails] = useState<MovieDetails | null>(null);
  const [loadingDetails, setLoadingDetails] = useState(false);

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
              {rec.match_score}% match
            </div>
            <p className="font-serif text-2xl italic leading-snug text-balance mb-6">
              &ldquo;{rec.why}&rdquo;
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
                  onClick={() => onFeedback("seen")}
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
            </div>
          </div>
        </div>
      </div>
    </div>,
    document.body,
  );
}
