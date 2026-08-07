import {
  AlertCircle,
  CheckCircle,
  Film,
  Loader2,
} from "lucide-react";
import React, { useCallback, useEffect, useRef, useState } from "react";
import { toast } from "sonner";
import { useLocation } from "wouter";

import { MovieModal, type FeedbackStatus, type Recommendation } from "@/components/MovieModal";
import { PageTransition } from "@/components/PageTransition";
import { PosterCard } from "@/components/PosterCard";
import { StarRating } from "@/components/StarRating";
import { API_BASE_URL, useAuth } from "@/hooks/useAuth";
import { useSwipeCard } from "@/hooks/useSwipeCard";
import { useTiltCard } from "@/hooks/useTiltCard";
import { useLang } from "@/lib/i18n";

type RecommendResponse = {
  taste_summary: string;
  recommendations: Recommendation[];
  discarded_rows: number;
  session_id: number | null;
  refined: boolean;
  ephemeral: boolean;
};

type RecommendMode = "profile" | "recent" | "genres" | "watchlist";
type KindFilter = "movie" | "series" | "both";

// desc: qué hace cada modo, visible en el paso 2 del wizard (feedback: "no
// entiendo qué significa cada opción"). Guardamos claves, no texto: una
// constante de módulo no puede llamar a t().
const modeOptions: { mode: RecommendMode; labelKey: string; descKey: string }[] = [
  { mode: "profile", labelKey: "recommend.modeProfile", descKey: "recommend.modeProfileDesc" },
  { mode: "recent", labelKey: "recommend.modeRecent", descKey: "recommend.modeRecentDesc" },
  { mode: "genres", labelKey: "recommend.modeGenres", descKey: "recommend.modeGenresDesc" },
  { mode: "watchlist", labelKey: "recommend.modeWatchlist", descKey: "recommend.modeWatchlistDesc" },
];

// wizard de 3 pasos (feedback: la página anterior tiraba todo junto y los
// usuarios nuevos no sabían por dónde empezar)
type WizardStep = 1 | 2 | 3;
const STEP_LABEL_KEYS = ["recommend.step1Label", "recommend.step2Label", "recommend.step3Label"];

const kindFilterOptions: { value: KindFilter; labelKey: string }[] = [
  { value: "movie", labelKey: "common.movies" },
  { value: "series", labelKey: "common.series" },
  { value: "both", labelKey: "common.both" },
];

// cargadas desde GET /recommend/options (backend/app/recommender.py::PICK_OPTIONS)
// -- ya no hardcodeadas acá, con 7 opciones duplicarlas a mano era tolerable,
// con 25+ garantiza que se desincronicen.
type PickOption = { key: string; label: string; group: string };
const PICK_GROUP_LABEL_KEYS: Record<string, string> = {
  generos: "recommend.groupGeneros",
  vibras: "recommend.groupVibras",
  movimientos: "recommend.groupMovimientos",
};
const MAX_SELECTED_OPTIONS = 5; // mismo tope que backend/app/main.py::MAX_SELECTED_OPTIONS

type ImportMethod = "zip" | "username" | "manual";

// onboarding without Letterboxd: rate seed titles by hand
export type OnboardingTitle = {
  title: string;
  year: number;
  kind: string;
  tmdb_id: number | null;
  poster_path: string | null;
  // solo viene seteado si el usuario ya puntuó este título antes — precarga
  // la grilla en vez de forzar a re-puntuar lo mismo cada sesión
  rating?: number | null;
  rating_source?: "import" | "manual" | "like" | "star" | "game" | null;
};

const MIN_MANUAL_RATINGS = 10; // keep in sync with backend/app/main.py::MIN_MANUAL_RATINGS
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
  return (
    <PosterCard rec={rec} index={index + 1} feedback={feedback} featured onSelect={onSelect}>
      <div className="flex justify-between items-baseline gap-4 mb-4">
        <h3 className="text-2xl font-black uppercase tracking-tighter leading-none group-hover:text-accent transition-colors">
          {rec.title}
        </h3>
        <span className="font-mono text-xs text-muted-foreground shrink-0">{rec.year}</span>
      </div>
    </PosterCard>
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
  const { t } = useLang();
  const letterboxdRating = item.rating_source === "import";

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
      <div className="font-mono text-[10px] text-muted-foreground mb-2">{item.year || ""}</div>
      <div className="mt-auto">
        <StarRating
          value={current}
          onChange={(rating) => onRate(item.title, rating)}
          size="sm"
          disabled={letterboxdRating}
        />
        {letterboxdRating ? (
          <p className="mt-1 text-center font-mono text-[8px] uppercase tracking-wider text-accent">
            {t("recommend.letterboxdRating")}
          </p>
        ) : (
          <button
            onClick={() => onRate(item.title, null)}
            className="mt-1 w-full py-1 font-mono text-[9px] uppercase tracking-wider text-muted-foreground hover:text-foreground transition-colors"
          >
            {t("recommend.notSeen")}
          </button>
        )}
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

const swipeActionBtn =
  "flex-1 py-3 font-mono text-[10px] uppercase tracking-widest border transition-colors border-foreground/20 hover:border-foreground";

const LETTERBOXD_USERNAMES_KEY = "butaca.letterboxdUsernames";
const MAX_REMEMBERED_USERNAMES = 5;

// Vista de a una. Las estrellas reemplazan los tres gestos sintéticos; el
// swipe hacia abajo queda como atajo de "No la vi".
function SwipeRating({
  titles,
  ratings,
  onRate,
}: {
  titles: OnboardingTitle[];
  ratings: Record<string, number>;
  onRate: (title: string, rating: number | null) => void;
}) {
  const { t } = useLang();
  const [skipped, setSkipped] = useState<Set<string>>(new Set());
  const remaining = titles.filter((t) => ratings[t.title] === undefined && !skipped.has(t.title));
  const current = remaining[0] as OnboardingTitle | undefined;
  const doneCount = titles.length - remaining.length;

  function rate(rating: number | null) {
    if (!current) return;
    if (rating === null) {
      setSkipped((prev) => new Set(prev).add(current.title));
    } else {
      onRate(current.title, rating);
    }
  }

  const { cardRef, hint, onPointerDown, onPointerMove, onPointerUp } = useSwipeCard({
    down: () => rate(null),
  });

  if (!current) {
    return (
      <p className="font-mono text-[10px] uppercase tracking-widest text-muted-foreground text-center py-16">
        {doneCount > 0 ? t("recommend.swipeAllRated") : t("recommend.swipeEmpty")}
      </p>
    );
  }

  return (
    <div>
      <div className="font-mono text-[10px] uppercase tracking-widest text-muted-foreground text-center mb-4">
        {doneCount} / {titles.length}
      </div>
      {/* touchAction none, no pan-y: ahora el swipe también usa el eje
          vertical, y con pan-y el navegador se queda el gesto para scrollear */}
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
                {t("recommend.notSeen")}
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
            <div className="font-black uppercase text-lg tracking-tighter leading-none">{current.title}</div>
            <div className="font-mono text-[10px] text-muted-foreground mt-1">{current.year || ""}</div>
          </div>
        </div>
      </div>

      <div className="max-w-xs mx-auto mt-6">
        <StarRating onChange={rate} size="lg" />
        <button onClick={() => rate(null)} className={`${swipeActionBtn} w-full mt-2`}>
          {t("recommend.notSeen")}
        </button>
      </div>
      <p className="text-center font-mono text-[9px] text-muted-foreground/60 mt-3">
        {t("recommend.swipeHint")}
      </p>
    </div>
  );
}

// ─── Main Page ───────────────────────────────────────────────────────────────

export default function Recommend() {
  const { isAuthenticated, loading: authLoading, token, user } = useAuth();
  const { t, lang } = useLang();
  const [, navigate] = useLocation();

  const [step, setStep] = useState<WizardStep>(1);
  const [mode, setMode] = useState<RecommendMode>("profile");
  const [kindFilter, setKindFilter] = useState<KindFilter>("movie");
  const [selectedGenres, setSelectedGenres] = useState<string[]>([]);
  const [pickOptions, setPickOptions] = useState<PickOption[]>([]);

  // picker "a tu elección" — público, sin auth, se carga una sola vez al
  // montar (no depende de sesión ni de mode)
  useEffect(() => {
    fetch(`${API_BASE_URL}/recommend/options`)
      .then((r) => (r.ok ? r.json() : null))
      .then((body: { options: PickOption[] } | null) => {
        if (body) setPickOptions(body.options);
      })
      .catch(() => {});
  }, []);

  const [importMethod, setImportMethod] = useState<ImportMethod>("zip");
  const [zipFile, setZipFile] = useState<File | null>(null);
  const [letterboxdUsername, setLetterboxdUsername] = useState("");
  const [isDragging, setIsDragging] = useState(false);
  const fileInputRef = useRef<HTMLInputElement>(null);

  // Pedido de Matías (2026-07-31): que recuerde los usuarios que vas poniendo,
  // y que el tuyo esté precargado. El tuyo es dato del perfil (decide si el
  // import escribe en tu cuenta); el historial de los otros es solo comodidad,
  // así que vive en localStorage y se ofrece con un <datalist> nativo.
  const [rememberedUsernames, setRememberedUsernames] = useState<string[]>(() => {
    try {
      const stored = JSON.parse(localStorage.getItem(LETTERBOXD_USERNAMES_KEY) ?? "[]");
      return Array.isArray(stored) ? stored.filter((x) => typeof x === "string") : [];
    } catch {
      return [];
    }
  });

  useEffect(() => {
    if (user?.letterboxdUsername) setLetterboxdUsername(user.letterboxdUsername);
  }, [user?.letterboxdUsername]);

  const isForeignAccount =
    Boolean(user?.letterboxdUsername) &&
    letterboxdUsername.trim().length > 0 &&
    letterboxdUsername.trim().toLowerCase() !== user!.letterboxdUsername!.toLowerCase();

  function rememberUsername(name: string) {
    const trimmed = name.trim();
    if (!trimmed) return;
    setRememberedUsernames((prev) => {
      const next = [trimmed, ...prev.filter((x) => x.toLowerCase() !== trimmed.toLowerCase())].slice(
        0,
        MAX_REMEMBERED_USERNAMES,
      );
      localStorage.setItem(LETTERBOXD_USERNAMES_KEY, JSON.stringify(next));
      return next;
    });
  }

  // onboarding without Letterboxd: seed titles fetched lazily, ratings by title
  const [onboardingTitles, setOnboardingTitles] = useState<OnboardingTitle[]>([]);
  const [loadingTitles, setLoadingTitles] = useState(false);
  const [manualRatings, setManualRatings] = useState<Record<string, number>>({});
  // titles the user searched and added (seen a film that isn't in the seed list)
  const [addedTitles, setAddedTitles] = useState<OnboardingTitle[]>([]);
  const [searchQuery, setSearchQuery] = useState("");
  const [searchResults, setSearchResults] = useState<OnboardingTitle[]>([]);
  // mismo umbral que el debounce de más abajo (2 caracteres) — mientras hay
  // una búsqueda activa, la grilla de posters muestra los resultados en vez
  // de la lista semilla
  const isSearching = searchQuery.trim().length >= 2;
  const manualCount = Object.keys(manualRatings).length;
  // pedido de Matías: el modo swipe es una preferencia del usuario, no un
  // reemplazo — arranca en grilla (comportamiento de siempre)
  const [ratingView, setRatingView] = useState<"grid" | "swipe">("grid");

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
  // qué "why" ya se mostró (typewriter o texto directo) por rec.id en esta
  // sesión — vive acá, no en MovieModal, porque el modal se desmonta al
  // cerrar (rec.id) => <MovieModal key={rec.id} ... />; un ref porque nada
  // en esta página necesita re-renderizar cuando cambia
  const seenWhysRef = useRef<Map<number, string>>(new Map());
  const [loading, setLoading] = useState(false);
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

  // fetch the seed titles the first time onboarding is opened — the backend
  // merges in anything the user already rated before (any source), so a
  // returning user sees those pre-filled and can still edit or add more
  // (reemplaza el banner "Usar mi perfil" todo-o-nada)
  useEffect(() => {
    if (importMethod !== "manual" || onboardingTitles.length || loadingTitles || !token) return;
    setLoadingTitles(true);
    fetch(`${API_BASE_URL}/onboarding/titles`, { headers: { Authorization: `Bearer ${token}` } })
      .then((r) => (r.ok ? r.json() : null))
      .then((body: { titles: OnboardingTitle[] } | null) => {
        if (!body) return;
        setOnboardingTitles(body.titles);
        const prefilled = Object.fromEntries(
          body.titles
            .filter((t) => t.rating != null && (t.rating_source === "import" || t.rating_source === "star"))
            .map((t) => [t.title, t.rating as number])
        );
        if (Object.keys(prefilled).length) {
          setManualRatings((prev) => ({ ...prefilled, ...prev }));
        }
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

  // feedback: los resultados de la búsqueda solo aparecían en un dropdown
  // angosto arriba del input — ahora se puntúan directo como posters en la
  // misma grilla de abajo, sin un paso intermedio de "agregar" separado
  function rateSearchResult(item: OnboardingTitle, rating: number | null) {
    const exists = manualTitles.some((t) => t.title.toLowerCase() === item.title.toLowerCase());
    if (!exists) setAddedTitles((prev) => [item, ...prev]);
    rateManual(item.title, rating);
    setSearchQuery("");
    setSearchResults([]);
  }

  const processFile = useCallback((file: File) => {
    if (!file.name.toLowerCase().endsWith(".zip")) {
      toast.error(t("recommend.notAZip"));
      return;
    }
    setZipFile(file);
  }, [t]);

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
    setSelectedGenres((prev) => {
      if (prev.includes(key)) return prev.filter((g) => g !== key);
      if (prev.length >= MAX_SELECTED_OPTIONS) return prev; // mismo tope que el backend
      return [...prev, key];
    });
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
      ? t("recommend.hintZip")
      : importMethod === "username"
        ? t("recommend.hintUsername")
        : t("recommend.hintManual", { n: MIN_MANUAL_RATINGS });

  async function handleGenerate() {
    if (!token || !canGenerate) return;
    setLoading(true);
    setError("");

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
            refine: true,
            // el LLM del backend escribe los "why" en este idioma
            lang,
          }),
        });
      } else {
        const formData = new FormData();
        formData.append("mode", mode);
        formData.append("kind_filter", kindFilter);
        formData.append("genres", mode === "genres" ? selectedGenres.join(",") : "");
        formData.append("refine", "1");
        formData.append("lang", lang);

        let endpoint = `${API_BASE_URL}/recommend/zip`;
        if (importMethod === "zip") {
          if (!zipFile) return;
          formData.append("file", zipFile);
        } else {
          endpoint = `${API_BASE_URL}/recommend/letterboxd`;
          formData.append("username", letterboxdUsername.trim());
          rememberUsername(letterboxdUsername);
        }

        response = await fetch(endpoint, {
          method: "POST",
          headers: { Authorization: `Bearer ${token}` },
          body: formData,
        });
      }

      if (!response.ok) {
        const body = await response.json().catch(() => null);
        throw new Error(body?.detail ?? t("recommend.backendError"));
      }

      const data = (await response.json()) as RecommendResponse;
      if (!data.recommendations.length) {
        throw new Error(result ? t("recommend.noNewPicks") : t("recommend.noValidRatings"));
      }

      setResult(data);
      setFeedbackState({});
      toast.success(t("recommend.picksReady"));
    } catch (err) {
      const message = err instanceof Error ? err.message : t("recommend.generateFailed");
      setError(message);
      toast.error(message);
    } finally {
      setLoading(false);
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
      toast.error(t("recommend.feedbackFailed"));
    }
  }

  // pedido de Matías (2026-07-31): "Ya la vi" → elegir cuánto te gustó queda
  // en el perfil real (rated_items), no solo como feedback de esta sesión.
  // title/tmdbId opcionales: el botón "no estoy de acuerdo" del modal reusa
  // esto para votar películas similares, no rec en sí.
  async function rateTitle(rec: Recommendation, rating: number, title?: string, tmdbId?: number | null) {
    if (!token) return false;
    const finalTitle = title ?? rec.title;
    try {
      const response = await fetch(`${API_BASE_URL}/profile/rate`, {
        method: "POST",
        headers: { "Content-Type": "application/json", Authorization: `Bearer ${token}` },
        body: JSON.stringify({
          title: finalTitle,
          rating,
          tmdb_id: title ? tmdbId ?? null : rec.tmdb_id,
        }),
      });
      if (!response.ok) throw new Error();
      const body = await response.json();
      if (body.status === "preserved") {
        toast.info(t("recommend.ratePreserved", { rating: body.rating }));
        return true;
      }
      toast.success(t("recommend.rateSaved", { title: finalTitle }));
      return true;
    } catch {
      toast.error(t("recommend.rateFailed"));
      return false;
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
            {t("recommend.eyebrow")}
          </div>
          <h1 className="text-6xl md:text-7xl font-black uppercase tracking-tighter leading-[0.9]">
            {t("recommend.titlePre")}{" "}
            <span className="text-accent italic font-serif normal-case tracking-normal">
              {t("recommend.titleAccent")}
            </span>{" "}
            {t("recommend.titlePost")}
          </h1>
        </header>

        {!result && !loading && (
          <div className="max-w-4xl">
            {/* Stepper: pasos completados clickeables para volver */}
            <div className="flex items-center gap-3 mb-12 font-mono text-[10px] uppercase tracking-widest">
              {STEP_LABEL_KEYS.map((labelKey, i) => {
                const label = t(labelKey);
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
                  {t("recommend.step1Title")}
                </h2>
                <p className="font-serif italic text-lg text-muted-foreground mb-8 max-w-2xl">
                  {t("recommend.step1Intro")}
                </p>

                <div className="flex gap-0 mb-6 max-w-xl">
                  <button onClick={() => setImportMethod("zip")} className={tabCls(importMethod === "zip")}>
                    {t("recommend.tabZip")}
                  </button>
                  <button onClick={() => setImportMethod("username")} className={tabCls(importMethod === "username")}>
                    {t("recommend.tabUsername")}
                  </button>
                  <button onClick={() => setImportMethod("manual")} className={tabCls(importMethod === "manual")}>
                    {t("recommend.tabManual")}
                  </button>
                </div>

                {importMethod === "zip" ? (
                  <div className="max-w-xl">
                    <p className="font-mono text-[10px] uppercase leading-relaxed text-muted-foreground mb-3">
                      {t("recommend.zipHint")}
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
                        {isDragging ? t("recommend.dropActive") : t("recommend.dropIdle")}
                      </div>
                      <div className="font-mono text-[10px] text-muted-foreground mb-3">
                        {t("recommend.dropClick")}
                      </div>
                      {zipFile ? (
                        <div className="inline-flex items-center gap-2 font-mono text-[10px] text-accent">
                          <CheckCircle className="w-3 h-3" />
                          {zipFile.name} · {formatFileSize(zipFile.size)}
                        </div>
                      ) : (
                        <div className="font-mono text-[10px] text-muted-foreground/60">
                          {t("recommend.dropOnlyZip")}
                        </div>
                      )}
                    </div>
                  </div>
                ) : importMethod === "username" ? (
                  <div className="max-w-xl">
                    <p className="font-mono text-[10px] uppercase leading-relaxed text-muted-foreground mb-2">
                      {t("recommend.usernameHint")}
                    </p>
                    <p className="font-mono text-[10px] uppercase leading-relaxed text-muted-foreground/60 mb-3">
                      {t("recommend.usernameWarning")}
                    </p>
                    <input
                      value={letterboxdUsername}
                      onChange={(e) => setLetterboxdUsername(e.target.value)}
                      placeholder={t("recommend.usernamePlaceholder")}
                      list="letterboxd-usernames"
                      className="w-full bg-transparent border-b-2 border-foreground py-3 font-mono text-sm placeholder:text-muted-foreground focus:outline-none focus:border-accent"
                    />
                    {/* datalist nativo: el historial de usuarios tipeados es
                        comodidad del navegador, no dato del perfil — no
                        necesita backend */}
                    <datalist id="letterboxd-usernames">
                      {rememberedUsernames.map((name) => (
                        <option key={name} value={name} />
                      ))}
                    </datalist>
                    {isForeignAccount && (
                      <p className="font-mono text-[10px] uppercase leading-relaxed text-accent mt-3">
                        {t("recommend.foreignAccount", {
                          name: letterboxdUsername.trim(),
                          own: user?.letterboxdUsername ?? "",
                        })}
                      </p>
                    )}
                  </div>
                ) : (
                  <div>
                    {/* feedback Gaspi: dejar clarísimo que esta grilla es para
                        conocerte, no el resultado; feedback Simón: ser honestos
                        con el límite del modo manual */}
                    <p className="font-mono text-[10px] uppercase leading-relaxed text-muted-foreground mb-2 max-w-2xl">
                      {t("recommend.manualHint")}
                    </p>
                    <p className="font-mono text-[10px] uppercase leading-relaxed text-muted-foreground/60 mb-6 max-w-2xl">
                      {t("recommend.manualWarning")}
                    </p>

                    <div className="flex items-baseline justify-between gap-4 mb-4 flex-wrap">
                      <div className="font-mono text-xs uppercase tracking-widest">
                        <span className={manualCount >= MIN_MANUAL_RATINGS ? "text-accent" : ""}>
                          {manualCount}
                        </span>{" "}
                        / {MIN_MANUAL_RATINGS} {t("recommend.ratedSuffix")}
                      </div>
                      <div className="flex gap-0">
                        <button
                          onClick={() => setRatingView("grid")}
                          className={`px-4 py-2 font-mono text-[10px] uppercase tracking-widest border transition-colors ${
                            ratingView === "grid"
                              ? "bg-foreground text-background border-foreground"
                              : "border-foreground/20 hover:border-foreground"
                          }`}
                        >
                          {t("recommend.viewGrid")}
                        </button>
                        <button
                          onClick={() => setRatingView("swipe")}
                          className={`px-4 py-2 font-mono text-[10px] uppercase tracking-widest border border-l-0 transition-colors ${
                            ratingView === "swipe"
                              ? "bg-foreground text-background border-foreground"
                              : "border-foreground/20 hover:border-foreground"
                          }`}
                        >
                          {t("recommend.viewSwipe")}
                        </button>
                      </div>
                    </div>

                    {/* buscar una peli vista que no esté en la lista curada */}
                    <div className="relative mb-6 max-w-xl">
                      <input
                        value={searchQuery}
                        onChange={(e) => setSearchQuery(e.target.value)}
                        placeholder={t("recommend.searchPlaceholder")}
                        className="w-full bg-transparent border-b-2 border-foreground py-3 font-mono text-sm placeholder:text-muted-foreground focus:outline-none focus:border-accent"
                      />
                    </div>

                    {/* feedback: los resultados de la búsqueda aparecían solo
                        en un dropdown angosto — ahora reemplazan la grilla de
                        posters de abajo mientras hay una búsqueda activa, y
                        se puntúan ahí directo */}
                    {isSearching ? (
                      searchResults.length > 0 ? (
                        <ManualRatingGrid
                          titles={searchResults}
                          ratings={manualRatings}
                          loading={false}
                          onRate={(title, rating) => {
                            const item = searchResults.find((r) => r.title === title);
                            if (item) rateSearchResult(item, rating);
                          }}
                        />
                      ) : (
                        <p className="font-mono text-[10px] uppercase tracking-widest text-muted-foreground py-6">
                          {t("recommend.searchEmpty", { query: searchQuery.trim() })}
                        </p>
                      )
                    ) : loadingTitles ? (
                      <div className="p-12 text-center">
                        <Loader2 className="w-6 h-6 text-accent animate-spin mx-auto" />
                      </div>
                    ) : ratingView === "swipe" ? (
                      <SwipeRating titles={manualTitles} ratings={manualRatings} onRate={rateManual} />
                    ) : (
                      <ManualRatingGrid
                        titles={manualTitles}
                        ratings={manualRatings}
                        loading={false}
                        onRate={rateManual}
                      />
                    )}
                  </div>
                )}
              </section>
            )}

            {step === 2 && (
              <section>
                <h2 className="text-3xl font-black uppercase tracking-tighter mb-3">
                  {t("recommend.step2Title")}
                </h2>
                <p className="font-serif italic text-lg text-muted-foreground mb-8 max-w-2xl">
                  {t("recommend.step2Intro")}
                </p>

                <div className="space-y-3 max-w-2xl">
                  {modeOptions.map((option) => {
                    const disabled =
                      (option.mode === "watchlist" && importMethod !== "zip") ||
                      (option.mode === "recent" && importMethod === "manual");
                    const disabledReason =
                      option.mode === "watchlist"
                        ? t("recommend.modeWatchlistDisabled")
                        : t("recommend.modeRecentDisabled");
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
                          {t(option.labelKey)}
                        </div>
                        <div
                          className={`font-serif italic text-sm ${
                            mode === option.mode ? "text-background/70" : "text-muted-foreground"
                          }`}
                        >
                          {disabled ? disabledReason : t(option.descKey)}
                        </div>
                      </button>
                    );
                  })}
                </div>

                {mode === "genres" && (
                  <div className="mt-6 max-w-2xl">
                    <p className="font-mono text-[10px] uppercase tracking-widest text-muted-foreground mb-3">
                      {t("recommend.picksSelected", {
                        n: selectedGenres.length,
                        max: MAX_SELECTED_OPTIONS,
                      })}
                    </p>
                    {Object.entries(
                      // agrupar preservando el orden en que llegan del backend,
                      // no un orden fijo a mano acá
                      pickOptions.reduce<Record<string, PickOption[]>>((groups, option) => {
                        (groups[option.group] ??= []).push(option);
                        return groups;
                      }, {}),
                    ).map(([group, options]) => (
                      <div key={group} className="mb-5">
                        <h3 className="font-mono text-[10px] uppercase tracking-widest text-muted-foreground mb-2">
                          {PICK_GROUP_LABEL_KEYS[group] ? t(PICK_GROUP_LABEL_KEYS[group]) : group}
                        </h3>
                        <div className="flex flex-wrap gap-2">
                          {options.map((option) => {
                            const selected = selectedGenres.includes(option.key);
                            const atCap = !selected && selectedGenres.length >= MAX_SELECTED_OPTIONS;
                            return (
                              <button
                                key={option.key}
                                onClick={() => toggleGenre(option.key)}
                                disabled={atCap}
                                className={`px-3 py-1.5 font-mono text-[10px] uppercase tracking-widest border transition-colors disabled:opacity-30 disabled:cursor-not-allowed ${
                                  selected
                                    ? "bg-accent text-accent-foreground border-accent"
                                    : "border-foreground/20 hover:border-foreground"
                                }`}
                              >
                                {option.label}
                              </button>
                            );
                          })}
                        </div>
                      </div>
                    ))}
                  </div>
                )}
                {mode === "genres" && selectedGenres.length === 0 && (
                  <p className="font-mono text-[10px] text-destructive mt-3">
                    {t("recommend.pickAtLeastOne")}
                  </p>
                )}
              </section>
            )}

            {step === 3 && (
              <section>
                <h2 className="text-3xl font-black uppercase tracking-tighter mb-3">
                  {t("recommend.step3Title")}
                </h2>
                <p className="font-serif italic text-lg text-muted-foreground mb-8 max-w-2xl">
                  {t("recommend.step3Intro")}
                </p>

                <div className="flex gap-0 max-w-xl mb-8">
                  {kindFilterOptions.map((option) => (
                    <button key={option.value} onClick={() => setKindFilter(option.value)} className={tabCls(kindFilter === option.value)}>
                      {t(option.labelKey)}
                    </button>
                  ))}
                </div>

                <p className="font-mono text-[10px] uppercase tracking-widest text-muted-foreground mb-8">
                  {t("recommend.recapSource")}{" "}
                  {importMethod === "zip"
                    ? `.zip (${zipFile?.name ?? ""})`
                    : importMethod === "username"
                      ? `@${letterboxdUsername.trim()}`
                      : t("recommend.recapManualCount", { n: manualCount })}{" "}
                  · {t("recommend.recapMode")}{" "}
                  {t(modeOptions.find((o) => o.mode === mode)?.labelKey ?? "")}
                  {mode === "genres" &&
                    ` (${selectedGenres
                      .map((k) => pickOptions.find((g) => g.key === k)?.label)
                      .filter(Boolean)
                      .join(", ")})`}
                </p>

                {/* feedback punto 3: explicar cómo se calculan los picks, en el
                    lugar donde el usuario está por pedirlos */}
                <details className="max-w-2xl mb-4 border border-foreground/20">
                  <summary className="cursor-pointer px-4 py-3 font-mono text-[10px] uppercase tracking-widest text-muted-foreground hover:text-accent transition-colors">
                    {t("recommend.howSummary")}
                  </summary>
                  <div className="px-4 pb-4 font-serif text-sm leading-relaxed space-y-2">
                    <p>{t("recommend.howP1")}</p>
                    <p>{t("recommend.howP2")}</p>
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
                    {t("recommend.continue")}
                  </button>
                ) : (
                  <button
                    onClick={handleGenerate}
                    disabled={loading || !canGenerate}
                    className="px-8 py-4 bg-accent text-accent-foreground font-mono text-xs uppercase tracking-widest hover:bg-foreground hover:text-background transition-colors disabled:opacity-60"
                  >
                    {t("recommend.generate")}
                  </button>
                )}
              </div>
            </div>
          </div>
        )}

        {loading && (
          <div className="py-20 text-center">
            <Loader2 className="w-7 h-7 text-accent animate-spin mx-auto mb-6" />
            <h3 className="text-2xl font-black uppercase tracking-tighter mb-3">
              {t("recommend.loadingTitle")}
            </h3>
            <p className="font-mono text-xs uppercase text-muted-foreground max-w-sm mx-auto">
              {t("recommend.loadingBody")}
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
                  {t("recommend.resultsBadge", { n: result.recommendations.length })}
                </span>
                <div className="h-px flex-grow bg-foreground/10 min-w-8" />
                <div className="flex gap-4 shrink-0">
                  <button
                    onClick={handleGenerate}
                    className="font-mono text-[10px] uppercase tracking-widest hover:text-accent transition-colors"
                  >
                    {t("recommend.newPicks")}
                  </button>
                  <button
                    onClick={() => {
                      setResult(null);
                      setFeedbackState({});
                    }}
                    className="font-mono text-[10px] uppercase tracking-widest hover:text-accent transition-colors"
                  >
                    {t("recommend.changeSearch")}
                  </button>
                </div>
              </div>
              <p className="font-mono text-[10px] uppercase tracking-widest text-muted-foreground mt-3">
                {result.taste_summary}
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
            seenWhys={seenWhysRef}
            onClose={() => setSelectedRec(null)}
            onFeedback={(status) => submitFeedback(selectedRec.id, status)}
            onRate={(rating, title, tmdbId) => rateTitle(selectedRec, rating, title, tmdbId)}
            readOnly={result?.ephemeral}
          />
        )}
      </main>
    </PageTransition>
  );
}
