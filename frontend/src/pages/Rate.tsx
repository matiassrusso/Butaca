import { Film, Loader2 } from "lucide-react";
import { useCallback, useEffect, useState } from "react";
import { toast } from "sonner";
import { useLocation } from "wouter";

import { PageTransition } from "@/components/PageTransition";
import { StarRating } from "@/components/StarRating";
import { API_BASE_URL, useAuth } from "@/hooks/useAuth";
import { useSwipeCard } from "@/hooks/useSwipeCard";
import type { OnboardingTitle } from "@/pages/Recommend";

// Sección para volver cuando quieras y sumar de a poco al perfil, sin
// depender del onboarding (una vez) o un reimport de Letterboxd (pedido de
// Matías, 2026-08-02). Dos pasos por título, calcando DisagreePanel
// (MovieModal.tsx): ¿la viste? -> si sí, ¿qué te pareció? con las mismas
// estrellas de siempre. Un "no la vi" no persiste nada -- mejora la
// exclusión implícitamente (no vuelve a aparecer en esta tanda), no el
// match_score.
type Step = "seen" | "rating";

export default function Rate() {
  const { isAuthenticated, loading: authLoading, token } = useAuth();
  const [, navigate] = useLocation();

  const [titles, setTitles] = useState<OnboardingTitle[]>([]);
  const [index, setIndex] = useState(0);
  const [rated, setRated] = useState(0);
  const [step, setStep] = useState<Step>("seen");
  const [saving, setSaving] = useState(false);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");

  const loadBatch = useCallback(() => {
    if (!token) return;
    setLoading(true);
    setError("");
    fetch(`${API_BASE_URL}/titles/swipe-batch`, { headers: { Authorization: `Bearer ${token}` } })
      .then((response) => (response.ok ? response.json() : Promise.reject()))
      .then((body: { titles: OnboardingTitle[] }) => {
        setTitles(body.titles ?? []);
        setIndex(0);
        setStep("seen");
      })
      .catch(() => setError("No pude traer pelis para puntuar."))
      .finally(() => setLoading(false));
  }, [token]);

  useEffect(() => {
    if (!authLoading && !isAuthenticated) navigate("/login");
  }, [authLoading, isAuthenticated, navigate]);

  useEffect(() => {
    loadBatch();
  }, [loadBatch]);

  const current = titles[index];

  function next() {
    setIndex((i) => i + 1);
    setStep("seen");
  }

  function skip() {
    next();
  }

  async function submitRating(rating: number) {
    if (!current || !token) return;
    setSaving(true);
    try {
      const response = await fetch(`${API_BASE_URL}/profile/rate`, {
        method: "POST",
        headers: { "Content-Type": "application/json", Authorization: `Bearer ${token}` },
        body: JSON.stringify({ title: current.title, rating, tmdb_id: current.tmdb_id }),
      });
      if (!response.ok) throw new Error();
      setRated((n) => n + 1);
      next();
    } catch {
      toast.error("No se pudo guardar el puntaje.");
    } finally {
      setSaving(false);
    }
  }

  const { cardRef, hint, onPointerDown, onPointerMove, onPointerUp } = useSwipeCard({
    down: skip,
    right: () => setStep("rating"),
  });

  if (authLoading || !isAuthenticated) {
    return (
      <div className="min-h-screen flex items-center justify-center">
        <Loader2 className="w-8 h-8 animate-spin text-accent" />
      </div>
    );
  }

  return (
    <PageTransition>
      <main className="max-w-2xl mx-auto px-6 pt-16 pb-24">
        <header className="pb-8 border-b-2 border-foreground mb-8">
          <div className="font-mono text-[10px] uppercase tracking-widest text-muted-foreground mb-4">
            [Puntuar]
          </div>
          <h1 className="text-6xl md:text-7xl font-black uppercase tracking-tighter leading-[0.9]">
            ¿Qué más <span className="text-accent italic font-serif normal-case tracking-normal">viste</span>?
          </h1>
          <p className="font-mono text-xs text-muted-foreground mt-4">
            Cuanto más puntúes, mejores matches. Ni el título ni la muestra son curados a mano: salen de
            la misma variedad que usa el picker de vibras.
          </p>
        </header>

        {loading && (
          <div className="py-20 text-center">
            <Loader2 className="w-7 h-7 text-accent animate-spin mx-auto mb-4" />
            <p className="font-mono text-xs uppercase text-muted-foreground">Buscando pelis...</p>
          </div>
        )}

        {!loading && error && (
          <div className="p-4 border-2 border-destructive/50 font-mono text-xs text-destructive">{error}</div>
        )}

        {!loading && !error && !current && (
          <div className="p-10 border-2 border-dashed border-foreground/20 text-center">
            <h2 className="text-2xl font-black uppercase tracking-tighter mb-2">
              {rated > 0 ? `Puntuaste ${rated} en esta tanda.` : "Se te acabaron las pelis de esta tanda."}
            </h2>
            <button
              onClick={loadBatch}
              className="mt-4 px-5 py-3 font-mono text-[10px] uppercase tracking-widest bg-accent text-accent-foreground hover:bg-foreground hover:text-background transition-colors"
            >
              Buscar más
            </button>
          </div>
        )}

        {!loading && !error && current && (
          <div>
            <div className="font-mono text-[10px] uppercase tracking-widest text-muted-foreground text-center mb-4">
              {rated} puntuadas en esta tanda
            </div>

            <div className="max-w-xs mx-auto" style={{ touchAction: "none" }}>
              <div
                key={current.title}
                ref={cardRef}
                onPointerDown={onPointerDown}
                onPointerMove={onPointerMove}
                onPointerUp={onPointerUp}
                onPointerCancel={onPointerUp}
                className="relative select-none cursor-grab active:cursor-grabbing border-2 border-foreground bg-secondary"
              >
                {hint && (
                  <div className="pointer-events-none absolute inset-0 z-10 flex items-center justify-center bg-background/70">
                    <span className="font-mono text-xs uppercase tracking-widest px-3 py-2 border-2 border-foreground bg-background">
                      {hint === "down" ? "No la vi" : "La vi"}
                    </span>
                  </div>
                )}
                {current.poster_path ? (
                  <img
                    src={current.poster_path}
                    alt={current.title}
                    draggable={false}
                    className="w-full aspect-[2/3] object-cover pointer-events-none"
                  />
                ) : (
                  <div className="w-full aspect-[2/3] flex items-center justify-center pointer-events-none">
                    <Film className="w-10 h-10 text-muted-foreground/40" />
                  </div>
                )}
                <div className="p-4 border-t-2 border-foreground bg-background pointer-events-none">
                  <div className="font-black uppercase text-lg tracking-tighter leading-none">
                    {current.title}
                  </div>
                  <div className="font-mono text-[10px] text-muted-foreground mt-1">{current.year || ""}</div>
                </div>
              </div>
            </div>

            <div className="max-w-xs mx-auto mt-6">
              {step === "seen" ? (
                <>
                  <p className="font-mono text-[10px] uppercase tracking-widest text-muted-foreground text-center mb-2">
                    ¿La viste?
                  </p>
                  <div className="flex gap-2">
                    <button
                      onClick={() => setStep("rating")}
                      className="flex-1 py-3 font-mono text-[10px] uppercase tracking-widest border border-foreground/30 hover:border-accent hover:text-accent transition-colors"
                    >
                      Sí, la vi
                    </button>
                    <button
                      onClick={skip}
                      className="flex-1 py-3 font-mono text-[10px] uppercase tracking-widest border border-foreground/30 hover:border-foreground transition-colors"
                    >
                      No la vi
                    </button>
                  </div>
                  <p className="text-center font-mono text-[9px] text-muted-foreground/60 mt-3">
                    O deslizá: derecha si la viste, abajo si no.
                  </p>
                </>
              ) : (
                <>
                  <p className="font-mono text-[10px] uppercase tracking-widest text-muted-foreground text-center mb-2">
                    ¿Qué te pareció?
                  </p>
                  <StarRating onChange={submitRating} disabled={saving} size="lg" />
                </>
              )}
            </div>
          </div>
        )}
      </main>
    </PageTransition>
  );
}
