import {
  AlertCircle,
  CheckCircle,
  Eye,
  ExternalLink,
  Film,
  Loader2,
  ThumbsDown,
  ThumbsUp,
} from "lucide-react";
import React, { useCallback, useEffect, useRef, useState } from "react";
import { createPortal } from "react-dom";
import { toast } from "sonner";
import { useLocation } from "wouter";

import { PageTransition } from "@/components/PageTransition";
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
  discarded_rows: number;
};

type FeedbackStatus = "interested" | "not_interested" | "seen";

type RecommendMode = "profile" | "recent" | "genres";
type KindFilter = "movie" | "series" | "both";

const modeOptions: { mode: RecommendMode; label: string }[] = [
  { mode: "profile", label: "Perfil completo" },
  { mode: "recent", label: "Últimas vistas" },
  { mode: "genres", label: "Selección de géneros" },
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

const tabCls = (active: boolean) =>
  `flex-1 py-3 font-mono text-[10px] uppercase tracking-widest border transition-colors ${
    active ? "bg-foreground text-background border-foreground" : "border-foreground/20 hover:border-foreground"
  }`;

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

  const btn = "flex-1 py-3 font-mono text-[10px] uppercase tracking-widest border transition-colors";

  return createPortal(
    <div
      className="fixed inset-0 z-[100] bg-foreground/60 backdrop-blur-sm flex items-start justify-center p-6 overflow-y-auto"
      onClick={onClose}
    >
      <div
        className="bg-background max-w-4xl w-full mt-12 mb-12 border-2 border-foreground"
        onClick={(e) => e.stopPropagation()}
      >
        <div className="flex justify-between items-baseline border-b-2 border-foreground px-6 py-4">
          <span className="font-mono text-[10px] uppercase tracking-widest">
            [Detail] · {rec.id}
          </span>
          <button onClick={onClose} className="font-mono text-xs hover:text-accent">
            [close ×]
          </button>
        </div>
        <div className="grid grid-cols-1 md:grid-cols-5 gap-8 p-6">
          <div className="md:col-span-2">
            {rec.poster_path ? (
              <img
                src={rec.poster_path}
                alt={rec.title}
                className="w-full aspect-[2/3] object-cover outline outline-1 -outline-offset-1 outline-black/10"
              />
            ) : (
              <div className="w-full aspect-[2/3] bg-secondary flex items-center justify-center">
                <Film className="w-10 h-10 text-muted-foreground/40" />
              </div>
            )}
          </div>
          <div className="md:col-span-3 flex flex-col">
            <h2 className="text-4xl md:text-5xl font-black uppercase tracking-tighter leading-[0.9] mb-4">
              {rec.title}
            </h2>
            <div className="font-mono text-xs text-muted-foreground uppercase tracking-widest mb-6">
              {rec.year}
              {rec.kind === "series" ? " · Serie" : ""}
              {rec.vote_average != null ? ` · ★ ${rec.vote_average.toFixed(1)}` : ""}
              {" · "}
              {rec.match_score}% match
            </div>
            <p className="font-serif text-2xl italic leading-snug text-balance mb-6">
              &ldquo;{rec.why}&rdquo;
            </p>

            {rec.tags.length > 0 && (
              <div className="flex flex-wrap gap-2 mb-6">
                {rec.tags.map((tag) => (
                  <span key={tag} className="font-mono text-[10px] uppercase px-2 py-1 border border-foreground/20">
                    {tag}
                  </span>
                ))}
              </div>
            )}

            {rec.overview && (
              <p className="text-sm text-muted-foreground leading-relaxed mb-6">{rec.overview}</p>
            )}

            {loadingDetails && (
              <div className="border-t border-foreground/10 pt-4 mb-6 flex items-center gap-2 font-mono text-[10px] uppercase tracking-widest text-muted-foreground">
                <Loader2 className="w-3.5 h-3.5 animate-spin" />
                Cargando reparto y tráiler...
              </div>
            )}

            {details && (details.cast.length > 0 || details.trailer_key) && (
              <div className="border-t border-foreground/10 pt-4 mb-6">
                {details.trailer_key && (
                  <a
                    href={`https://www.youtube.com/watch?v=${details.trailer_key}`}
                    target="_blank"
                    rel="noreferrer"
                    className="mb-4 inline-flex items-center gap-2 px-4 py-2 border border-foreground/30 font-mono text-[10px] uppercase tracking-widest hover:border-accent hover:text-accent transition-colors"
                  >
                    <Film className="w-3.5 h-3.5" />
                    Ver tráiler
                    <ExternalLink className="w-3 h-3" />
                  </a>
                )}
                {details.cast.length > 0 && (
                  <>
                    <div className="font-mono text-[10px] uppercase tracking-widest text-muted-foreground mb-2">
                      Cast
                    </div>
                    <div className="text-sm">
                      {details.cast.map((c) => c.name).join(" · ")}
                    </div>
                  </>
                )}
              </div>
            )}

            <div className="mt-auto pt-4 border-t border-foreground/10">
              <p className="font-mono text-[10px] uppercase tracking-widest text-muted-foreground mb-3">
                ¿Qué te parece este pick?
              </p>
              <div className="flex gap-2">
                <button
                  onClick={() => onFeedback("interested")}
                  className={`${btn} ${feedback === "interested" ? "bg-foreground text-background border-foreground" : "border-foreground/30 hover:border-foreground"}`}
                >
                  Me interesa
                </button>
                <button
                  onClick={() => onFeedback("seen")}
                  className={`${btn} ${feedback === "seen" ? "bg-secondary border-foreground" : "border-foreground/30 hover:border-foreground"}`}
                >
                  Ya la vi
                </button>
                <button
                  onClick={() => onFeedback("not_interested")}
                  className={`${btn} ${feedback === "not_interested" ? "bg-accent text-accent-foreground border-accent" : "border-foreground/30 hover:border-foreground"}`}
                >
                  No me interesa
                </button>
              </div>
            </div>
          </div>
        </div>
      </div>
    </div>,
    document.body,
  );
}

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

  return (
    <button
      type="button"
      onClick={onSelect}
      className="animate-reveal text-left group block w-full"
      style={{ animationDelay: `${100 + index * 100}ms` }}
    >
      <div className="mb-6 relative overflow-hidden">
        {poster ? (
          <img
            src={poster}
            alt={rec.title}
            loading="lazy"
            className="w-full aspect-[2/3] object-cover bg-secondary outline outline-1 -outline-offset-1 outline-black/10 transition-transform duration-500 group-hover:scale-[1.02]"
          />
        ) : (
          <div className="w-full aspect-[2/3] bg-secondary flex items-center justify-center">
            <Film className="w-10 h-10 text-muted-foreground/40" />
          </div>
        )}
        <div className="absolute -top-3 -right-3 size-16 bg-accent flex items-center justify-center text-accent-foreground font-mono text-lg font-bold shadow-lg">
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
        <h3 className="text-2xl font-black uppercase tracking-tighter leading-none">{rec.title}</h3>
        <span className="font-mono text-xs text-muted-foreground shrink-0">{rec.year}</span>
      </div>
      <p className="font-serif text-xl leading-snug mb-4 italic text-balance">
        &ldquo;{rec.why}&rdquo;
      </p>
      <div className="font-mono text-[10px] uppercase tracking-widest text-muted-foreground border-t border-foreground/10 pt-4">
        {rec.tags.slice(0, 3).join(" / ") || "Sin tags"}
      </div>
    </button>
  );
}

// ─── Main Page ───────────────────────────────────────────────────────────────

export default function Recommend() {
  const { isAuthenticated, loading: authLoading, token } = useAuth();
  const [, navigate] = useLocation();

  const [mode, setMode] = useState<RecommendMode>("profile");
  const [kindFilter, setKindFilter] = useState<KindFilter>("both");
  const [selectedGenres, setSelectedGenres] = useState<string[]>([]);
  const [importMethod, setImportMethod] = useState<"zip" | "username">("zip");
  const [zipFile, setZipFile] = useState<File | null>(null);
  const [letterboxdUsername, setLetterboxdUsername] = useState("");
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

  const hasSource = importMethod === "zip" ? Boolean(zipFile) : letterboxdUsername.trim().length > 0;
  const canGenerate = hasSource && (mode !== "genres" || selectedGenres.length > 0);

  async function handleGenerate() {
    if (!token || !canGenerate) return;
    setLoading(true);
    setError("");

    try {
      const formData = new FormData();
      formData.append("mode", mode);
      formData.append("kind_filter", kindFilter);
      formData.append("genres", mode === "genres" ? selectedGenres.join(",") : "");

      let endpoint = `${API_BASE_URL}/recommend/zip`;
      if (importMethod === "zip") {
        if (!zipFile) return;
        formData.append("file", zipFile);
      } else {
        endpoint = `${API_BASE_URL}/recommend/letterboxd`;
        formData.append("username", letterboxdUsername.trim());
      }

      const response = await fetch(endpoint, {
        method: "POST",
        headers: { Authorization: `Bearer ${token}` },
        body: formData,
      });

      if (!response.ok) {
        const body = await response.json().catch(() => null);
        throw new Error(body?.detail ?? "No pude hablar con el backend.");
      }

      const data = (await response.json()) as RecommendResponse;
      if (!data.recommendations.length) {
        throw new Error("No pude leer ratings válidos de esa fuente.");
      }

      setResult(data);
      setFeedbackState({});
      toast.success("Tus picks están listos.");
      if (data.discarded_rows > 0) {
        toast.warning(
          `${data.discarded_rows} fila${data.discarded_rows === 1 ? "" : "s"} del CSV no se pudo${
            data.discarded_rows === 1 ? "" : "ieron"
          } importar (sin título o sin rating válido).`
        );
      }
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
          <div className="grid grid-cols-1 lg:grid-cols-12 gap-12">
            <aside className="lg:col-span-4 space-y-10 lg:sticky lg:top-24 lg:self-start">
              <div>
                <div className="font-mono text-[10px] uppercase tracking-widest mb-3 text-muted-foreground">
                  [01] Fuente
                </div>
                <div className="flex gap-0 mb-4">
                  <button onClick={() => setImportMethod("zip")} className={tabCls(importMethod === "zip")}>
                    Subir .zip
                  </button>
                  <button onClick={() => setImportMethod("username")} className={tabCls(importMethod === "username")}>
                    Username
                  </button>
                </div>

                {importMethod === "zip" ? (
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
                ) : (
                  <div>
                    <p className="font-mono text-[10px] uppercase leading-relaxed text-muted-foreground mb-3">
                      Leemos tu diario público de Letterboxd (ratings, fechas, rewatches). No
                      cubre likes/favoritos. Tu perfil tiene que ser público.
                    </p>
                    <input
                      value={letterboxdUsername}
                      onChange={(e) => setLetterboxdUsername(e.target.value)}
                      placeholder="ej: scorsese"
                      className="w-full bg-transparent border-b-2 border-foreground py-3 font-mono text-sm placeholder:text-muted-foreground focus:outline-none focus:border-accent"
                    />
                  </div>
                )}
              </div>

              <div>
                <div className="font-mono text-[10px] uppercase tracking-widest mb-3 text-muted-foreground">
                  [02] Qué querés ver hoy
                </div>
                <div className="space-y-2">
                  {modeOptions.map((option) => (
                    <button
                      key={option.mode}
                      onClick={() => setMode(option.mode)}
                      className={`w-full text-left px-4 py-3 border font-mono text-xs uppercase tracking-widest transition-colors ${
                        mode === option.mode
                          ? "bg-foreground text-background border-foreground"
                          : "border-foreground/20 hover:border-foreground"
                      }`}
                    >
                      <span className="text-accent mr-2">{mode === option.mode ? "●" : "○"}</span>
                      {option.label}
                    </button>
                  ))}
                </div>
                {mode === "genres" && (
                  <div className="mt-4 flex flex-wrap gap-2">
                    {genreOptions.map((genre) => (
                      <button
                        key={genre.key}
                        onClick={() => toggleGenre(genre.key)}
                        className={`px-3 py-1 font-mono text-[10px] uppercase tracking-widest border transition-colors ${
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
                  <p className="font-mono text-[10px] text-destructive mt-2">Elegí al menos un género.</p>
                )}
              </div>

              <div>
                <div className="font-mono text-[10px] uppercase tracking-widest mb-3 text-muted-foreground">
                  [03] Formato
                </div>
                <div className="flex gap-0">
                  {kindFilterOptions.map((option) => (
                    <button key={option.value} onClick={() => setKindFilter(option.value)} className={tabCls(kindFilter === option.value)}>
                      {option.label}
                    </button>
                  ))}
                </div>
              </div>

              <button
                onClick={handleGenerate}
                disabled={loading || !canGenerate}
                className="w-full px-8 py-4 bg-accent text-accent-foreground font-mono text-xs uppercase tracking-widest hover:bg-foreground hover:text-background transition-colors disabled:opacity-60"
              >
                Dame mis recomendaciones
              </button>
            </aside>

            <section className="lg:col-span-8">
              <div className="p-8 border-2 border-dashed border-foreground/20 text-center font-mono text-[10px] uppercase tracking-widest text-muted-foreground">
                Tus picks van a aparecer acá
              </div>
            </section>
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
            <div className="flex items-center gap-4 mb-12">
              <span className="font-mono text-xs px-2 py-1 border border-foreground/20">
                [Resultados · {result.recommendations.length}]
              </span>
              <div className="h-px flex-grow bg-foreground/10" />
              <span className="font-mono text-[10px] uppercase tracking-widest text-muted-foreground hidden md:inline max-w-md truncate">
                {result.taste_summary}
              </span>
              <button
                onClick={() => {
                  setResult(null);
                  setFeedbackState({});
                }}
                className="font-mono text-[10px] uppercase tracking-widest hover:text-accent transition-colors shrink-0"
              >
                ↻ Nuevos picks
              </button>
            </div>

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
