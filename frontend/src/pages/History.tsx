import { Loader2, RefreshCw, Sparkles, Star } from "lucide-react";
import { useEffect, useState } from "react";
import { useLocation } from "wouter";

import { Navbar } from "@/components/Navbar";
import { PageTransition } from "@/components/PageTransition";
import { API_BASE_URL, useAuth } from "@/hooks/useAuth";

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
};

function formatSessionDate(value: string): string {
  const date = new Date(`${value}Z`);
  return Number.isNaN(date.getTime())
    ? value
    : date.toLocaleString("es-AR", {
        dateStyle: "medium",
        timeStyle: "short",
      });
}

export default function History() {
  const { isAuthenticated, loading: authLoading, token } = useAuth();
  const [, navigate] = useLocation();
  const [tab, setTab] = useState<"recommended" | "watched">("recommended");
  const [sessions, setSessions] = useState<RecommendationSession[]>([]);
  const [watchedItems, setWatchedItems] = useState<WatchedItem[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");

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
            setSessions(body.sessions ?? []);
          }
        }
      })
      .catch((err) => {
        if (!cancelled) {
          setError(err instanceof Error ? err.message : "No pude cargar tu historial.");
        }
      })
      .finally(() => {
        if (!cancelled) {
          setLoading(false);
        }
      });

    return () => {
      cancelled = true;
    };
  }, [token, tab]);

  if (authLoading || !isAuthenticated) {
    return (
      <div className="min-h-screen bg-background flex items-center justify-center">
        <Loader2 className="w-8 h-8 animate-spin text-primary" />
      </div>
    );
  }

  return (
    <PageTransition className="min-h-screen bg-background film-grain">
      <Navbar />

      <div className="pt-24 pb-16">
        <div className="container max-w-6xl">
          <div className="mb-10">
            <p className="text-primary text-sm uppercase tracking-widest mb-3 font-medium">
              Tu archivo
            </p>
            <h1
              className="text-4xl md:text-5xl font-serif mb-4"
              style={{ fontFamily: "'Instrument Serif', serif" }}
            >
              Historial de <em className="text-gradient not-italic">sesiones</em>
            </h1>
            <p className="text-muted-foreground leading-relaxed max-w-2xl">
              Cada tanda de picks que ya generaste queda ac&aacute; para revisitarlas sin volver a
              subir el zip.
            </p>
          </div>

          <div className="flex gap-2 mb-6" role="tablist" aria-label="Historial">
            {[
              ["recommended", "Recomendadas"],
              ["watched", "Vistas"],
            ].map(([value, label]) => (
              <button
                key={value}
                role="tab"
                aria-selected={tab === value}
                onClick={() => setTab(value as "recommended" | "watched")}
                className={`px-4 py-2 rounded-xl border text-sm font-medium transition-colors ${
                  tab === value
                    ? "bg-primary text-primary-foreground border-primary"
                    : "border-border bg-card/40 text-muted-foreground hover:text-foreground"
                }`}
              >
                {label}
              </button>
            ))}
          </div>

          {loading && (
            <div className="py-20 text-center">
              <Loader2 className="w-8 h-8 animate-spin text-primary mx-auto mb-4" />
              <p className="text-sm text-muted-foreground">Cargando tu historial...</p>
            </div>
          )}

          {!loading && error && (
            <div className="p-4 rounded-xl border border-destructive/30 bg-destructive/5 text-sm text-destructive">
              {error}
            </div>
          )}

          {!loading && !error && tab === "recommended" && sessions.length === 0 && (
            <div className="p-8 rounded-2xl border border-border bg-card/40 text-center">
              <Sparkles className="w-8 h-8 text-primary mx-auto mb-4" />
              <h2
                className="text-2xl font-serif mb-2"
                style={{ fontFamily: "'Instrument Serif', serif" }}
              >
                Todav&iacute;a no generaste picks
              </h2>
              <p className="text-sm text-muted-foreground mb-5">
                Cuando hagas tu primera sesi&oacute;n de recomendaciones, va a aparecer ac&aacute;.
              </p>
              <button
                onClick={() => navigate("/recommend")}
                className="inline-flex items-center gap-2 bg-primary text-primary-foreground px-4 py-2 rounded-xl text-sm font-medium hover:bg-primary/90 transition-colors"
              >
                <RefreshCw className="w-4 h-4" />
                Ir a recomendar
              </button>
            </div>
          )}

          {!loading && !error && tab === "recommended" && sessions.length > 0 && (
            <div className="space-y-8">
              {sessions.map((session) => (
                <section
                  key={session.id}
                  className="rounded-2xl border border-border bg-card/40 overflow-hidden"
                >
                  <div className="p-6 border-b border-border bg-card/60">
                    <div className="flex flex-wrap items-center justify-between gap-3 mb-3">
                      <div>
                        <p className="text-xs uppercase tracking-widest text-primary mb-2">
                          {formatSessionDate(session.created_at)}
                        </p>
                        <h2
                          className="text-2xl font-serif"
                          style={{ fontFamily: "'Instrument Serif', serif" }}
                        >
                          Sesi&oacute;n {session.id}
                        </h2>
                      </div>
                      <span className="px-3 py-1 rounded-full bg-primary/10 border border-primary/20 text-xs text-primary">
                        Mood: {session.mood || "sin filtro"}
                      </span>
                    </div>
                    <p className="text-sm text-muted-foreground max-w-3xl">
                      {session.taste_summary}
                    </p>
                  </div>

                  <div className="grid md:grid-cols-2 xl:grid-cols-3 gap-4 p-6">
                    {session.recommendations.map((rec) => (
                      <article
                        key={rec.id}
                        className="rounded-2xl border border-border bg-background/70 overflow-hidden"
                      >
                        {rec.backdrop_path && (
                          <img
                            src={rec.backdrop_path}
                            alt={rec.title}
                            className="w-full h-32 object-cover"
                          />
                        )}
                        <div className="p-4">
                          <div className="flex items-start justify-between gap-3 mb-2">
                            <div>
                              <h3
                                className="text-xl font-serif leading-tight"
                                style={{ fontFamily: "'Instrument Serif', serif" }}
                              >
                                {rec.title}
                              </h3>
                              <p className="text-xs text-muted-foreground mt-1">
                                {rec.year} {rec.kind === "series" ? "· Serie" : ""}
                              </p>
                            </div>
                            <span className="text-xs text-primary whitespace-nowrap">
                              {rec.match_score}% match
                            </span>
                          </div>

                          {rec.vote_average != null && (
                            <p className="flex items-center gap-1 text-xs text-muted-foreground mb-3">
                              <Star className="w-3 h-3 fill-primary text-primary" />
                              {rec.vote_average.toFixed(1)}
                            </p>
                          )}

                          <p className="text-sm text-foreground/85 leading-relaxed mb-3">
                            {rec.why}
                          </p>

                          {rec.tags.length > 0 && (
                            <div className="flex flex-wrap gap-2">
                              {rec.tags.map((tag) => (
                                <span
                                  key={tag}
                                  className="px-2 py-1 rounded-full text-[11px] bg-primary/10 border border-primary/15 text-primary"
                                >
                                  {tag}
                                </span>
                              ))}
                            </div>
                          )}
                        </div>
                      </article>
                    ))}
                  </div>
                </section>
              ))}
            </div>
          )}

          {!loading && !error && tab === "watched" && watchedItems.length === 0 && (
            <div className="p-8 rounded-2xl border border-border bg-card/40 text-center">
              <Star className="w-8 h-8 text-primary mx-auto mb-4" />
              <h2
                className="text-2xl font-serif mb-2"
                style={{ fontFamily: "'Instrument Serif', serif" }}
              >
                Todav&iacute;a no importaste vistas
              </h2>
              <p className="text-sm text-muted-foreground">
                Sub&iacute; tu export de Letterboxd para verlas ac&aacute;.
              </p>
            </div>
          )}

          {!loading && !error && tab === "watched" && watchedItems.length > 0 && (
            <div className="grid md:grid-cols-2 xl:grid-cols-3 gap-4">
              {watchedItems.map((item) => (
                <article
                  key={`${item.title}-${item.created_at}`}
                  className="rounded-2xl border border-border bg-card/40 p-5"
                >
                  <div className="flex items-start justify-between gap-3 mb-3">
                    <div>
                      <p className="text-xs uppercase tracking-widest text-primary mb-2">
                        {formatSessionDate(item.created_at)}
                      </p>
                      <h2
                        className="text-2xl font-serif leading-tight"
                        style={{ fontFamily: "'Instrument Serif', serif" }}
                      >
                        {item.title}
                      </h2>
                    </div>
                    <span className="flex items-center gap-1 text-sm text-primary whitespace-nowrap">
                      <Star className="w-4 h-4 fill-primary text-primary" />
                      {item.rating.toFixed(1)}
                    </span>
                  </div>
                  {item.review && (
                    <p className="text-sm text-muted-foreground leading-relaxed">{item.review}</p>
                  )}
                </article>
              ))}
            </div>
          )}
        </div>
      </div>
    </PageTransition>
  );
}
