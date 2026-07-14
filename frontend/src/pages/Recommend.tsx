import { AnimatePresence, motion } from "framer-motion";
import {
  AlertCircle,
  CheckCircle,
  Clock,
  Eye,
  ExternalLink,
  FileText,
  Film,
  Loader2,
  RefreshCw,
  Sparkles,
  Star,
  Tags,
  ThumbsDown,
  ThumbsUp,
  Upload as UploadIcon,
  User,
  X,
} from "lucide-react";
import React, { useCallback, useEffect, useRef, useState } from "react";
import { toast } from "sonner";
import { useLocation } from "wouter";

import { Navbar } from "@/components/Navbar";
import { PageTransition } from "@/components/PageTransition";
import PixelCard from "@/components/PixelCard";
import { API_BASE_URL, useAuth } from "@/hooks/useAuth";

type Recommendation = {
  id: number;
  tmdb_id: number | null;
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

type MovieDetails = {
  cast: { name: string; character: string; profile_path: string | null }[];
  trailer_key: string | null;
};

type RecommendResponse = {
  taste_summary: string;
  recommendations: Recommendation[];
};

type FeedbackStatus = "interested" | "not_interested" | "seen";

const feedbackOptions: { status: FeedbackStatus; label: string; icon: typeof ThumbsUp }[] = [
  { status: "interested", label: "Me interesa", icon: ThumbsUp },
  { status: "not_interested", label: "No me interesa", icon: ThumbsDown },
  { status: "seen", label: "Ya la vi", icon: Eye },
];

type RecommendMode = "profile" | "recent" | "genres";
type KindFilter = "movie" | "series" | "both";

const modeOptions: { mode: RecommendMode; label: string; description: string; icon: typeof User }[] = [
  {
    mode: "profile",
    label: "Según mi perfil",
    description: "Analiza todo tu historial de ratings y reviews.",
    icon: User,
  },
  {
    mode: "recent",
    label: "Según lo último que vi",
    description: "Se basa solo en las películas que viste más recientemente.",
    icon: Clock,
  },
  {
    mode: "genres",
    label: "Por géneros",
    description: "Elegís uno o más géneros y buscamos algo de esa mezcla.",
    icon: Tags,
  },
];

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

function formatFileSize(bytes: number): string {
  return bytes < 1024 * 1024 ? `${Math.round(bytes / 1024)} KB` : `${(bytes / (1024 * 1024)).toFixed(1)} MB`;
}

// ─── Movie Detail Modal ─────────────────────────────────────────────────────

function MovieModal({
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

  return (
    <motion.div
      initial={{ opacity: 0 }}
      animate={{ opacity: 1 }}
      exit={{ opacity: 0 }}
      transition={{ duration: 0.2 }}
      className="fixed inset-0 z-50 flex items-end sm:items-center justify-center p-4"
      onClick={onClose}
    >
      <div className="absolute inset-0 bg-black/80 backdrop-blur-md" />

      <motion.div
        initial={{ opacity: 0, y: 40, scale: 0.96 }}
        animate={{ opacity: 1, y: 0, scale: 1 }}
        exit={{ opacity: 0, y: 20, scale: 0.98 }}
        transition={{ duration: 0.3, ease: [0.23, 1, 0.32, 1] }}
        onClick={(e) => e.stopPropagation()}
        className="relative w-full max-w-2xl max-h-[90vh] overflow-y-auto rounded-2xl border border-border bg-card shadow-2xl"
      >
        {rec.backdrop_path && (
          <div className="relative h-48 overflow-hidden rounded-t-2xl">
            <img src={rec.backdrop_path} alt={rec.title} className="w-full h-full object-cover" />
            <div className="absolute inset-0 bg-gradient-to-t from-card via-card/60 to-transparent" />
          </div>
        )}

        <div className="p-6">
          <button
            onClick={onClose}
            aria-label="Cerrar detalle"
            className="absolute top-4 right-4 p-2 rounded-xl bg-background/80 backdrop-blur-sm border border-border hover:bg-secondary transition-colors"
          >
            <X className="w-4 h-4" />
          </button>

          <div className="flex gap-5">
            {rec.poster_path && (
              <img
                src={rec.poster_path}
                alt={rec.title}
                className="w-24 h-36 rounded-xl object-cover shrink-0 shadow-xl border border-border"
              />
            )}

            <div className="flex-1 min-w-0">
              <h2 className="text-2xl font-serif mb-1 leading-tight" style={{ fontFamily: "'Instrument Serif', serif" }}>
                {rec.title}
              </h2>
              <div className="flex flex-wrap items-center gap-3 mb-3 text-sm text-muted-foreground">
                {rec.kind === "series" && (
                  <span className="px-2 py-0.5 rounded-full bg-secondary text-xs">Serie</span>
                )}
                <span>{rec.year}</span>
                {rec.vote_average != null && (
                  <span className="flex items-center gap-1">
                    <Star className="w-3 h-3 fill-primary text-primary" />
                    {rec.vote_average.toFixed(1)}
                  </span>
                )}
                <span className="px-2 py-0.5 rounded-full bg-secondary text-xs">{rec.match_score}% match</span>
              </div>
            </div>
          </div>

          <div className="mt-5 p-4 rounded-xl border border-primary/20 bg-primary/5">
            <p className="text-xs text-primary uppercase tracking-wider mb-2 font-medium flex items-center gap-1.5">
              <Sparkles className="w-3 h-3" />
              Por qué esta peli para vos
            </p>
            <p className="text-sm leading-relaxed text-foreground/80">{rec.why}</p>
          </div>

          {rec.tags.length > 0 && (
            <div className="flex flex-wrap gap-2 mt-4">
              {rec.tags.map((tag) => (
                <span key={tag} className="px-2.5 py-1 rounded-full text-xs border border-primary/20 text-primary/80 bg-primary/5">
                  {tag}
                </span>
              ))}
            </div>
          )}

          {rec.overview && <p className="mt-4 text-sm text-muted-foreground leading-relaxed">{rec.overview}</p>}

          {loadingDetails && (
            <div className="mt-5 pt-5 border-t border-border flex items-center gap-2 text-sm text-muted-foreground">
              <Loader2 className="w-4 h-4 animate-spin text-primary" />
              Cargando reparto y tr&aacute;iler...
            </div>
          )}

          {details && (details.cast.length > 0 || details.trailer_key) && (
            <section className="mt-5 pt-5 border-t border-border">
              {details.trailer_key && (
                <a
                  href={`https://www.youtube.com/watch?v=${details.trailer_key}`}
                  target="_blank"
                  rel="noreferrer"
                  className="mb-5 inline-flex items-center gap-2 px-4 py-2 rounded-xl border border-primary/30 bg-primary/10 text-sm text-primary hover:bg-primary/20 transition-colors"
                >
                  <Film className="w-4 h-4" />
                  Ver tr&aacute;iler
                  <ExternalLink className="w-3.5 h-3.5" />
                </a>
              )}

              {details.cast.length > 0 && (
                <>
                  <h3 className="text-xl font-serif mb-3" style={{ fontFamily: "'Instrument Serif', serif" }}>
                    Reparto
                  </h3>
                  <div className="grid grid-cols-2 sm:grid-cols-3 gap-2.5">
                    {details.cast.map((member) => (
                      <div key={`${member.name}-${member.character}`} className="flex items-center gap-2.5 rounded-xl bg-background/60 p-2.5 min-w-0">
                        {member.profile_path ? (
                          <img src={member.profile_path} alt={member.name} className="w-10 h-10 rounded-full object-cover shrink-0" />
                        ) : (
                          <span className="w-10 h-10 rounded-full bg-secondary flex items-center justify-center shrink-0 text-sm text-primary" aria-label={`Sin foto de ${member.name}`}>
                            {member.name.charAt(0)}
                          </span>
                        )}
                        <div className="min-w-0">
                          <p className="text-sm leading-tight truncate">{member.name}</p>
                          {member.character && <p className="text-xs text-muted-foreground truncate mt-0.5">{member.character}</p>}
                        </div>
                      </div>
                    ))}
                  </div>
                </>
              )}
            </section>
          )}

          <div className="mt-6 pt-5 border-t border-border">
            <p className="text-xs text-muted-foreground mb-3">¿Qué te parece este pick?</p>
            <div className="flex gap-3">
              {feedbackOptions.map((option) => (
                <button
                  key={option.status}
                  onClick={() => onFeedback(option.status)}
                  className={`flex items-center gap-2 px-4 py-2 rounded-xl text-sm border transition-all duration-200 active:scale-95 ${
                    feedback === option.status
                      ? "bg-primary text-primary-foreground border-primary"
                      : "border-border hover:border-primary/50 hover:bg-primary/5"
                  }`}
                >
                  <option.icon className="w-4 h-4" />
                  {option.label}
                </button>
              ))}
            </div>
          </div>
        </div>
      </motion.div>
    </motion.div>
  );
}

// ─── Recommendation Card ────────────────────────────────────────────────────

function RecommendationCard({
  rec,
  index,
  feedback,
  onSelect,
  onFeedback,
}: {
  rec: Recommendation;
  index: number;
  feedback?: FeedbackStatus;
  onSelect: () => void;
  onFeedback: (status: FeedbackStatus) => void;
}) {
  const poster = rec.poster_path ?? rec.backdrop_path;

  return (
    <motion.div
      initial={{ opacity: 0, y: 40 }}
      animate={{ opacity: 1, y: 0 }}
      transition={{ delay: index * 0.1, duration: 0.5, ease: [0.23, 1, 0.32, 1] }}
      className="flex flex-col gap-3"
    >
      <PixelCard variant="amber" className="pelipick-poster" onClick={onSelect}>
        {poster ? (
          <img
            src={poster}
            alt={rec.title}
            className="absolute inset-0 w-full h-full object-cover"
            style={{ zIndex: 0 }}
          />
        ) : (
          <div className="absolute inset-0 flex items-center justify-center bg-gradient-to-br from-secondary to-background" style={{ zIndex: 0 }}>
            <Film className="w-12 h-12 text-muted-foreground/30" />
          </div>
        )}

        <div
          className="absolute inset-0 bg-gradient-to-t from-black/90 via-black/30 to-black/20"
          style={{ zIndex: 2 }}
        />

        <div className="absolute inset-x-0 top-0 flex items-center justify-between p-3" style={{ zIndex: 3 }}>
          <div className="flex items-center gap-2">
            <span className="w-8 h-8 rounded-full bg-black/60 backdrop-blur-sm border border-white/15 flex items-center justify-center text-xs font-medium text-primary">
              {index + 1}
            </span>
            {rec.kind === "series" && (
              <span className="px-2 py-0.5 rounded-full bg-black/60 backdrop-blur-sm border border-white/15 text-[10px] font-medium text-white/80">
                Serie
              </span>
            )}
          </div>
          {feedback && (
            <span
              className={`w-7 h-7 rounded-full flex items-center justify-center ${
                feedback === "interested"
                  ? "bg-primary"
                  : feedback === "seen"
                    ? "bg-black/60 border border-white/15"
                    : "bg-destructive/30 border border-destructive/40"
              }`}
            >
              {feedback === "interested" && <ThumbsUp className="w-3.5 h-3.5 text-primary-foreground" />}
              {feedback === "seen" && <Eye className="w-3.5 h-3.5 text-white/80" />}
              {feedback === "not_interested" && <ThumbsDown className="w-3.5 h-3.5 text-destructive" />}
            </span>
          )}
        </div>

        <div className="absolute inset-x-0 bottom-0 p-4" style={{ zIndex: 3 }}>
          <h3
            className="text-lg font-serif leading-tight mb-1 text-white"
            style={{ fontFamily: "'Instrument Serif', serif" }}
          >
            {rec.title}
          </h3>
          <div className="flex items-center gap-2 text-xs text-white/70 mb-2">
            <span>{rec.year}</span>
            {rec.vote_average != null && (
              <span className="flex items-center gap-0.5">
                <Star className="w-2.5 h-2.5 fill-primary text-primary" />
                {rec.vote_average.toFixed(1)}
              </span>
            )}
            <span className="text-primary">{rec.match_score}% match</span>
          </div>
          <div className="flex flex-wrap gap-1.5">
            {rec.tags.slice(0, 3).map((tag) => (
              <span
                key={tag}
                className="px-2 py-0.5 rounded-full text-[10px] border border-white/20 text-white/80 bg-black/30 backdrop-blur-sm"
              >
                {tag}
              </span>
            ))}
          </div>
        </div>
      </PixelCard>

      <div className="flex gap-2">
        <button
          onClick={() => onFeedback("interested")}
          className={`flex-1 flex items-center justify-center gap-1.5 py-2 rounded-lg text-xs border transition-all duration-200 active:scale-95 ${
            feedback === "interested"
              ? "bg-primary text-primary-foreground border-primary"
              : "border-border hover:border-primary/50 hover:bg-primary/5 text-muted-foreground"
          }`}
        >
          <ThumbsUp className="w-3.5 h-3.5" />
          Me interesa
        </button>
        <button
          onClick={() => onFeedback("seen")}
          className={`flex items-center justify-center gap-1.5 px-3 py-2 rounded-lg text-xs border transition-all duration-200 active:scale-95 ${
            feedback === "seen"
              ? "bg-secondary text-foreground border-border"
              : "border-border hover:border-border/80 hover:bg-secondary text-muted-foreground"
          }`}
          aria-label="Ya la vi"
        >
          <Eye className="w-3.5 h-3.5" />
        </button>
        <button
          onClick={() => onFeedback("not_interested")}
          className={`flex items-center justify-center gap-1.5 px-3 py-2 rounded-lg text-xs border transition-all duration-200 active:scale-95 ${
            feedback === "not_interested"
              ? "bg-destructive/20 text-destructive border-destructive/30"
              : "border-border hover:border-destructive/30 hover:bg-destructive/5 text-muted-foreground"
          }`}
          aria-label="No me interesa"
        >
          <ThumbsDown className="w-3.5 h-3.5" />
        </button>
      </div>
    </motion.div>
  );
}

// ─── Main Page ───────────────────────────────────────────────────────────────

export default function Recommend() {
  const { isAuthenticated, loading: authLoading, token } = useAuth();
  const [, navigate] = useLocation();

  const [mode, setMode] = useState<RecommendMode>("profile");
  const [kindFilter, setKindFilter] = useState<KindFilter>("both");
  const [selectedGenres, setSelectedGenres] = useState<string[]>([]);
  const [zipFile, setZipFile] = useState<File | null>(null);
  const [isDragging, setIsDragging] = useState(false);
  const fileInputRef = useRef<HTMLInputElement>(null);

  const [result, setResult] = useState<RecommendResponse | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");
  const [feedbackState, setFeedbackState] = useState<Record<number, FeedbackStatus>>({});
  const [selectedRec, setSelectedRec] = useState<Recommendation | null>(null);

  useEffect(() => {
    if (!authLoading && !isAuthenticated) {
      navigate("/login");
    }
  }, [authLoading, isAuthenticated, navigate]);

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

  const canGenerate = Boolean(zipFile) && (mode !== "genres" || selectedGenres.length > 0);

  async function handleGenerate() {
    if (!token || !zipFile || !canGenerate) return;
    setLoading(true);
    setError("");

    try {
      const formData = new FormData();
      formData.append("mode", mode);
      formData.append("kind_filter", kindFilter);
      formData.append("genres", mode === "genres" ? selectedGenres.join(",") : "");
      formData.append("file", zipFile);

      const response = await fetch(`${API_BASE_URL}/recommend/zip`, {
        method: "POST",
        headers: {
          Authorization: `Bearer ${token}`,
        },
        body: formData,
      });

      if (!response.ok) {
        const body = await response.json().catch(() => null);
        throw new Error(body?.detail ?? "No pude hablar con el backend.");
      }

      const data = (await response.json()) as RecommendResponse;
      if (!data.recommendations.length) {
        throw new Error("No pude leer ratings válidos de ese zip.");
      }

      setResult(data);
      setFeedbackState({});
      toast.success("Tus picks están listos.");
    } catch (err) {
      const message = err instanceof Error ? err.message : "Falló la recomendación.";
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
        headers: {
          "Content-Type": "application/json",
          Authorization: `Bearer ${token}`,
        },
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
          <motion.div initial={{ opacity: 0, y: 20 }} animate={{ opacity: 1, y: 0 }} transition={{ duration: 0.5 }} className="mb-10">
            <p className="text-primary text-sm uppercase tracking-widest mb-3 font-medium">Personalizado para vos</p>
            <h1 className="text-4xl md:text-5xl font-serif mb-4" style={{ fontFamily: "'Instrument Serif', serif" }}>
              Tus <em className="text-gradient not-italic">picks de peli</em>
            </h1>
            <p className="text-muted-foreground leading-relaxed max-w-2xl">
              Cada recomendación está basada en tu historial real — tus ratings, tus reviews, tus
              patrones. No un algoritmo genérico.
            </p>
          </motion.div>

          {!result && !loading && (
            <motion.div initial={{ opacity: 0, y: 20 }} animate={{ opacity: 1, y: 0 }} transition={{ delay: 0.1 }} className="max-w-2xl">
              <div className="p-5 rounded-xl border border-border bg-card/30 mb-6">
                <div className="flex items-start gap-3">
                  <div className="w-8 h-8 rounded-lg bg-primary/10 flex items-center justify-center shrink-0 mt-0.5">
                    <ExternalLink className="w-4 h-4 text-primary" />
                  </div>
                  <div>
                    <h3 className="text-sm font-medium mb-2">Cómo exportar de Letterboxd</h3>
                    <ol className="text-sm text-muted-foreground space-y-1 list-decimal list-inside">
                      <li>Letterboxd → Settings → pestaña Data</li>
                      <li>"Export your data" — descarga un .zip</li>
                      <li>Subí ese .zip tal cual, sin descomprimir, acá abajo</li>
                    </ol>
                  </div>
                </div>
              </div>

              <div
                onDrop={handleDrop}
                onDragOver={(e) => {
                  e.preventDefault();
                  setIsDragging(true);
                }}
                onDragLeave={() => setIsDragging(false)}
                onClick={() => fileInputRef.current?.click()}
                className={`relative border-2 border-dashed rounded-2xl p-10 text-center cursor-pointer transition-all duration-300 mb-6 ${
                  isDragging ? "border-primary bg-primary/5 scale-[1.01]" : "border-border hover:border-primary/50 hover:bg-card/30"
                }`}
              >
                <input ref={fileInputRef} type="file" accept=".zip,application/zip" onChange={handleFileInput} className="hidden" />
                <div className="w-14 h-14 rounded-2xl bg-primary/10 border border-primary/20 flex items-center justify-center mx-auto mb-4">
                  <UploadIcon className="w-6 h-6 text-primary" />
                </div>
                <h3 className="text-lg font-serif mb-1" style={{ fontFamily: "'Instrument Serif', serif" }}>
                  {isDragging ? "Soltalo acá" : "Arrastrá tu .zip acá"}
                </h3>
                <p className="text-muted-foreground text-sm mb-3">o hacé click para buscarlo</p>
                {zipFile ? (
                  <div className="inline-flex items-center gap-2 text-xs text-primary bg-primary/10 px-3 py-1.5 rounded-full">
                    <CheckCircle className="w-3 h-3" />
                    {zipFile.name} · {formatFileSize(zipFile.size)}
                  </div>
                ) : (
                  <div className="inline-flex items-center gap-2 text-xs text-muted-foreground/60 bg-secondary/50 px-3 py-1.5 rounded-full">
                    <FileText className="w-3 h-3" />
                    Solo .zip
                  </div>
                )}
              </div>

              <div className="p-6 rounded-2xl border border-border bg-card/50">
                <span className="text-sm font-medium mb-3 block">Qué querés ver hoy</span>
                <div className="grid sm:grid-cols-3 gap-3 mb-2">
                  {modeOptions.map((option) => (
                    <button
                      key={option.mode}
                      type="button"
                      onClick={() => setMode(option.mode)}
                      className={`text-left p-3.5 rounded-xl border transition-all duration-200 ${
                        mode === option.mode
                          ? "border-primary bg-primary/10"
                          : "border-border hover:border-primary/40 hover:bg-card/60"
                      }`}
                    >
                      <div className="flex items-center gap-2 mb-1">
                        <option.icon className={`w-4 h-4 ${mode === option.mode ? "text-primary" : "text-muted-foreground"}`} />
                        <span className="text-sm font-medium">{option.label}</span>
                      </div>
                      <p className="text-xs text-muted-foreground leading-snug">{option.description}</p>
                    </button>
                  ))}
                </div>

                {mode === "genres" && (
                  <div className="mb-5 mt-3 flex flex-wrap gap-2">
                    {genreOptions.map((genre) => (
                      <button
                        key={genre.key}
                        type="button"
                        onClick={() => toggleGenre(genre.key)}
                        className={`px-3 py-1.5 rounded-full text-xs border transition-all duration-200 ${
                          selectedGenres.includes(genre.key)
                            ? "bg-primary text-primary-foreground border-primary"
                            : "border-border hover:border-primary/50 hover:bg-primary/5 text-muted-foreground"
                        }`}
                      >
                        {genre.label}
                      </button>
                    ))}
                  </div>
                )}
                {mode === "genres" && selectedGenres.length === 0 && (
                  <p className="text-xs text-destructive/80 mb-5 -mt-2">Elegí al menos un género.</p>
                )}
                {mode !== "genres" && <div className="mb-5" />}

                <label className="block mb-5">
                  <span className="text-sm font-medium mb-2 block">Qué querés que te recomiende</span>
                  <div className="grid grid-cols-3 gap-2">
                    {kindFilterOptions.map((option) => (
                      <button
                        key={option.value}
                        type="button"
                        onClick={() => setKindFilter(option.value)}
                        className={`py-2.5 rounded-xl text-sm border transition-all duration-200 ${
                          kindFilter === option.value
                            ? "bg-primary text-primary-foreground border-primary"
                            : "border-border hover:border-primary/50 hover:bg-primary/5 text-muted-foreground"
                        }`}
                      >
                        {option.label}
                      </button>
                    ))}
                  </div>
                </label>

                <button
                  onClick={handleGenerate}
                  disabled={loading || !canGenerate}
                  className="w-full flex items-center justify-center gap-2 bg-primary text-primary-foreground py-3.5 rounded-xl font-medium hover:bg-primary/90 transition-all duration-200 active:scale-95 disabled:opacity-60 amber-glow"
                >
                  <Sparkles className="w-4 h-4" />
                  Dame mis recomendaciones
                </button>
              </div>
            </motion.div>
          )}

          {loading && (
            <motion.div initial={{ opacity: 0 }} animate={{ opacity: 1 }} className="py-20 text-center">
              <div className="w-16 h-16 rounded-2xl bg-primary/10 border border-primary/20 flex items-center justify-center mx-auto mb-6">
                <Loader2 className="w-7 h-7 text-primary animate-spin" />
              </div>
              <h3 className="text-2xl font-serif mb-3" style={{ fontFamily: "'Instrument Serif', serif" }}>
                Buscando tus pelis...
              </h3>
              <p className="text-muted-foreground text-sm max-w-sm mx-auto">
                Leyendo tu historial y buscando candidatos que encajen con tu gusto.
              </p>
              <div className="grid sm:grid-cols-2 lg:grid-cols-3 gap-6 mt-12 text-left">
                {[...Array(6)].map((_, i) => (
                  <div key={i} className="rounded-2xl border border-border bg-card overflow-hidden">
                    <div className="skeleton h-44 w-full" />
                    <div className="p-5 space-y-3">
                      <div className="skeleton h-5 w-3/4 rounded-lg" />
                      <div className="skeleton h-4 w-1/2 rounded-lg" />
                      <div className="skeleton h-16 w-full rounded-xl" />
                      <div className="skeleton h-9 w-full rounded-lg" />
                    </div>
                  </div>
                ))}
              </div>
            </motion.div>
          )}

          {error && !loading ? (
            <div className="mt-4 p-4 rounded-xl border border-destructive/30 bg-destructive/5 flex items-start gap-3">
              <AlertCircle className="w-5 h-5 text-destructive shrink-0 mt-0.5" />
              <p className="text-sm text-destructive">{error}</p>
            </div>
          ) : null}

          {result && !loading && (
            <>
              <div className="flex items-center justify-between mb-8 gap-4">
                <div>
                  <p className="text-sm text-muted-foreground mb-1">{result.recommendations.length} películas para vos</p>
                  <p className="text-xs text-muted-foreground/70 max-w-xl">{result.taste_summary}</p>
                </div>
                <button
                  onClick={() => {
                    setResult(null);
                    setFeedbackState({});
                  }}
                  className="flex items-center gap-2 text-sm text-muted-foreground hover:text-foreground transition-colors duration-200 px-4 py-2 rounded-xl border border-border hover:border-border/80 hover:bg-secondary shrink-0"
                >
                  <RefreshCw className="w-3.5 h-3.5" />
                  Nuevos picks
                </button>
              </div>

              <div className="grid sm:grid-cols-2 lg:grid-cols-3 gap-6">
                {result.recommendations.map((rec, i) => (
                  <RecommendationCard
                    key={rec.id}
                    rec={rec}
                    index={i}
                    feedback={feedbackState[rec.id]}
                    onSelect={() => setSelectedRec(rec)}
                    onFeedback={(status) => submitFeedback(rec.id, status)}
                  />
                ))}
              </div>
            </>
          )}
        </div>
      </div>

      <AnimatePresence>
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
      </AnimatePresence>
    </PageTransition>
  );
}
