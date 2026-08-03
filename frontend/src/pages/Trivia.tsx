import { Film, Loader2 } from "lucide-react";
import { useCallback, useEffect, useState } from "react";
import { useLocation } from "wouter";

import { PageTransition } from "@/components/PageTransition";
import { API_BASE_URL, useAuth } from "@/hooks/useAuth";

// Trivia de cine (idea de Matías, 2026-08-02) -- puro entretenimiento, no
// toca el perfil de gusto (a diferencia del juego pairwise): el puntaje
// vive solo en este componente, se pierde al salir de la página a propósito.
type Question = {
  title: string;
  poster_path: string | null;
  question: string;
  options: string[];
  correct_answer: string;
};

export default function Trivia() {
  const { isAuthenticated, loading: authLoading, token } = useAuth();
  const [, navigate] = useLocation();

  const [question, setQuestion] = useState<Question | null>(null);
  const [picked, setPicked] = useState<string | null>(null);
  const [score, setScore] = useState({ correct: 0, total: 0 });
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");

  const loadQuestion = useCallback(() => {
    if (!token) return;
    setLoading(true);
    setError("");
    setPicked(null);
    fetch(`${API_BASE_URL}/games/trivia`, { headers: { Authorization: `Bearer ${token}` } })
      .then((response) => (response.ok ? response.json() : Promise.reject()))
      .then((body: Question | null) => setQuestion(body))
      .catch(() => setError("No pude armar una pregunta."))
      .finally(() => setLoading(false));
  }, [token]);

  useEffect(() => {
    if (!authLoading && !isAuthenticated) navigate("/login");
  }, [authLoading, isAuthenticated, navigate]);

  useEffect(() => {
    loadQuestion();
  }, [loadQuestion]);

  function answer(option: string) {
    if (!question || picked) return;
    setPicked(option);
    setScore((s) => ({
      correct: s.correct + (option === question.correct_answer ? 1 : 0),
      total: s.total + 1,
    }));
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
      <main className="max-w-2xl mx-auto px-6 pt-16 pb-24">
        <header className="pb-8 border-b-2 border-foreground mb-8">
          <div className="font-mono text-[10px] uppercase tracking-widest text-muted-foreground mb-4">
            [Juego]
          </div>
          <h1 className="text-6xl md:text-7xl font-black uppercase tracking-tighter leading-[0.9]">
            Trivia de <span className="text-accent italic font-serif normal-case tracking-normal">cine</span>
          </h1>
          <p className="font-mono text-xs text-muted-foreground mt-4">
            Puro entretenimiento -- esto no toca tu perfil de gusto.
          </p>
        </header>

        {loading && (
          <div className="py-20 text-center">
            <Loader2 className="w-7 h-7 text-accent animate-spin mx-auto mb-4" />
            <p className="font-mono text-xs uppercase text-muted-foreground">Armando una pregunta...</p>
          </div>
        )}

        {!loading && error && (
          <div className="p-4 border-2 border-destructive/50 font-mono text-xs text-destructive">{error}</div>
        )}

        {!loading && !error && !question && (
          <div className="p-10 border-2 border-dashed border-foreground/20 text-center">
            <h2 className="text-2xl font-black uppercase tracking-tighter mb-2">
              No hay suficientes pelis sin puntuar para armar una pregunta.
            </h2>
            <button
              onClick={loadQuestion}
              className="mt-4 px-5 py-3 font-mono text-[10px] uppercase tracking-widest bg-accent text-accent-foreground hover:bg-foreground hover:text-background transition-colors"
            >
              Reintentar
            </button>
          </div>
        )}

        {!loading && !error && question && (
          <div>
            <div className="font-mono text-[10px] uppercase tracking-widest text-muted-foreground text-center mb-6">
              {score.correct}/{score.total} correctas
            </div>

            <div className="flex gap-4 items-start mb-6">
              {question.poster_path ? (
                <img
                  src={question.poster_path}
                  alt={question.title}
                  className="w-24 aspect-[2/3] object-cover shrink-0 outline outline-1 -outline-offset-1 outline-black/10"
                />
              ) : (
                <div className="w-24 aspect-[2/3] bg-secondary flex items-center justify-center shrink-0">
                  <Film className="w-6 h-6 text-muted-foreground/40" />
                </div>
              )}
              <p className="text-xl font-black uppercase tracking-tighter leading-tight pt-2">
                {question.question}
              </p>
            </div>

            <div className="grid grid-cols-2 gap-3">
              {question.options.map((option) => {
                const isCorrect = option === question.correct_answer;
                const isPicked = option === picked;
                const revealed = picked !== null;
                return (
                  <button
                    key={option}
                    onClick={() => answer(option)}
                    disabled={revealed}
                    className={`py-3 px-4 font-mono text-xs uppercase tracking-widest border-2 transition-colors text-left ${
                      revealed && isCorrect
                        ? "border-accent bg-accent/10 text-accent"
                        : revealed && isPicked
                          ? "border-destructive bg-destructive/10 text-destructive"
                          : "border-foreground/20 hover:border-foreground disabled:pointer-events-none"
                    }`}
                  >
                    {option}
                  </button>
                );
              })}
            </div>

            {picked && (
              <button
                onClick={loadQuestion}
                className="mt-6 w-full py-3 font-mono text-[10px] uppercase tracking-widest bg-accent text-accent-foreground hover:bg-foreground hover:text-background transition-colors"
              >
                Siguiente
              </button>
            )}
          </div>
        )}
      </main>
    </PageTransition>
  );
}
