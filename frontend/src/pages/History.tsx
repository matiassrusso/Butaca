import { Film, Loader2 } from "lucide-react";
import { useEffect, useState } from "react";
import { useLocation } from "wouter";

import { PageTransition } from "@/components/PageTransition";
import { API_BASE_URL, useAuth } from "@/hooks/useAuth";
import { isUnknownMatch } from "@/lib/match";

type Recommendation = {
  id: number;
  title: string;
  year: number;
  kind: string;
  why: string;
  match_score: number;
  tags: string[];
  poster_path: string | null;
  backdrop_path: string | null;
  overview: string;
  vote_average: number | null;
};

type RecommendationSession = {
  id: number;
  mood: string;
  taste_summary: string;
  created_at: string;
  recommendations: Recommendation[];
};

type WatchedItem = {
  title: string;
  rating: number;
  review: string;
  created_at: string;
  watched_date: string;
  source: "import" | "manual" | "like";
};

function formatSessionDate(value: string): string {
  const date = new Date(`${value}Z`);
  return Number.isNaN(date.getTime())
    ? value
    : date.toLocaleString("es-AR", { dateStyle: "medium", timeStyle: "short" });
}

// watched_date is a bare date (no time), unlike created_at — formatting it
// through formatSessionDate would read it as UTC midnight and shift it to
// the previous day in timezones behind UTC (e.g. Argentina), so this keeps
// the display in UTC to match the literal date the user picked
function formatWatchedDate(value: string): string {
  if (!value) return "";
  const date = new Date(`${value}T00:00:00Z`);
  return Number.isNaN(date.getTime())
    ? value
    : date.toLocaleDateString("es-AR", { dateStyle: "medium", timeZone: "UTC" });
}

function stars(rating: number): string {
  return "★".repeat(Math.floor(rating)) + (rating % 1 ? "½" : "");
}

// los ratings "manual"/"like" son sintéticos (botón de Butaca, no estrellas
// puestas en Letterboxd) — mostrarlos como estrellas 1-5 sería un dato
// inventado, mismo criterio que ya se usa en el "why" del LLM (ver
// llm_client._rating_label en el backend)
function ratingLabel(rating: number): string {
  if (rating >= 4) return "Te encantó";
  if (rating <= 2) return "No te gustó";
  return "Te gustó";
}

function sourceLabel(source: WatchedItem["source"]): string {
  return source === "import" ? "Letterboxd" : "Butaca";
}

export default function History() {
  const { isAuthenticated, loading: authLoading, token } = useAuth();
  const [, navigate] = useLocation();
  const [tab, setTab] = useState<"recommended" | "watched">("watched");
  const [sessions, setSessions] = useState<RecommendationSession[]>([]);
  const [watchedItems, setWatchedItems] = useState<WatchedItem[]>([]);
  const [openSession, setOpenSession] = useState<number | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  const [openReview, setOpenReview] = useState<string | null>(null);

  useEffect(() => {
    if (!authLoading && !isAuthenticated) {
      navigate("/login");
    }
  }, [authLoading, isAuthenticated, navigate]);

  useEffect(() => {
    if (!token) {
      setLoading(false);
      return;
    }

    let cancelled = false;
    setLoading(true);
    setError("");

    fetch(`${API_BASE_URL}/history${tab === "watched" ? "/watched" : ""}`, {
      headers: { Authorization: `Bearer ${token}` },
    })
      .then(async (response) => {
        if (!response.ok) {
          const body = await response.json().catch(() => null);
          throw new Error(body?.detail ?? "No pude cargar tu historial.");
        }
        return response.json();
      })
      .then((body) => {
        if (!cancelled) {
          if (tab === "watched") {
            setWatchedItems(body.items ?? []);
          } else {
            const list: RecommendationSession[] = body.sessions ?? [];
            setSessions(list);
            setOpenSession(list[0]?.id ?? null);
          }
        }
      })
      .catch((err) => {
        if (!cancelled) setError(err instanceof Error ? err.message : "No pude cargar tu historial.");
      })
      .finally(() => {
        if (!cancelled) setLoading(false);
      });

    return () => {
      cancelled = true;
    };
  }, [token, tab]);

  if (authLoading || !isAuthenticated) {
    return (
      <div className="min-h-screen flex items-center justify-center">
        <Loader2 className="w-8 h-8 animate-spin text-accent" />
      </div>
    );
  }

  const tabCls = (active: boolean) =>
    `px-6 py-3 font-mono text-xs uppercase tracking-widest border-b-2 transition-colors ${
      active ? "border-foreground text-foreground" : "border-transparent text-muted-foreground hover:text-foreground"
    }`;

  return (
    <PageTransition>
      <main className="max-w-7xl mx-auto px-6 pt-16 pb-24">
        <header className="pb-8 border-b-2 border-foreground mb-8">
          <div className="font-mono text-[10px] uppercase tracking-widest text-muted-foreground mb-4">
            [Archive]
          </div>
          <h1 className="text-6xl md:text-7xl font-black uppercase tracking-tighter leading-[0.9]">
            Tu <span className="text-accent italic font-serif normal-case tracking-normal">bitácora</span>
          </h1>
        </header>

        <div className="flex gap-0 border-b border-foreground/20 mb-12">
          <button onClick={() => setTab("watched")} className={tabCls(tab === "watched")}>
            [Vistas]
          </button>
          <button onClick={() => setTab("recommended")} className={tabCls(tab === "recommended")}>
            [Recomendadas]
          </button>
        </div>

        {loading && (
          <div className="py-20 text-center">
            <Loader2 className="w-7 h-7 text-accent animate-spin mx-auto mb-4" />
            <p className="font-mono text-xs uppercase text-muted-foreground">Cargando tu historial...</p>
          </div>
        )}

        {!loading && error && (
          <div className="p-4 border-2 border-destructive/50 font-mono text-xs text-destructive">{error}</div>
        )}

        {!loading && !error && tab === "watched" && watchedItems.length === 0 && (
          <div className="p-10 border-2 border-dashed border-foreground/20 text-center">
            <h2 className="text-2xl font-black uppercase tracking-tighter mb-2">
              Todavía no importaste vistas
            </h2>
            <p className="font-mono text-xs uppercase text-muted-foreground">
              Subí tu export de Letterboxd para verlas acá.
            </p>
          </div>
        )}

        {!loading && !error && tab === "watched" && watchedItems.length > 0 && (
          <table className="w-full">
            <thead>
              <tr className="font-mono text-[10px] uppercase tracking-widest text-muted-foreground border-b border-foreground/20">
                <th className="text-left py-3 w-12">#</th>
                <th className="text-left py-3">Título</th>
                <th className="text-left py-3 hidden sm:table-cell">Vista</th>
                <th className="text-left py-3 hidden md:table-cell">Dónde</th>
                <th className="text-right py-3">Rating</th>
              </tr>
            </thead>
            <tbody>
              {watchedItems.map((item, i) => {
                const rowKey = `${item.title}-${item.created_at}`;
                const reviewOpen = openReview === rowKey;
                return (
                  <tr key={rowKey} className="border-b border-foreground/5 hover:bg-foreground/[0.03]">
                    <td className="py-4 font-mono text-xs text-muted-foreground">{String(i + 1).padStart(2, "0")}</td>
                    <td className="py-4">
                      <div className="font-medium">{item.title}</div>
                      {item.review && (
                        <>
                          <button
                            onClick={() => setOpenReview(reviewOpen ? null : rowKey)}
                            className="mt-1 font-mono text-[9px] uppercase tracking-widest text-accent underline decoration-dotted"
                          >
                            {reviewOpen ? "Ocultar reseña" : "Tu reseña"}
                          </button>
                          {reviewOpen && (
                            <div className="text-xs text-muted-foreground mt-1 max-w-md">{item.review}</div>
                          )}
                        </>
                      )}
                    </td>
                    <td className="py-4 hidden sm:table-cell font-mono text-xs text-muted-foreground">
                      {item.watched_date ? formatWatchedDate(item.watched_date) : formatSessionDate(item.created_at)}
                    </td>
                    <td className="py-4 hidden md:table-cell font-mono text-xs text-muted-foreground">
                      {sourceLabel(item.source)}
                    </td>
                    <td className="py-4 text-right font-mono text-sm text-accent">
                      {item.source === "import" ? stars(item.rating) : ratingLabel(item.rating)}
                    </td>
                  </tr>
                );
              })}
            </tbody>
          </table>
        )}

        {!loading && !error && tab === "recommended" && sessions.length === 0 && (
          <div className="p-10 border-2 border-dashed border-foreground/20 text-center">
            <h2 className="text-2xl font-black uppercase tracking-tighter mb-2">Todavía no generaste picks</h2>
            <p className="font-mono text-xs uppercase text-muted-foreground mb-5">
              Cuando hagas tu primera sesión de recomendaciones, va a aparecer acá.
            </p>
            <button
              onClick={() => navigate("/recommend")}
              className="inline-flex items-center gap-2 px-6 py-3 bg-accent text-accent-foreground font-mono text-xs uppercase tracking-widest hover:bg-foreground hover:text-background transition-colors"
            >
              Ir a recomendar
            </button>
          </div>
        )}

        {!loading && !error && tab === "recommended" && sessions.length > 0 && (
          <div className="space-y-6">
            {sessions.map((session) => {
              const isOpen = openSession === session.id;
              return (
                <div key={session.id} className="border-2 border-foreground/10 hover:border-foreground/40 transition-colors">
                  <button
                    onClick={() => setOpenSession(isOpen ? null : session.id)}
                    className="w-full flex flex-wrap items-baseline justify-between gap-4 p-6 text-left"
                  >
                    <div className="flex items-baseline gap-6 flex-wrap">
                      <span className="font-mono text-xs text-accent">[SESIÓN {session.id}]</span>
                      <span className="font-mono text-xs text-muted-foreground uppercase tracking-widest">
                        {formatSessionDate(session.created_at)}
                      </span>
                      <span className="text-lg font-medium">{session.mood || "sin filtro"}</span>
                    </div>
                    <div className="flex items-baseline gap-4">
                      <span className="font-mono text-xs text-muted-foreground">
                        {session.recommendations.length} picks
                      </span>
                      <span className="font-mono text-xs">{isOpen ? "[−]" : "[+]"}</span>
                    </div>
                  </button>
                  {isOpen && (
                    <div className="border-t border-foreground/10 p-6 pt-6">
                      <p className="font-mono text-[10px] uppercase tracking-widest text-muted-foreground mb-6 max-w-3xl">
                        {session.taste_summary}
                      </p>
                      <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-8">
                        {session.recommendations.map((rec) => (
                          <article key={rec.id}>
                            <div className="mb-4 relative overflow-hidden">
                              {rec.poster_path ?? rec.backdrop_path ? (
                                <img
                                  src={rec.poster_path ?? rec.backdrop_path ?? undefined}
                                  alt={rec.title}
                                  className="w-full aspect-[2/3] object-cover"
                                />
                              ) : (
                                <div className="w-full aspect-[2/3] bg-secondary flex items-center justify-center">
                                  <Film className="w-8 h-8 text-muted-foreground/40" />
                                </div>
                              )}
                              <div className="absolute top-2 right-2 px-2 py-1 bg-accent text-accent-foreground font-mono text-xs font-bold">
                                {isUnknownMatch(rec.match_score) ? "S/D" : `${rec.match_score}%`}
                              </div>
                            </div>
                            <h3 className="text-lg font-black uppercase tracking-tighter leading-none mb-1">
                              {rec.title}
                            </h3>
                            <p className="font-mono text-[10px] text-muted-foreground mb-2">
                              {rec.year}
                              {rec.kind === "series" ? " · Serie" : ""}
                            </p>
                            <p className="font-serif text-sm italic leading-snug">&ldquo;{rec.why}&rdquo;</p>
                          </article>
                        ))}
                      </div>
                    </div>
                  )}
                </div>
              );
            })}
          </div>
        )}
      </main>
    </PageTransition>
  );
}
