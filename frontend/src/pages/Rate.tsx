import { AnimatePresence, motion } from "framer-motion";
import { Film, Loader2 } from "lucide-react";
import { useCallback, useEffect, useLayoutEffect, useRef, useState } from "react";
import { toast } from "sonner";
import { useLocation } from "wouter";

import { PageTransition } from "@/components/PageTransition";
import { StarRating } from "@/components/StarRating";
import { API_BASE_URL, useAuth } from "@/hooks/useAuth";
import { useSwipeCard } from "@/hooks/useSwipeCard";
import { useLang } from "@/lib/i18n";
import type { OnboardingTitle } from "@/pages/Recommend";

// Sección para volver cuando quieras y sumar de a poco al perfil, sin
// depender del onboarding (una vez) o un reimport de Letterboxd (pedido de
// Matías, 2026-08-02). Dos pasos por título, calcando DisagreePanel
// (MovieModal.tsx): ¿la viste? -> si sí, ¿qué te pareció? con las mismas
// estrellas de siempre. Un "no la vi" no persiste nada -- mejora la
// exclusión implícitamente (no vuelve a aparecer), no el match_score.
//
// Cola infinita (pedido de Matías, 2026-08-03: "no me gusta que hayan
// tandas, debería ser infinito"): en vez de pedir un lote fijo y mostrar un
// botón "buscar más" al vaciarse, se pre-fetchea el próximo lote en
// silencio cuando faltan pocos títulos por delante y se lo pega a la cola.
// El usuario nunca ve el corte entre lotes.
const PREFETCH_THRESHOLD = 5;

type Step = "seen" | "rating";
type Kind = "movie" | "series" | "both";

const KIND_OPTIONS: { value: Kind; labelKey: string }[] = [
  { value: "movie", labelKey: "common.movies" },
  { value: "series", labelKey: "common.series" },
  { value: "both", labelKey: "common.both" },
];

export default function Rate() {
  const { isAuthenticated, loading: authLoading, token } = useAuth();
  const [, navigate] = useLocation();
  const { t } = useLang();

  const [kind, setKind] = useState<Kind>("movie");
  const [titles, setTitles] = useState<OnboardingTitle[]>([]);
  const [index, setIndex] = useState(0);
  const [rated, setRated] = useState(0);
  const [step, setStep] = useState<Step>("seen");
  const [saving, setSaving] = useState(false);
  const [loading, setLoading] = useState(true);
  const [exhausted, setExhausted] = useState(false);
  const [error, setError] = useState("");
  const fetchingRef = useRef(false);

  const fetchMore = useCallback(
    (replace: boolean) => {
      if (!token || fetchingRef.current) return;
      fetchingRef.current = true;
      if (replace) setLoading(true);
      setError("");
      fetch(`${API_BASE_URL}/titles/swipe-batch?kind=${kind}`, { headers: { Authorization: `Bearer ${token}` } })
        .then((response) => (response.ok ? response.json() : Promise.reject()))
        .then((body: { titles: OnboardingTitle[] }) => {
          const fresh = body.titles ?? [];
          setTitles((prev) => (replace ? fresh : [...prev, ...fresh]));
          if (replace) {
            setIndex(0);
            setStep("seen");
          }
          setExhausted(fresh.length === 0);
        })
        // se guarda la CLAVE, no el texto: así el cartel de error también
        // cambia de idioma si tocás el toggle con el error en pantalla
        .catch(() => setError("rate.error"))
        .finally(() => {
          setLoading(false);
          fetchingRef.current = false;
        });
    },
    [token, kind],
  );

  useEffect(() => {
    if (!authLoading && !isAuthenticated) navigate("/login");
  }, [authLoading, isAuthenticated, navigate]);

  useEffect(() => {
    setExhausted(false);
    fetchMore(true);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [token, kind]);

  useEffect(() => {
    if (!loading && !exhausted && titles.length - index <= PREFETCH_THRESHOLD) {
      fetchMore(false);
    }
  }, [index, titles.length, loading, exhausted, fetchMore]);

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
      toast.error(t("rate.saveError"));
    } finally {
      setSaving(false);
    }
  }

  const { cardRef, hint, onPointerDown, onPointerMove, onPointerUp } = useSwipeCard({
    left: skip,
    right: () => setStep("rating"),
  });

  // el swipe derecho no saca la card (sigue siendo el mismo título, solo
  // cambia el paso a "puntuar") -- useSwipeCard vuela la card afuera para
  // CUALQUIER dirección con handler, así que sin este reset quedaba volada
  // y desvanecida esperando el rating (reporte de Matías, 2026-08-03).
  // Split del drag (div interno, sin motion) vs. el slide de avance entre
  // cards (motion.div externo) evita que este reset compita con esa otra
  // animación. useLayoutEffect (no useEffect) para que el reset ocurra
  // antes del primer paint tras el swipe -- si no, se alcanza a ver un
  // frame de la card totalmente volada antes de empezar a volver.
  useLayoutEffect(() => {
    if (step === "rating" && cardRef.current) {
      const el = cardRef.current;
      el.style.transition = "transform 0.25s ease, opacity 0.25s ease";
      el.style.transform = "translate(0px, 0px) rotate(0deg)";
      el.style.opacity = "1";
    }
  }, [step, cardRef]);

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
            {t("rate.tag")}
          </div>
          <h1 className="text-6xl md:text-7xl font-black uppercase tracking-tighter leading-[0.9]">
            {t("rate.titlePrefix")}
            <span className="text-accent italic font-serif normal-case tracking-normal">
              {t("rate.titleAccent")}
            </span>
            {t("rate.titleSuffix")}
          </h1>
          <p className="font-mono text-xs text-muted-foreground mt-4">{t("rate.intro")}</p>
          <div className="flex gap-2 mt-5">
            {KIND_OPTIONS.map((option) => (
              <button
                key={option.value}
                onClick={() => setKind(option.value)}
                disabled={loading}
                className={`px-4 py-2 font-mono text-[10px] uppercase tracking-widest border transition-colors ${
                  kind === option.value
                    ? "bg-accent text-accent-foreground border-accent"
                    : "border-foreground/30 hover:border-foreground"
                }`}
              >
                {t(option.labelKey)}
              </button>
            ))}
          </div>
        </header>

        {loading && (
          <div className="py-20 text-center">
            <Loader2 className="w-7 h-7 text-accent animate-spin mx-auto mb-4" />
            <p className="font-mono text-xs uppercase text-muted-foreground">{t("rate.loading")}</p>
          </div>
        )}

        {!loading && error && (
          <div className="p-4 border-2 border-destructive/50 font-mono text-xs text-destructive">{t(error)}</div>
        )}

        {!loading && !error && !current && exhausted && (
          <div className="p-10 border-2 border-dashed border-foreground/20 text-center">
            <h2 className="text-2xl font-black uppercase tracking-tighter mb-2">
              {t("rate.exhausted")}
            </h2>
            <button
              onClick={() => {
                setExhausted(false);
                fetchMore(true);
              }}
              className="mt-4 px-5 py-3 font-mono text-[10px] uppercase tracking-widest bg-accent text-accent-foreground hover:bg-foreground hover:text-background transition-colors"
            >
              {t("common.retry")}
            </button>
          </div>
        )}

        {!loading && !error && current && (
          <div>
            <div className="font-mono text-[10px] uppercase tracking-widest text-muted-foreground text-center mb-4">
              {t("rate.ratedCount", { n: rated })}
            </div>

            <AnimatePresence mode="wait" initial={false}>
              {/* wrapper solo anima el avance entre cards (enter/exit) -- el
                  drag en vivo vive en el div interno, SIN motion, para no
                  competir por la propiedad transform con esta animación
                  (bug real: el slide a la derecha quedaba trabado/raro
                  porque las dos peleaban por el mismo transform en el mismo
                  elemento, reportado por Matías 2026-08-03) */}
              <motion.div
                key={current.title}
                initial={{ x: 60, opacity: 0 }}
                animate={{ x: 0, opacity: 1 }}
                exit={{ x: -60, opacity: 0 }}
                transition={{ duration: 0.25, ease: "easeOut" }}
                className="max-w-xs mx-auto"
              >
                <div
                  ref={cardRef}
                  onPointerDown={onPointerDown}
                  onPointerMove={onPointerMove}
                  onPointerUp={onPointerUp}
                  onPointerCancel={onPointerUp}
                  className="relative select-none cursor-grab active:cursor-grabbing border-2 border-foreground bg-secondary"
                  style={{ touchAction: "none" }}
                >
                  {hint && (
                    <div className="pointer-events-none absolute inset-0 z-10 flex items-center justify-center bg-background/70">
                      <span className="font-mono text-xs uppercase tracking-widest px-3 py-2 border-2 border-foreground bg-background">
                        {hint === "right" ? t("rate.hintSeen") : t("rate.hintNotSeen")}
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
                    <div className="font-black uppercase text-lg tracking-tighter leading-tight line-clamp-2 min-h-12">
                      {current.title}
                    </div>
                    <div className="font-mono text-[10px] text-muted-foreground mt-1">{current.year || ""}</div>
                  </div>
                </div>
              </motion.div>
            </AnimatePresence>

            <div className="max-w-xs mx-auto mt-6 overflow-hidden">
              <AnimatePresence mode="wait" initial={false}>
                {step === "seen" ? (
                  <motion.div
                    key="seen"
                    initial={{ opacity: 0 }}
                    animate={{ opacity: 1 }}
                    exit={{ x: -30, opacity: 0 }}
                    transition={{ duration: 0.2, ease: "easeOut" }}
                  >
                    <p className="font-mono text-[10px] uppercase tracking-widest text-muted-foreground text-center mb-2">
                      {t("rate.seenQuestion")}
                    </p>
                    <div className="flex gap-2">
                      <button
                        onClick={() => setStep("rating")}
                        className="flex-1 py-3 font-mono text-[10px] uppercase tracking-widest border border-foreground/30 hover:border-accent hover:text-accent transition-colors"
                      >
                        {t("rate.seenYes")}
                      </button>
                      <button
                        onClick={skip}
                        className="flex-1 py-3 font-mono text-[10px] uppercase tracking-widest border border-foreground/30 hover:border-foreground transition-colors"
                      >
                        {t("rate.seenNo")}
                      </button>
                    </div>
                    <p className="text-center font-mono text-[9px] text-muted-foreground/60 mt-3">
                      {t("rate.swipeHint")}
                    </p>
                  </motion.div>
                ) : (
                  <motion.div
                    key="rating"
                    initial={{ x: 30, opacity: 0 }}
                    animate={{ x: 0, opacity: 1 }}
                    exit={{ opacity: 0 }}
                    transition={{ duration: 0.2, ease: "easeOut" }}
                  >
                    <p className="font-mono text-[10px] uppercase tracking-widest text-muted-foreground text-center mb-2">
                      {t("rate.ratingQuestion")}
                    </p>
                    <StarRating onChange={submitRating} disabled={saving} size="lg" />
                  </motion.div>
                )}
              </AnimatePresence>
            </div>
          </div>
        )}
      </main>
    </PageTransition>
  );
}
