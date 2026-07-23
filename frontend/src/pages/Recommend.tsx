import {
  AlertCircle,
  CheckCircle,
  Eye,
  Film,
  Loader2,
  ThumbsDown,
  ThumbsUp,
} from "lucide-react";
import React, { useCallback, useEffect, useRef, useState } from "react";
import { toast } from "sonner";
import { useLocation } from "wouter";

import { MovieModal, type FeedbackStatus, type Recommendation } from "@/components/MovieModal";
import { PageTransition } from "@/components/PageTransition";
import { API_BASE_URL, useAuth } from "@/hooks/useAuth";
import { useTiltCard } from "@/hooks/useTiltCard";

type RecommendResponse = {
  taste_summary: string;
  recommendations: Recommendation[];
  discarded_rows: number;
  session_id: number | null;
  refined: boolean;
};

type RecommendMode = "profile" | "recent" | "genres" | "watchlist";
type KindFilter = "movie" | "series" | "both";

// desc: qué hace cada modo, visible en el paso 2 del wizard (feedback: "no
// entiendo qué significa cada opción")
const modeOptions: { mode: RecommendMode; label: string; desc: string }[] = [
  {
    mode: "profile",
    label: "Perfil completo",
    desc: "Cruzamos todo tu historial: géneros, directores, décadas y tags.",
  },
  {
    mode: "recent",
    label: "Últimas vistas",
    desc: "Le damos más peso a lo último que viste — para seguir la racha.",
  },
  {
    mode: "genres",
    label: "Selección de géneros",
    desc: "Vos elegís los géneros, nosotros buscamos lo mejor adentro de eso.",
  },
  {
    mode: "watchlist",
    label: "De mi watchlist",
    desc: "Ordenamos tu propia watchlist según tu perfil: cuál va primero.",
  },
];

// wizard de 3 pasos (feedback: la página anterior tiraba todo junto y los
// usuarios nuevos no sabían por dónde empezar)
type WizardStep = 1 | 2 | 3;
const STEP_LABELS = ["Tu historial", "Qué ver", "Formato"];

const kindFilterOptions: { value: KindFilter; label: string }[] = [
  { value: "movie", label: "Películas" },
  { value: "series", label: "Series" },
  { value: "both", label: "Ambas" },
];

// misma clave que backend/app/recommender.py::GENRE_OPTIONS
const genreOptions: { key: string; label: string }[] = [
  { key: "action", label: "Acción" },
  { key: "romance", label: "Romance" },
  { key: "comedy", label: "Comedia" },
  { key: "horror", label: "Terror / oscuro" },
  { key: "drama", label: "Drama" },
  { key: "psychological", label: "Psicológico / misterio" },
  { key: "scifi", label: "Ciencia ficción / fantástico" },
];

type ImportMethod = "zip" | "username" | "manual";

// onboarding without Letterboxd: rate seed titles by hand
type OnboardingTitle = {
  title: string;
  year: number;
  kind: string;
  tmdb_id: number | null;
  poster_path: string | null;
};

const MIN_MANUAL_RATINGS = 10; // keep in sync with backend/app/main.py::MIN_MANUAL_RATINGS
// each button maps to a synthetic rating; "No la vi" removes the title (skip)
const manualRatingOptions: { label: string; value: number }[] = [
  { label: "Me encantó", value: 4.5 },
  { label: "Bien", value: 3.5 },
  { label: "No me gustó", value: 1.5 },
];

function formatFileSize(bytes: number): string {
  return bytes < 1024 * 1024 ? `${Math.round(bytes / 1024)} KB` : `${(bytes / (1024 * 1024)).toFixed(1)} MB`;
}

const tabCls = (active: boolean) =>
  `flex-1 py-3 font-mono text-[10px] uppercase tracking-widest border transition-colors ${
    active ? "bg-foreground text-background border-foreground" : "border-foreground/20 hover:border-foreground"
  }`;

// ─── Recommendation Card ────────────────────────────────────────────────────

function RecommendationCard({
  rec,
  index,
  feedback,
  onSelect,
}: {
  rec: Recommendation;
  index: number;
  feedback?: FeedbackStatus;
  onSelect: () => void;
}) {
  const poster = rec.poster_path ?? rec.backdrop_path;
  const { wrapRef, onMouseMove, onMouseLeave } = useTiltCard();

  return (
    <button
      type="button"
      onClick={onSelect}
      className="animate-reveal text-left group block w-full"
      style={{ animationDelay: `${100 + index * 100}ms`, perspective: "1000px" }}
    >
      <div
        ref={wrapRef}
        onMouseMove={onMouseMove}
        onMouseLeave={onMouseLeave}
        className="mb-6 relative transition-transform duration-200 ease-out"
        style={{ transformStyle: "preserve-3d" }}
      >
        <div className="relative overflow-hidden">
          {poster ? (
            <img
              src={poster}
              alt={rec.title}
              loading="lazy"
              className="w-full aspect-[2/3] object-cover bg-secondary outline outline-1 -outline-offset-1 outline-black/10 transition-transform duration-700 group-hover:scale-[1.04]"
            />
          ) : (
            <div className="w-full aspect-[2/3] bg-secondary flex items-center justify-center">
              <Film className="w-10 h-10 text-muted-foreground/40" />
            </div>
          )}
          <div
            className="pointer-events-none absolute inset-0 opacity-0 group-hover:opacity-100 transition-opacity duration-500 mix-blend-overlay"
            style={{
              background:
                "radial-gradient(circle at var(--mx, 50%) var(--my, 50%), rgba(255,255,255,0.5), transparent 55%)",
            }}
          />
        </div>
        <div
          className="absolute -top-3 -right-3 size-16 bg-accent flex items-center justify-center text-accent-foreground font-mono text-lg font-bold shadow-2xl shadow-accent/30 ring-1 ring-background/40"
          style={{ transform: "translateZ(40px)" }}
        >
          {rec.match_score}%
        </div>
        {rec.kind === "series" && (
          <span className="absolute top-3 left-3 font-mono text-[10px] uppercase px-2 py-1 bg-background border border-foreground/20">
            Serie
          </span>
        )}
        {feedback && (
          <span className="absolute bottom-3 left-3 size-7 bg-background border border-foreground/20 flex items-center justify-center">
            {feedback === "interested" && <ThumbsUp className="w-3.5 h-3.5 text-accent" />}
            {feedback === "seen" && <Eye className="w-3.5 h-3.5 text-muted-foreground" />}
            {feedback === "not_interested" && <ThumbsDown className="w-3.5 h-3.5 text-destructive" />}
          </span>
        )}
      </div>
      <div className="flex justify-between items-baseline gap-4 mb-4">
        <h3 className="text-2xl font-black uppercase tracking-tighter leading-none group-hover:text-accent transition-colors">
          {rec.title}
        </h3>
        <span className="font-mono text-xs text-muted-foreground shrink-0">{rec.year}</span>
      </div>
      <p className="font-serif text-xl leading-snug mb-4 italic text-balance">
        &ldquo;{rec.why}&rdquo;
      </p>
      <div className="font-mono text-[10px] uppercase tracking-widest text-muted-foreground border-t border-foreground/10 pt-4">
        {rec.director
          ? `Dir. ${rec.director} • ${rec.tags.slice(0, 2).join(" / ") || "—"}`
          : rec.tags.slice(0, 3).join(" / ") || "Sin tags"}
      </div>
    </button>
  );
}

// ─── Onboarding rating grid (no Letterboxd) ─────────────────────────────────

// mismo tilt 3D + glare que los posters de picks (useTiltCard necesita una
// instancia por card, por eso es un componente y no un map inline)
function ManualRatingCard({
  item,
  current,
  onRate,
}: {
  item: OnboardingTitle;
  current: number | undefined;
  onRate: (title: string, rating: number | null) => void;
}) {
  const { wrapRef, onMouseMove, onMouseLeave } = useTiltCard();

  return (
    <div className="flex flex-col">
      <div style={{ perspective: "1000px" }}>
        <div
          ref={wrapRef}
          onMouseMove={onMouseMove}
          onMouseLeave={onMouseLeave}
          className="group relative overflow-hidden aspect-[2/3] bg-secondary mb-2 border border-foreground/10 transition-transform duration-200 ease-out"
          style={{ transformStyle: "preserve-3d" }}
        >
          {item.poster_path ? (
            <img
              src={item.poster_path}
              alt={item.title}
              loading="lazy"
              className="w-full h-full object-cover transition-transform duration-700 group-hover:scale-[1.04]"
            />
          ) : (
            <div className="w-full h-full flex items-center justify-center">
              <Film className="w-7 h-7 text-muted-foreground/40" />
            </div>
          )}
          <div
            className="pointer-events-none absolute inset-0 opacity-0 group-hover:opacity-100 transition-opacity duration-500 mix-blend-overlay"
            style={{
              background:
                "radial-gradient(circle at var(--mx, 50%) var(--my, 50%), rgba(255,255,255,0.5), transparent 55%)",
            }}
          />
        </div>
      </div>
      <div className="font-black uppercase text-xs tracking-tighter leading-none mb-0.5">{item.title}</div>
      <div className="font-mono text-[10px] text-muted-foreground mb-2">{item.year}</div>
      <div className="mt-auto grid grid-cols-2 gap-1">
        {manualRatingOptions.map((option) => (
          <button
            key={option.value}
            onClick={() => onRate(item.title, current === option.value ? null : option.value)}
            className={`px-1.5 py-1.5 font-mono text-[9px] uppercase tracking-wider border transition-colors ${
              current === option.value
                ? "bg-accent text-accent-foreground border-accent"
                : "border-foreground/20 hover:border-foreground"
            }`}
          >
            {option.label}
          </button>
        ))}
        <button
          onClick={() => onRate(item.title, null)}
          className={`px-1.5 py-1.5 font-mono text-[9px] uppercase tracking-wider border transition-colors ${
            current === undefined
              ? "bg-foreground text-background border-foreground"
              : "border-foreground/20 hover:border-foreground"
          }`}
        >
          No la vi
        </button>
      </div>
    </div>
  );
}

function ManualRatingGrid({
  titles,
  ratings,
  loading,
  onRate,
}: {
  titles: OnboardingTitle[];
  ratings: Record<string, number>;
  loading: boolean;
  onRate: (title: string, rating: number | null) => void;
}) {
  if (loading) {
    return (
      <div className="p-12 text-center">
        <Loader2 className="w-6 h-6 text-accent animate-spin mx-auto" />
      </div>
    );
  }

  return (
    <div className="grid grid-cols-2 md:grid-cols-3 gap-6">
      {titles.map((item) => (
        <ManualRatingCard key={item.title} item={item} current={ratings[item.title]} onRate={onRate} />
      ))}
    </div>
  );
}

// ─── Main Page ───────────────────────────────────────────────────────────────

export default function Recommend() {
  const { isAuthenticated, loading: authLoading, token } = useAuth();
  const [, navigate] = useLocation();

  const [step, setStep] = useState<WizardStep>(1);
  const [mode, setMode] = useState<RecommendMode>("profile");
  const [kindFilter, setKindFilter] = useState<KindFilter>("movie");
  const [selectedGenres, setSelectedGenres] = useState<string[]>([]);
  const [importMethod, setImportMethod] = useState<ImportMethod>("zip");
  const [zipFile, setZipFile] = useState<File | null>(null);
  const [letterboxdUsername, setLetterboxdUsername] = useState("");
  const [isDragging, setIsDragging] = useState(false);
  const fileInputRef = useRef<HTMLInputElement>(null);

  // onboarding without Letterboxd: seed titles fetched lazily, ratings by title
  const [onboardingTitles, setOnboardingTitles] = useState<OnboardingTitle[]>([]);
  const [loadingTitles, setLoadingTitles] = useState(false);
  const [manualRatings, setManualRatings] = useState<Record<string, number>>({});
  // titles the user searched and added (seen a film that isn't in the seed list)
  const [addedTitles, setAddedTitles] = useState<OnboardingTitle[]>([]);
  const [searchQuery, setSearchQuery] = useState("");
  const [searchResults, setSearchResults] = useState<OnboardingTitle[]>([]);
  const manualCount = Object.keys(manualRatings).length;

  // added titles first (on top), then the seed list, deduped by title
  const manualTitles = (() => {
    const seen = new Set<string>();
    const merged: OnboardingTitle[] = [];
    for (const item of [...addedTitles, ...onboardingTitles]) {
      const key = item.title.toLowerCase();
      if (seen.has(key)) continue;
      seen.add(key);
      merged.push(item);
    }
    return merged;
  })();

  const [result, setResult] = useState<RecommendResponse | null>(null);
  const [loading, setLoading] = useState(false);
  const [refining, setRefining] = useState(false);
  const [error, setError] = useState("");
  const [feedbackState, setFeedbackState] = useState<Record<number, FeedbackStatus>>({});
  const [selectedRec, setSelectedRec] = useState<Recommendation | null>(null);

  useEffect(() => {
    if (!authLoading && !isAuthenticated) {
      navigate("/login");
    }
  }, [authLoading, isAuthenticated, navigate]);

  // watchlist needs a zip (only the zip carries one); recent needs real watch
  // dates (manual ratings have none) — fall back to profile if the current
  // source can't serve the selected mode
  useEffect(() => {
    if (
      (mode === "watchlist" && importMethod !== "zip") ||
      (mode === "recent" && importMethod === "manual")
    ) {
      setMode("profile");
    }
  }, [importMethod, mode]);

  // fetch the seed titles the first time onboarding is opened
  useEffect(() => {
    if (importMethod !== "manual" || onboardingTitles.length || loadingTitles || !token) return;
    setLoadingTitles(true);
    fetch(`${API_BASE_URL}/onboarding/titles`, { headers: { Authorization: `Bearer ${token}` } })
      .then((r) => (r.ok ? r.json() : null))
      .then((body: { titles: OnboardingTitle[] } | null) => {
        if (body) setOnboardingTitles(body.titles);
      })
      .catch(() => {})
      .finally(() => setLoadingTitles(false));
  }, [importMethod, onboardingTitles.length, loadingTitles, token]);

  function rateManual(title: string, rating: number | null) {
    setManualRatings((prev) => {
      const next = { ...prev };
      if (rating === null) delete next[title];
      else next[title] = rating;
      return next;
    });
  }

  // debounced TMDb search for a seen film that isn't in the seed list
  useEffect(() => {
    const query = searchQuery.trim();
    if (importMethod !== "manual" || query.length < 2 || !token) {
      setSearchResults([]);
      return;
    }
    const controller = new AbortController();
    const timer = setTimeout(() => {
      fetch(`${API_BASE_URL}/onboarding/search?q=${encodeURIComponent(query)}`, {
        headers: { Authorization: `Bearer ${token}` },
        signal: controller.signal,
      })
        .then((r) => (r.ok ? r.json() : null))
        .then((body: { titles: OnboardingTitle[] } | null) => {
          if (body) setSearchResults(body.titles);
        })
        .catch(() => {});
    }, 350);
    return () => {
      clearTimeout(timer);
      controller.abort();
    };
  }, [searchQuery, importMethod, token]);

  function addSearchedTitle(item: OnboardingTitle) {
    const exists = manualTitles.some((t) => t.title.toLowerCase() === item.title.toLowerCase());
    if (exists) {
      toast.info("Esa peli ya está en la lista.");
    } else {
      setAddedTitles((prev) => [item, ...prev]);
    }
    setSearchQuery("");
    setSearchResults([]);
  }

  const processFile = useCallback((file: File) => {
    if (!file.name.toLowerCase().endsWith(".zip")) {
      toast.error("Eso no es un .zip — exportá tu data desde Letterboxd y subí ese archivo.");
      return;
    }
    setZipFile(file);
  }, []);

  function handleDrop(event: React.DragEvent<HTMLDivElement>) {
    event.preventDefault();
    setIsDragging(false);
    const dropped = event.dataTransfer.files[0];
    if (dropped) processFile(dropped);
  }

  function handleFileInput(event: React.ChangeEvent<HTMLInputElement>) {
    const file = event.target.files?.[0];
    if (file) processFile(file);
  }

  function toggleGenre(key: string) {
    setSelectedGenres((prev) => (prev.includes(key) ? prev.filter((g) => g !== key) : [...prev, key]));
  }

  const hasSource =
    importMethod === "zip"
      ? Boolean(zipFile)
      : importMethod === "username"
        ? letterboxdUsername.trim().length > 0
        : manualCount >= MIN_MANUAL_RATINGS;
  const step2Valid = mode !== "genres" || selectedGenres.length > 0;
  const canGenerate = hasSource && step2Valid;

  // hint junto al botón deshabilitado: qué falta para poder continuar
  const step1Hint =
    importMethod === "zip"
      ? "Subí tu .zip para continuar."
      : importMethod === "username"
        ? "Escribí tu usuario de Letterboxd para continuar."
        : `Puntuá al menos ${MIN_MANUAL_RATINGS} pelis para continuar.`;

  async function handleGenerate() {
    if (!token || !canGenerate) return;
    setLoading(true);
    setError("");

    // fast first render everywhere: get the heuristic picks now (refine off),
    // swap in the LLM-written reasons afterward via the refine endpoint so the
    // user isn't waiting on the ~5-15s model call to see anything
    try {
      let response: Response;
      if (importMethod === "manual") {
        response = await fetch(`${API_BASE_URL}/recommend/manual`, {
          method: "POST",
          headers: { "Content-Type": "application/json", Authorization: `Bearer ${token}` },
          body: JSON.stringify({
            ratings: Object.entries(manualRatings).map(([title, rating]) => ({ title, rating })),
            mood: "",
            mode,
            kind_filter: kindFilter,
            genres: mode === "genres" ? selectedGenres.join(",") : "",
            refine: false,
          }),
        });
      } else {
        const formData = new FormData();
        formData.append("mode", mode);
        formData.append("kind_filter", kindFilter);
        formData.append("genres", mode === "genres" ? selectedGenres.join(",") : "");
        formData.append("refine", "0");

        let endpoint = `${API_BASE_URL}/recommend/zip`;
        if (importMethod === "zip") {
          if (!zipFile) return;
          formData.append("file", zipFile);
        } else {
          endpoint = `${API_BASE_URL}/recommend/letterboxd`;
          formData.append("username", letterboxdUsername.trim());
        }

        response = await fetch(endpoint, {
          method: "POST",
          headers: { Authorization: `Bearer ${token}` },
          body: formData,
        });
      }

      if (!response.ok) {
        const body = await response.json().catch(() => null);
        throw new Error(body?.detail ?? "No pude hablar con el backend.");
      }

      const data = (await response.json()) as RecommendResponse;
      if (!data.recommendations.length) {
        throw new Error(
          result
            ? "No encontré picks nuevos para esta búsqueda — ya te mostré todo lo que tenemos. Probá cambiar el modo, el género o el formato."
            : "No pude leer ratings válidos de esa fuente."
        );
      }

      setResult(data);
      setFeedbackState({});
      toast.success("Tus picks están listos.");
      if (data.session_id != null) void refineSession(data.session_id);
    } catch (err) {
      const message = err instanceof Error ? err.message : "Falló la recomendación.";
      setError(message);
      toast.error(message);
    } finally {
      setLoading(false);
    }
  }

  async function refineSession(sessionId: number) {
    if (!token) return;
    setRefining(true);
    try {
      const response = await fetch(`${API_BASE_URL}/recommend/sessions/${sessionId}/refine`, {
        method: "POST",
        headers: { Authorization: `Bearer ${token}` },
      });
      if (!response.ok) return;

      const refined = (await response.json()) as RecommendResponse;
      if (!refined.refined) return;

      const whyById = new Map(refined.recommendations.map((r) => [r.id, r.why]));
      setResult((prev) => {
        // guard against a stale refine landing after the user regenerated:
        // only patch the result this refine actually belongs to
        if (!prev || prev.session_id !== refined.session_id) return prev;
        return {
          ...prev,
          taste_summary: refined.taste_summary,
          recommendations: prev.recommendations.map((rec) => ({
            ...rec,
            why: whyById.get(rec.id) ?? rec.why,
          })),
        };
      });
    } catch {
      // refine is best-effort; on any failure the heuristic picks just stay
    } finally {
      setRefining(false);
    }
  }

  async function submitFeedback(recommendationId: number, status: FeedbackStatus) {
    if (!token) return;
    try {
      const response = await fetch(`${API_BASE_URL}/feedback`, {
        method: "POST",
        headers: { "Content-Type": "application/json", Authorization: `Bearer ${token}` },
        body: JSON.stringify({ recommendation_id: recommendationId, status }),
      });

      if (!response.ok) throw new Error();
      setFeedbackState((prev) => ({ ...prev, [recommendationId]: status }));
    } catch {
      toast.error("No se pudo guardar el feedback.");
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
      <main className="max-w-7xl mx-auto px-6 pt-16 pb-24">
        <header className="pb-10 border-b-2 border-foreground mb-12">
          <div className="font-mono text-[10px] uppercase tracking-widest text-muted-foreground mb-4">
            [Personalizado para vos]
          </div>
          <h1 className="text-6xl md:text-7xl font-black uppercase tracking-tighter leading-[0.9]">
            Tus <span className="text-accent italic font-serif normal-case tracking-normal">picks</span> de peli
          </h1>
        </header>

        {!result && !loading && (
          <div className="max-w-4xl">
            {/* Stepper: pasos completados clickeables para volver */}
            <div className="flex items-center gap-3 mb-12 font-mono text-[10px] uppercase tracking-widest">
              {STEP_LABELS.map((label, i) => {
                const n = (i + 1) as WizardStep;
                const done = step > n;
                const current = step === n;
                return (
                  <React.Fragment key={label}>
                    {i > 0 && <span className="text-muted-foreground/40">→</span>}
                    <button
                      type="button"
                      onClick={() => done && setStep(n)}
                      disabled={!done}
                      className={`flex items-center gap-2 transition-colors ${
                        current
                          ? "text-foreground"
                          : done
                            ? "text-muted-foreground hover:text-accent"
                            : "text-muted-foreground/40 cursor-default"
                      }`}
                    >
                      <span
                        className={`size-5 grid place-items-center border text-[10px] ${
                          current
                            ? "bg-accent text-accent-foreground border-accent"
                            : done
                              ? "bg-foreground text-background border-foreground"
                              : "border-foreground/30"
                        }`}
                      >
                        {done ? "✓" : n}
                      </span>
                      {label}
                    </button>
                  </React.Fragment>
                );
              })}
            </div>

            {step === 1 && (
              <section>
                <h2 className="text-3xl font-black uppercase tracking-tighter mb-3">
                  ¿De dónde sacamos tu gusto?
                </h2>
                <p className="font-serif italic text-lg text-muted-foreground mb-8 max-w-2xl">
                  Para recomendarte en serio primero tenemos que conocerte. Elegí cómo nos
                  contás qué viste y qué te gustó.
                </p>

                <div className="flex gap-0 mb-6 max-w-xl">
                  <button onClick={() => setImportMethod("zip")} className={tabCls(importMethod === "zip")}>
                    Subir .zip
                  </button>
                  <button onClick={() => setImportMethod("username")} className={tabCls(importMethod === "username")}>
                    Username
                  </button>
                  <button onClick={() => setImportMethod("manual")} className={tabCls(importMethod === "manual")}>
                    Sin cuenta
                  </button>
                </div>

                {importMethod === "zip" ? (
                  <div className="max-w-xl">
                    <p className="font-mono text-[10px] uppercase leading-relaxed text-muted-foreground mb-3">
                      La mejor opción: trae tu historial completo (ratings, reviews, likes,
                      watchlist). Descargalo desde Letterboxd: Settings → Data → Export your
                      data.
                    </p>
                    <div
                      onDrop={handleDrop}
                      onDragOver={(e) => {
                        e.preventDefault();
                        setIsDragging(true);
                      }}
                      onDragLeave={() => setIsDragging(false)}
                      onClick={() => fileInputRef.current?.click()}
                      className={`border-2 border-dashed p-8 text-center cursor-pointer transition-colors ${
                        isDragging ? "border-accent bg-accent/5" : "border-foreground/30 hover:border-foreground"
                      }`}
                    >
                      <input ref={fileInputRef} type="file" accept=".zip,application/zip" onChange={handleFileInput} className="hidden" />
                      <div className="font-mono text-xs uppercase tracking-widest mb-2">
                        {isDragging ? "Soltalo acá" : "Arrastrá tu .zip acá"}
                      </div>
                      <div className="font-mono text-[10px] text-muted-foreground mb-3">o click para elegir</div>
                      {zipFile ? (
                        <div className="inline-flex items-center gap-2 font-mono text-[10px] text-accent">
                          <CheckCircle className="w-3 h-3" />
                          {zipFile.name} · {formatFileSize(zipFile.size)}
                        </div>
                      ) : (
                        <div className="font-mono text-[10px] text-muted-foreground/60">Solo .zip</div>
                      )}
                    </div>
                  </div>
                ) : importMethod === "username" ? (
                  <div className="max-w-xl">
                    <p className="font-mono text-[10px] uppercase leading-relaxed text-muted-foreground mb-3">
                      Leemos tu diario público de Letterboxd (ratings, fechas, rewatches).
                      Trae solo lo reciente — el .zip arma un perfil más completo. Tu perfil
                      tiene que ser público.
                    </p>
                    <input
                      value={letterboxdUsername}
                      onChange={(e) => setLetterboxdUsername(e.target.value)}
                      placeholder="ej: scorsese"
                      className="w-full bg-transparent border-b-2 border-foreground py-3 font-mono text-sm placeholder:text-muted-foreground focus:outline-none focus:border-accent"
                    />
                  </div>
                ) : (
                  <div>
                    {/* feedback Gaspi: dejar clarísimo que esta grilla es para
                        conocerte, no el resultado; feedback Simón: ser honestos
                        con el límite del modo manual */}
                    <p className="font-mono text-[10px] uppercase leading-relaxed text-muted-foreground mb-2 max-w-2xl">
                      Estas pelis no son recomendaciones — son para conocerte. Puntuá las que
                      hayas visto y con eso armamos tu perfil. Tus picks aparecen al final.
                    </p>
                    <p className="font-mono text-[10px] uppercase leading-relaxed text-muted-foreground/60 mb-6 max-w-2xl">
                      Ojo: acá solo sabemos de las pelis que puntúes en esta lista, así que
                      algún pick puede ser una que ya viste. Si tenés Letterboxd, el .zip
                      evita eso.
                    </p>

                    <div className="flex items-baseline justify-between gap-4 mb-4 flex-wrap">
                      <div className="font-mono text-xs uppercase tracking-widest">
                        <span className={manualCount >= MIN_MANUAL_RATINGS ? "text-accent" : ""}>
                          {manualCount}
                        </span>{" "}
                        / {MIN_MANUAL_RATINGS} puntuadas
                      </div>
                    </div>

                    {/* buscar una peli vista que no esté en la lista curada */}
                    <div className="relative mb-6 max-w-xl">
                      <input
                        value={searchQuery}
                        onChange={(e) => setSearchQuery(e.target.value)}
                        placeholder="¿Viste otra? Buscala por nombre…"
                        className="w-full bg-transparent border-b-2 border-foreground py-3 font-mono text-sm placeholder:text-muted-foreground focus:outline-none focus:border-accent"
                      />
                      {searchResults.length > 0 && (
                        <div className="absolute z-20 left-0 right-0 mt-1 max-h-80 overflow-y-auto border-2 border-foreground bg-background shadow-lg">
                          {searchResults.map((item) => (
                            <button
                              key={`${item.tmdb_id}-${item.title}`}
                              onClick={() => addSearchedTitle(item)}
                              className="w-full flex items-center gap-3 px-3 py-2 text-left hover:bg-accent/10 transition-colors border-b border-foreground/10 last:border-b-0"
                            >
                              {item.poster_path ? (
                                <img src={item.poster_path} alt="" className="w-8 h-12 object-cover shrink-0" />
                              ) : (
                                <div className="w-8 h-12 bg-secondary flex items-center justify-center shrink-0">
                                  <Film className="w-3 h-3 text-muted-foreground/40" />
                                </div>
                              )}
                              <span className="font-mono text-xs">
                                {item.title} <span className="text-muted-foreground">({item.year})</span>
                              </span>
                            </button>
                          ))}
                        </div>
                      )}
                    </div>

                    <ManualRatingGrid
                      titles={manualTitles}
                      ratings={manualRatings}
                      loading={loadingTitles}
                      onRate={rateManual}
                    />
                  </div>
                )}
              </section>
            )}

            {step === 2 && (
              <section>
                <h2 className="text-3xl font-black uppercase tracking-tighter mb-3">
                  ¿Qué querés ver hoy?
                </h2>
                <p className="font-serif italic text-lg text-muted-foreground mb-8 max-w-2xl">
                  Todos los modos usan tu perfil — lo que cambia es desde dónde arranca la
                  búsqueda.
                </p>

                <div className="space-y-3 max-w-2xl">
                  {modeOptions.map((option) => {
                    const disabled =
                      (option.mode === "watchlist" && importMethod !== "zip") ||
                      (option.mode === "recent" && importMethod === "manual");
                    const disabledReason =
                      option.mode === "watchlist"
                        ? "Solo con .zip: la watchlist no viene por las otras vías."
                        : "Necesita fechas de visto, que el modo sin cuenta no tiene.";
                    return (
                      <button
                        key={option.mode}
                        onClick={() => !disabled && setMode(option.mode)}
                        disabled={disabled}
                        className={`w-full text-left px-5 py-4 border transition-colors disabled:opacity-40 disabled:cursor-not-allowed ${
                          mode === option.mode
                            ? "bg-foreground text-background border-foreground"
                            : "border-foreground/20 hover:border-foreground"
                        }`}
                      >
                        <div className="font-mono text-xs uppercase tracking-widest mb-1">
                          <span className="text-accent mr-2">{mode === option.mode ? "●" : "○"}</span>
                          {option.label}
                        </div>
                        <div
                          className={`font-serif italic text-sm ${
                            mode === option.mode ? "text-background/70" : "text-muted-foreground"
                          }`}
                        >
                          {disabled ? disabledReason : option.desc}
                        </div>
                      </button>
                    );
                  })}
                </div>

                {mode === "genres" && (
                  <div className="mt-6 flex flex-wrap gap-2 max-w-2xl">
                    {genreOptions.map((genre) => (
                      <button
                        key={genre.key}
                        onClick={() => toggleGenre(genre.key)}
                        className={`px-3 py-1.5 font-mono text-[10px] uppercase tracking-widest border transition-colors ${
                          selectedGenres.includes(genre.key)
                            ? "bg-accent text-accent-foreground border-accent"
                            : "border-foreground/20 hover:border-foreground"
                        }`}
                      >
                        {genre.label}
                      </button>
                    ))}
                  </div>
                )}
                {mode === "genres" && selectedGenres.length === 0 && (
                  <p className="font-mono text-[10px] text-destructive mt-3">Elegí al menos un género.</p>
                )}
              </section>
            )}

            {step === 3 && (
              <section>
                <h2 className="text-3xl font-black uppercase tracking-tighter mb-3">
                  ¿Películas, series o ambas?
                </h2>
                <p className="font-serif italic text-lg text-muted-foreground mb-8 max-w-2xl">
                  Último paso. Elegí el formato y pedí tus picks.
                </p>

                <div className="flex gap-0 max-w-xl mb-8">
                  {kindFilterOptions.map((option) => (
                    <button key={option.value} onClick={() => setKindFilter(option.value)} className={tabCls(kindFilter === option.value)}>
                      {option.label}
                    </button>
                  ))}
                </div>

                <p className="font-mono text-[10px] uppercase tracking-widest text-muted-foreground mb-8">
                  Fuente:{" "}
                  {importMethod === "zip"
                    ? `.zip (${zipFile?.name ?? ""})`
                    : importMethod === "username"
                      ? `@${letterboxdUsername.trim()}`
                      : `${manualCount} pelis puntuadas`}{" "}
                  · Modo: {modeOptions.find((o) => o.mode === mode)?.label}
                  {mode === "genres" &&
                    ` (${selectedGenres
                      .map((k) => genreOptions.find((g) => g.key === k)?.label)
                      .filter(Boolean)
                      .join(", ")})`}
                </p>

                {/* feedback punto 3: explicar cómo se calculan los picks, en el
                    lugar donde el usuario está por pedirlos */}
                <details className="max-w-2xl mb-4 border border-foreground/20">
                  <summary className="cursor-pointer px-4 py-3 font-mono text-[10px] uppercase tracking-widest text-muted-foreground hover:text-accent transition-colors">
                    ¿Cómo se calculan tus picks?
                  </summary>
                  <div className="px-4 pb-4 font-serif text-sm leading-relaxed space-y-2">
                    <p>
                      Armamos tu perfil con lo que puntuaste: géneros, directores, décadas y
                      tags de lo que amaste y lo que odiaste. Con eso buscamos candidatos en
                      TMDb y los puntuamos contra tu perfil — cada pick trae la razón
                      concreta del match, no un promedio global.
                    </p>
                    <p>
                      Arriba de eso, un agente de IA revisa los candidatos y reescribe las
                      razones citando películas reales de tu historial. Tu feedback (ya la
                      vi / no me interesa) entra al cálculo de la próxima tanda.
                    </p>
                  </div>
                </details>
              </section>
            )}

            {/* Navegación del wizard */}
            <div className="flex items-center justify-between gap-4 mt-12 pt-8 border-t border-foreground/10">
              {step > 1 ? (
                <button
                  onClick={() => setStep((s) => (s - 1) as WizardStep)}
                  className="font-mono text-[10px] uppercase tracking-widest text-muted-foreground hover:text-accent transition-colors"
                >
                  ← Volver
                </button>
              ) : (
                <span />
              )}

              <div className="flex items-center gap-4">
                {step === 1 && !hasSource && (
                  <span className="font-mono text-[10px] uppercase tracking-widest text-muted-foreground/60">
                    {step1Hint}
                  </span>
                )}
                {step < 3 ? (
                  <button
                    onClick={() => setStep((s) => (s + 1) as WizardStep)}
                    disabled={step === 1 ? !hasSource : !step2Valid}
                    className="px-8 py-4 bg-foreground text-background font-mono text-xs uppercase tracking-widest hover:bg-accent hover:text-accent-foreground transition-colors disabled:opacity-40 disabled:cursor-not-allowed"
                  >
                    Continuar →
                  </button>
                ) : (
                  <button
                    onClick={handleGenerate}
                    disabled={loading || !canGenerate}
                    className="px-8 py-4 bg-accent text-accent-foreground font-mono text-xs uppercase tracking-widest hover:bg-foreground hover:text-background transition-colors disabled:opacity-60"
                  >
                    Dame mis recomendaciones
                  </button>
                )}
              </div>
            </div>
          </div>
        )}

        {loading && (
          <div className="py-20 text-center">
            <Loader2 className="w-7 h-7 text-accent animate-spin mx-auto mb-6" />
            <h3 className="text-2xl font-black uppercase tracking-tighter mb-3">Buscando tus pelis...</h3>
            <p className="font-mono text-xs uppercase text-muted-foreground max-w-sm mx-auto">
              Leyendo tu historial y buscando candidatos que encajen con tu gusto.
            </p>
          </div>
        )}

        {error && !loading ? (
          <div className="mt-4 p-4 border-2 border-destructive/50 flex items-start gap-3">
            <AlertCircle className="w-5 h-5 text-destructive shrink-0 mt-0.5" />
            <p className="font-mono text-xs text-destructive">{error}</p>
          </div>
        ) : null}

        {result && !loading && (
          <>
            <div className="mb-12">
              <div className="flex items-center gap-4 flex-wrap">
                <span className="font-mono text-xs px-2 py-1 border border-foreground/20 shrink-0">
                  [Resultados · {result.recommendations.length}]
                </span>
                <div className="h-px flex-grow bg-foreground/10 min-w-8" />
                <div className="flex gap-4 shrink-0">
                  <button
                    onClick={handleGenerate}
                    className="font-mono text-[10px] uppercase tracking-widest hover:text-accent transition-colors"
                  >
                    ↻ Nuevos picks
                  </button>
                  <button
                    onClick={() => {
                      setResult(null);
                      setFeedbackState({});
                    }}
                    className="font-mono text-[10px] uppercase tracking-widest hover:text-accent transition-colors"
                  >
                    Cambiar búsqueda
                  </button>
                </div>
              </div>
              <p className="font-mono text-[10px] uppercase tracking-widest text-muted-foreground mt-3">
                {result.taste_summary}
                {refining && (
                  <span className="ml-2 inline-flex items-center gap-1 text-accent normal-case">
                    <Loader2 className="w-3 h-3 animate-spin" /> puliendo las razones…
                  </span>
                )}
              </p>
            </div>

            {/* feedback: a 2 columnas en desktop ancho cada poster salía más
                alto que el viewport — 3 columnas achican a ~600px y los 6
                picks entran en 2 filas */}
            <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-10">
              {result.recommendations.map((rec, i) => (
                <RecommendationCard
                  key={rec.id}
                  rec={rec}
                  index={i}
                  feedback={feedbackState[rec.id]}
                  onSelect={() => setSelectedRec(rec)}
                />
              ))}
            </div>
          </>
        )}

        {selectedRec && (
          <MovieModal
            key={selectedRec.id}
            rec={selectedRec}
            token={token}
            feedback={feedbackState[selectedRec.id]}
            onClose={() => setSelectedRec(null)}
            onFeedback={(status) => submitFeedback(selectedRec.id, status)}
          />
        )}
      </main>
    </PageTransition>
  );
}
