import { Film, Loader2 } from "lucide-react";
import { useCallback, useEffect, useState } from "react";
import { toast } from "sonner";
import { useLocation } from "wouter";

import { PageTransition } from "@/components/PageTransition";
import { API_BASE_URL, useAuth } from "@/hooks/useAuth";
import type { OnboardingTitle } from "@/pages/Recommend";

// Juego "¿cuál te gustó más?" (idea de Matías, 2026-08-02): a diferencia de
// la trivia, cada elección es señal real de preferencia relativa entre dos
// títulos sin puntuar -- el ganador se guarda en el perfil con un rating
// inferido (GAME_PAIRWISE_RATING en el backend), el perdedor no se toca.
type Pair = { left: OnboardingTitle | null; right: OnboardingTitle | null };

function Poster({ item, onPick, disabled }: { item: OnboardingTitle; onPick: () => void; disabled: boolean }) {
  return (
    <button
      type="button"
      onClick={onPick}
      disabled={disabled}
      className="group text-left disabled:opacity-60 disabled:pointer-events-none"
    >
      <div className="relative border-2 border-foreground/20 group-hover:border-accent transition-colors overflow-hidden">
        {item.poster_path ? (
          <img
            src={item.poster_path}
            alt={item.title}
            className="w-full aspect-[2/3] object-cover transition-transform duration-500 group-hover:scale-[1.04]"
          />
        ) : (
          <div className="w-full aspect-[2/3] bg-secondary flex items-center justify-center">
            <Film className="w-10 h-10 text-muted-foreground/40" />
          </div>
        )}
      </div>
      <div className="mt-2 font-black uppercase text-sm tracking-tighter leading-tight">{item.title}</div>
      <div className="font-mono text-[10px] text-muted-foreground">{item.year || ""}</div>
    </button>
  );
}

export default function PairwiseGame() {
  const { isAuthenticated, loading: authLoading, token } = useAuth();
  const [, navigate] = useLocation();

  const [pair, setPair] = useState<Pair>({ left: null, right: null });
  const [rounds, setRounds] = useState(0);
  const [loading, setLoading] = useState(true);
  const [choosing, setChoosing] = useState(false);
  const [error, setError] = useState("");

  const loadPair = useCallback(() => {
    if (!token) return;
    setLoading(true);
    setError("");
    fetch(`${API_BASE_URL}/games/pairwise`, { headers: { Authorization: `Bearer ${token}` } })
      .then((response) => (response.ok ? response.json() : Promise.reject()))
      .then((body: Pair) => setPair(body))
      .catch(() => setError("No pude armar un par para jugar."))
      .finally(() => setLoading(false));
  }, [token]);

  useEffect(() => {
    if (!authLoading && !isAuthenticated) navigate("/login");
  }, [authLoading, isAuthenticated, navigate]);

  useEffect(() => {
    loadPair();
  }, [loadPair]);

  async function choose(winner: OnboardingTitle) {
    if (!token || choosing) return;
    setChoosing(true);
    try {
      const response = await fetch(`${API_BASE_URL}/games/pairwise/choose`, {
        method: "POST",
        headers: { "Content-Type": "application/json", Authorization: `Bearer ${token}` },
        body: JSON.stringify({ winner_title: winner.title, winner_tmdb_id: winner.tmdb_id }),
      });
      if (!response.ok) throw new Error();
      setRounds((n) => n + 1);
      loadPair();
    } catch {
      toast.error("No se pudo guardar tu elección.");
    } finally {
      setChoosing(false);
    }
  }

  if (authLoading || !isAuthenticated) {
    return (
      <div className="min-h-screen flex items-center justify-center">
        <Loader2 className="w-8 h-8 animate-spin text-accent" />
      </div>
    );
  }

  return (
    <PageTransition>
      <main className="max-w-3xl mx-auto px-6 pt-16 pb-24">
        <header className="pb-8 border-b-2 border-foreground mb-8">
          <div className="font-mono text-[10px] uppercase tracking-widest text-muted-foreground mb-4">
            [Juego]
          </div>
          <h1 className="text-6xl md:text-7xl font-black uppercase tracking-tighter leading-[0.9]">
            ¿Cuál te <span className="text-accent italic font-serif normal-case tracking-normal">gustó</span> más?
          </h1>
          <p className="font-mono text-xs text-muted-foreground mt-4">
            Elegí una. Tu elección queda en el perfil como preferencia, no como puntaje exacto.
          </p>
        </header>

        {loading && (
          <div className="py-20 text-center">
            <Loader2 className="w-7 h-7 text-accent animate-spin mx-auto mb-4" />
            <p className="font-mono text-xs uppercase text-muted-foreground">Buscando un par...</p>
          </div>
        )}

        {!loading && error && (
          <div className="p-4 border-2 border-destructive/50 font-mono text-xs text-destructive">{error}</div>
        )}

        {!loading && !error && (!pair.left || !pair.right) && (
          <div className="p-10 border-2 border-dashed border-foreground/20 text-center">
            <h2 className="text-2xl font-black uppercase tracking-tighter mb-2">
              {rounds > 0 ? `Jugaste ${rounds} ronda${rounds === 1 ? "" : "s"}.` : "No hay suficientes pelis sin puntuar para armar un par."}
            </h2>
            <button
              onClick={loadPair}
              className="mt-4 px-5 py-3 font-mono text-[10px] uppercase tracking-widest bg-accent text-accent-foreground hover:bg-foreground hover:text-background transition-colors"
            >
              Reintentar
            </button>
          </div>
        )}

        {!loading && !error && pair.left && pair.right && (
          <div>
            <div className="font-mono text-[10px] uppercase tracking-widest text-muted-foreground text-center mb-6">
              {rounds} ronda{rounds === 1 ? "" : "s"} jugada{rounds === 1 ? "" : "s"}
            </div>
            <div className="grid grid-cols-2 gap-6 md:gap-10 items-start">
              <Poster item={pair.left} onPick={() => choose(pair.left!)} disabled={choosing} />
              <Poster item={pair.right} onPick={() => choose(pair.right!)} disabled={choosing} />
            </div>
          </div>
        )}
      </main>
    </PageTransition>
  );
}
