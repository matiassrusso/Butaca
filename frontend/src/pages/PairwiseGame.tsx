import { Film, Loader2 } from "lucide-react";
import { useCallback, useEffect, useState } from "react";
import { toast } from "sonner";
import { useLocation } from "wouter";

import { PageTransition } from "@/components/PageTransition";
import { API_BASE_URL, useAuth } from "@/hooks/useAuth";
import { useLang } from "@/lib/i18n";
import type { OnboardingTitle } from "@/pages/Recommend";

// Juego "¿cuál te gustó más?" (idea de Matías, 2026-08-02, rediseñado
// 2026-08-03 tras un bug real: el par venía de títulos SIN VER, y elegir
// cualquiera los marcaba como vistos+gustados en la bitácora sin que el
// usuario los hubiera visto nunca). Ahora el par sale de dos títulos que el
// usuario YA vio y puntuó igual -- no se inventa un rating nuevo, solo se
// guarda la preferencia relativa para desempatar entre "amados" con el
// mismo puntaje.
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
  const { t } = useLang();

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
      // se guarda la CLAVE, no el texto: el cartel sigue el toggle de idioma
      .catch(() => setError("games.pairwise.error"))
      .finally(() => setLoading(false));
  }, [token]);

  useEffect(() => {
    if (!authLoading && !isAuthenticated) navigate("/login");
  }, [authLoading, isAuthenticated, navigate]);

  useEffect(() => {
    loadPair();
  }, [loadPair]);

  async function choose(winner: OnboardingTitle, loser: OnboardingTitle) {
    if (!token || choosing) return;
    setChoosing(true);
    try {
      const response = await fetch(`${API_BASE_URL}/games/pairwise/choose`, {
        method: "POST",
        headers: { "Content-Type": "application/json", Authorization: `Bearer ${token}` },
        body: JSON.stringify({ winner_title: winner.title, loser_title: loser.title }),
      });
      if (!response.ok) throw new Error();
      setRounds((n) => n + 1);
      loadPair();
    } catch {
      toast.error(t("games.pairwise.saveError"));
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
            {t("games.tagSingle")}
          </div>
          <h1 className="text-6xl md:text-7xl font-black uppercase tracking-tighter leading-[0.9]">
            {t("games.pairwise.titlePrefix")}
            <span className="text-accent italic font-serif normal-case tracking-normal">
              {t("games.pairwise.titleAccent")}
            </span>
            {t("games.pairwise.titleSuffix")}
          </h1>
          <p className="font-mono text-xs text-muted-foreground mt-4">{t("games.pairwise.intro")}</p>
        </header>

        {loading && (
          <div className="py-20 text-center">
            <Loader2 className="w-7 h-7 text-accent animate-spin mx-auto mb-4" />
            <p className="font-mono text-xs uppercase text-muted-foreground">{t("games.pairwise.loading")}</p>
          </div>
        )}

        {!loading && error && (
          <div className="p-4 border-2 border-destructive/50 font-mono text-xs text-destructive">{t(error)}</div>
        )}

        {!loading && !error && (!pair.left || !pair.right) && (
          <div className="p-10 border-2 border-dashed border-foreground/20 text-center">
            <h2 className="text-2xl font-black uppercase tracking-tighter mb-2">
              {rounds > 0
                ? t(rounds === 1 ? "games.pairwise.playedOne" : "games.pairwise.playedMany", { n: rounds })
                : t("games.pairwise.needMore")}
            </h2>
            <button
              onClick={loadPair}
              className="mt-4 px-5 py-3 font-mono text-[10px] uppercase tracking-widest bg-accent text-accent-foreground hover:bg-foreground hover:text-background transition-colors"
            >
              {t("common.retry")}
            </button>
          </div>
        )}

        {!loading && !error && pair.left && pair.right && (
          <div>
            <div className="font-mono text-[10px] uppercase tracking-widest text-muted-foreground text-center mb-6">
              {t(rounds === 1 ? "games.pairwise.roundsOne" : "games.pairwise.roundsMany", { n: rounds })}
            </div>
            <div className="grid grid-cols-2 gap-6 md:gap-10 items-start">
              <Poster item={pair.left} onPick={() => choose(pair.left!, pair.right!)} disabled={choosing} />
              <Poster item={pair.right} onPick={() => choose(pair.right!, pair.left!)} disabled={choosing} />
            </div>
          </div>
        )}
      </main>
    </PageTransition>
  );
}
