import { Check, Copy, Link2, Loader2 } from "lucide-react";
import { useEffect, useState } from "react";
import { toast } from "sonner";
import { useLocation, useSearchParams } from "wouter";

import { MovieModal, type Recommendation } from "@/components/MovieModal";
import { PageTransition } from "@/components/PageTransition";
import { PosterCard } from "@/components/PosterCard";
import { API_BASE_URL, useAuth } from "@/hooks/useAuth";
import { useLang, type Lang } from "@/lib/i18n";

type WrappedTitle = {
  title: string;
  rating: number;
  source: "import" | "manual" | "like" | "star" | "game";
  review: string;
  poster_path: string | null;
  release_year: number | null;
  tmdb_id: number | null;
  kind: string | null;
};

type LabelCount = { label: string; count: number };

type WrappedData = {
  year: number | null;
  available_years: { year: number; count: number }[];
  enough_data: boolean;
  total: number;
  precise_count: number;
  dated_count: number;
  review_count: number;
  average_rating: number | null;
  by_month: { month: number; count: number }[];
  top_month: number | null;
  favorites: WrappedTitle[];
  picks_count: number;
  match_curve: { month: string; avg_match: number; count: number }[];
  vibes: LabelCount[];
  decades: { decade: number; count: number }[];
  movements: LabelCount[];
};

const PRECISE_SOURCES = ["import", "star"];

function stars(rating: number): string {
  return "★".repeat(Math.floor(rating)) + (rating % 1 ? "½" : "");
}

function locale(lang: Lang): string {
  return lang === "en" ? "en-US" : "es-AR";
}

// Intl ya sabe los doce meses en los dos idiomas: mantener 24 claves a mano
// sería puro trabajo repetido
function monthName(month: number, lang: Lang, style: "short" | "long" = "short"): string {
  return new Date(2000, month - 1, 1).toLocaleDateString(locale(lang), { month: style });
}

// una favorita se dibuja con el póster compartido (tilt + glare + modal). El
// id -1 y match_score 50 no son un hack propio: es el mismo contrato que usa
// /weekly en la home para picks que no tienen fila en recommendations_served
// (submitFeedback corta en id < 0, y "Ya la vi" pega a /profile/rate, que no
// necesita id). El "why" es la propia reseña del usuario.
function asRecommendation(item: WrappedTitle): Recommendation {
  return {
    id: -1,
    tmdb_id: item.tmdb_id,
    title: item.title,
    year: item.release_year ?? 0,
    kind: item.kind ?? "movie",
    why: item.review,
    match_score: 50,
    tags: [],
    poster_path: item.poster_path,
    backdrop_path: null,
    overview: "",
    vote_average: null,
    refined: true,
  };
}

function SectionTitle({ label, note }: { label: string; note?: string }) {
  return (
    <div className="mb-8">
      <div className="flex items-baseline gap-4">
        <span className="font-mono text-xs px-2 py-1 border border-foreground/20 shrink-0">{label}</span>
        <div className="h-px flex-grow bg-foreground/10" />
      </div>
      {note && (
        <p className="font-mono text-[10px] uppercase tracking-widest leading-relaxed text-muted-foreground/70 mt-3 max-w-2xl">
          {note}
        </p>
      )}
    </div>
  );
}

function BarRow({ label, value, max, caption }: { label: string; value: number; max: number; caption?: string }) {
  const pct = max > 0 ? value / max : 0;
  return (
    <div className="flex items-center gap-3">
      <span className="font-mono text-[10px] uppercase tracking-widest text-muted-foreground w-14 shrink-0">
        {label}
      </span>
      <div className="flex-1 h-7 bg-foreground/5">
        <div className="h-full bg-accent" style={{ width: `${pct * 100}%`, opacity: 0.35 + pct * 0.65 }} />
      </div>
      <span className="font-mono text-xs w-16 text-right shrink-0">{caption ?? value}</span>
    </div>
  );
}

// dos botones de copiar: el resumen en texto es lo que de verdad se manda por
// chat. No hay generación de imagen a propósito — la página está pensada para
// que una captura quede bien.
function ShareRow({ data }: { data: WrappedData }) {
  const { t } = useLang();
  const [copied, setCopied] = useState<"text" | "link" | null>(null);

  async function copy(kind: "text" | "link", value: string) {
    try {
      await navigator.clipboard.writeText(value);
      setCopied(kind);
      setTimeout(() => setCopied(null), 2000);
    } catch {
      // el portapapeles falla en contexto no seguro o sin permiso: avisar,
      // no fingir que copió
      setCopied(null);
      toast.error(t("wrapped.copyError"));
    }
  }

  const url = `${window.location.origin}/wrapped${data.year ? `?year=${data.year}` : ""}`;
  const summary = t("wrapped.shareText", {
    year: data.year ?? "",
    total: data.total,
    average: data.average_rating ?? t("wrapped.noAverage"),
    top: data.favorites[0]?.title ?? "—",
    url,
  });

  const button = "flex items-center gap-2 px-4 py-3 font-mono text-[10px] uppercase tracking-widest border-2 border-foreground hover:bg-accent hover:border-accent hover:text-accent-foreground transition-colors";

  return (
    <section className="mt-20 border-t-2 border-foreground pt-10">
      <SectionTitle label={t("wrapped.share")} note={t("wrapped.shareNote")} />
      <div className="flex flex-wrap gap-3">
        <button type="button" onClick={() => copy("text", summary)} className={button}>
          {copied === "text" ? <Check className="w-3.5 h-3.5" /> : <Copy className="w-3.5 h-3.5" />}
          {copied === "text" ? t("wrapped.copied") : t("wrapped.copyText")}
        </button>
        <button type="button" onClick={() => copy("link", url)} className={button}>
          {copied === "link" ? <Check className="w-3.5 h-3.5" /> : <Link2 className="w-3.5 h-3.5" />}
          {copied === "link" ? t("wrapped.copied") : t("wrapped.copyLink")}
        </button>
      </div>
      <p className="font-mono text-[10px] leading-relaxed text-muted-foreground/60 mt-5 max-w-2xl normal-case">
        {summary}
      </p>
    </section>
  );
}

export default function Wrapped() {
  const { isAuthenticated, loading: authLoading, token } = useAuth();
  const { t, lang } = useLang();
  const [, navigate] = useLocation();
  // el año vive en la URL (no en estado) para que el link copiado abra el
  // mismo año. useSearchParams de wouter re-renderiza cuando cambia solo el
  // query string; useLocation NO (su path es "/wrapped" en los dos casos).
  const [searchParams, setSearchParams] = useSearchParams();
  const [data, setData] = useState<WrappedData | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  const [selected, setSelected] = useState<Recommendation | null>(null);

  const rawYear = Number(searchParams.get("year"));
  const requestedYear = Number.isInteger(rawYear) && rawYear > 0 ? rawYear : null;

  useEffect(() => {
    if (!authLoading && !isAuthenticated) navigate("/login");
  }, [authLoading, isAuthenticated, navigate]);

  useEffect(() => {
    if (!token) return;
    let cancelled = false;
    setLoading(true);
    setError("");

    fetch(`${API_BASE_URL}/wrapped${requestedYear ? `?year=${requestedYear}` : ""}`, {
      headers: { Authorization: `Bearer ${token}` },
    })
      .then(async (response) => {
        if (!response.ok) {
          const body = await response.json().catch(() => null);
          throw new Error(body?.detail ?? t("wrapped.error"));
        }
        return response.json();
      })
      .then((body: WrappedData) => {
        if (!cancelled) setData(body);
      })
      .catch((err) => {
        if (!cancelled) setError(err instanceof Error ? err.message : t("wrapped.error"));
      })
      .finally(() => {
        if (!cancelled) setLoading(false);
      });

    return () => {
      cancelled = true;
    };
  }, [token, requestedYear]);

  if (authLoading || !isAuthenticated) {
    return (
      <div className="min-h-screen flex items-center justify-center">
        <Loader2 className="w-8 h-8 animate-spin text-accent" />
      </div>
    );
  }

  const monthMax = Math.max(...(data?.by_month ?? []).map((m) => m.count), 1);
  const decadeMax = Math.max(...(data?.decades ?? []).map((d) => d.count), 1);
  const inProgress = data?.year === new Date().getFullYear();

  return (
    <PageTransition>
      <main className="max-w-5xl mx-auto px-5 sm:px-6 pt-12 pb-24">
        <header className="pb-8 border-b-2 border-foreground mb-10">
          <div className="font-mono text-[10px] uppercase tracking-widest text-muted-foreground mb-3">
            {t("wrapped.kicker")}
          </div>
          <h1 className="text-6xl sm:text-8xl font-black uppercase tracking-tighter leading-[0.85]">
            {data?.year ?? "—"}
          </h1>
          <p className="font-serif italic text-2xl sm:text-3xl text-muted-foreground mt-3">
            {t("wrapped.title")}
          </p>
          {inProgress && (
            <p className="font-mono text-[10px] uppercase tracking-widest text-accent mt-4">
              {t("wrapped.inProgress")}
            </p>
          )}

          {data && data.available_years.length > 1 && (
            <nav aria-label={t("wrapped.yearPicker")} className="mt-8">
              <div className="font-mono text-[10px] uppercase tracking-widest text-muted-foreground mb-3">
                {t("wrapped.yearPicker")}
              </div>
              <div className="flex flex-wrap gap-2">
                {data.available_years.map((entry) => (
                  <button
                    key={entry.year}
                    type="button"
                    onClick={() => setSearchParams({ year: String(entry.year) })}
                    aria-current={entry.year === data.year}
                    className={`px-3 py-2 font-mono text-[10px] uppercase tracking-widest border-2 transition-colors ${
                      entry.year === data.year
                        ? "bg-accent border-accent text-accent-foreground"
                        : "border-foreground/20 hover:border-accent hover:text-accent"
                    }`}
                  >
                    {entry.year}
                    <span className="ml-2 opacity-60">{entry.count}</span>
                  </button>
                ))}
              </div>
            </nav>
          )}
        </header>

        {loading && (
          <div className="py-24 text-center">
            <Loader2 className="w-7 h-7 text-accent animate-spin mx-auto mb-4" />
            <p className="font-mono text-xs uppercase text-muted-foreground">{t("wrapped.loading")}</p>
          </div>
        )}

        {!loading && error && (
          <div className="p-4 border-2 border-destructive/50 font-mono text-xs text-destructive">{error}</div>
        )}

        {/* sin un solo título con fecha usable no hay año que contar */}
        {!loading && !error && data && data.year === null && (
          <div className="p-10 border-2 border-dashed border-foreground/20 text-center">
            <h2 className="text-3xl font-black uppercase tracking-tighter mb-3">{t("wrapped.emptyTitle")}</h2>
            <p className="font-mono text-xs uppercase leading-relaxed text-muted-foreground mb-6 max-w-md mx-auto">
              {t("wrapped.emptyBody")}
            </p>
            <button
              onClick={() => navigate("/rate")}
              className="inline-flex items-center gap-2 px-6 py-3 bg-accent text-accent-foreground font-mono text-xs uppercase tracking-widest hover:bg-foreground hover:text-background transition-colors"
            >
              {t("wrapped.emptyCta")}
            </button>
          </div>
        )}

        {/* el año elegido existe pero es demasiado flaco para contar algo */}
        {!loading && !error && data && data.year !== null && !data.enough_data && (
          <div className="p-10 border-2 border-dashed border-foreground/20 text-center">
            <h2 className="text-3xl font-black uppercase tracking-tighter mb-3">
              {t("wrapped.emptyYearTitle", { year: data.year })}
            </h2>
            <p className="font-mono text-xs uppercase leading-relaxed text-muted-foreground max-w-md mx-auto">
              {data.total === 0
                ? t("wrapped.emptyYearNone", { year: data.year })
                : t("wrapped.emptyYearBody", { n: data.total, year: data.year })}
            </p>
          </div>
        )}

        {!loading && !error && data && data.year !== null && data.enough_data && (
          <>
            <div className="grid grid-cols-2 md:grid-cols-4 border-2 border-foreground">
              {[
                { label: t("wrapped.statTitles"), value: data.total },
                {
                  label: t("wrapped.statAverage"),
                  value: data.average_rating ?? t("wrapped.noAverage"),
                  note: data.average_rating !== null ? t("wrapped.averageNote", { n: data.precise_count }) : undefined,
                },
                { label: t("wrapped.statReviews"), value: data.review_count },
                { label: t("wrapped.statPicks"), value: data.picks_count },
              ].map((stat, i) => (
                <div
                  key={stat.label}
                  className={`px-4 py-5 border-foreground/20 ${i % 2 === 1 ? "border-l" : ""} ${
                    i > 0 ? "md:border-l" : ""
                  } ${i >= 2 ? "border-t md:border-t-0" : ""}`}
                >
                  <div className="text-4xl font-black tracking-tighter">{stat.value}</div>
                  <div className="font-mono text-[10px] uppercase tracking-widest text-muted-foreground mt-1">
                    {stat.label}
                  </div>
                  {stat.note && (
                    <div className="font-mono text-[9px] uppercase tracking-widest text-muted-foreground/60 mt-1">
                      {stat.note}
                    </div>
                  )}
                </div>
              ))}
            </div>

            {/* qué se está contando: sin esto los números no se pueden explicar */}
            <p className="font-mono text-[10px] uppercase tracking-widest leading-relaxed text-muted-foreground/70 mt-4 max-w-3xl">
              {data.dated_count === data.total
                ? t("wrapped.countingNoteAll", { total: data.total })
                : data.dated_count === 0
                  ? t("wrapped.countingNoteNone", { total: data.total })
                  : t("wrapped.countingNote", { dated: data.dated_count, total: data.total })}
            </p>

            {data.favorites.length > 0 && (
              <section className="mt-16">
                <SectionTitle label={t("wrapped.favorites")} note={t("wrapped.favoritesNote")} />
                <div className="grid grid-cols-2 sm:grid-cols-3 lg:grid-cols-4 gap-x-5 gap-y-10">
                  {data.favorites.map((item, i) => {
                    const rec = asRecommendation(item);
                    const precise = PRECISE_SOURCES.includes(item.source);
                    return (
                      <PosterCard
                        key={`${item.title}-${i}`}
                        rec={rec}
                        index={i}
                        showScore={false}
                        onSelect={() => setSelected(rec)}
                      >
                        <h3 className="text-base font-black uppercase tracking-tighter leading-none mb-1 group-hover:text-accent transition-colors">
                          {item.title}
                        </h3>
                        <p className="font-mono text-[10px] text-accent">
                          {precise ? stars(item.rating) : t("wrapped.ratedInButaca")}
                          {item.release_year ? (
                            <span className="text-muted-foreground"> · {item.release_year}</span>
                          ) : null}
                        </p>
                      </PosterCard>
                    );
                  })}
                </div>
              </section>
            )}

            <section className="mt-20">
              <SectionTitle
                label={t("wrapped.months")}
                note={
                  data.top_month
                    ? t("wrapped.topMonth", { month: monthName(data.top_month, lang, "long") })
                    : undefined
                }
              />
              <div className="space-y-2">
                {data.by_month.map((entry) => (
                  <BarRow
                    key={entry.month}
                    label={monthName(entry.month, lang)}
                    value={entry.count}
                    max={monthMax}
                  />
                ))}
              </div>
            </section>

            {data.decades.length > 0 && (
              <section className="mt-20">
                <SectionTitle
                  label={t("wrapped.decades")}
                  note={t("wrapped.decadesNote", {
                    n: data.decades.reduce((sum, d) => sum + d.count, 0),
                  })}
                />
                <div className="space-y-2">
                  {data.decades.map((entry) => (
                    <BarRow key={entry.decade} label={`${entry.decade}s`} value={entry.count} max={decadeMax} />
                  ))}
                </div>
              </section>
            )}

            {data.movements.length > 0 && (
              <section className="mt-20">
                <SectionTitle label={t("wrapped.movements")} note={t("wrapped.movementsNote")} />
                <ol className="border-2 border-foreground">
                  {data.movements.map((movement, i) => (
                    <li
                      key={movement.label}
                      className={`flex items-baseline justify-between gap-4 px-5 py-4 ${
                        i > 0 ? "border-t border-foreground/20" : ""
                      }`}
                    >
                      <span className="flex items-baseline gap-4 min-w-0">
                        <span className="font-mono text-xs text-muted-foreground">
                          {String(i + 1).padStart(2, "0")}
                        </span>
                        <span className="font-serif italic text-xl sm:text-2xl truncate">{movement.label}</span>
                      </span>
                      <span className="font-mono text-xs text-accent shrink-0">{movement.count}</span>
                    </li>
                  ))}
                </ol>
              </section>
            )}

            {data.match_curve.length > 0 && (
              <section className="mt-20">
                <SectionTitle label={t("wrapped.matchCurve")} note={t("wrapped.matchCurveNote")} />
                <div className="space-y-2">
                  {data.match_curve.map((point) => (
                    <BarRow
                      key={point.month}
                      label={monthName(Number(point.month.slice(5, 7)), lang)}
                      value={point.avg_match}
                      max={100}
                      caption={`${point.avg_match}%`}
                    />
                  ))}
                </div>
              </section>
            )}

            {data.vibes.length > 0 && (
              <section className="mt-20">
                <SectionTitle label={t("wrapped.vibes")} note={t("wrapped.vibesNote")} />
                <div className="flex flex-wrap gap-2">
                  {data.vibes.map((vibe) => (
                    <span
                      key={vibe.label}
                      className="px-3 py-2 border-2 border-foreground/20 font-mono text-[10px] uppercase tracking-widest"
                    >
                      {vibe.label}
                      <span className="ml-2 text-accent">{vibe.count}</span>
                    </span>
                  ))}
                </div>
              </section>
            )}

            <ShareRow data={data} />
          </>
        )}
      </main>

      {selected && (
        <MovieModal
          rec={selected}
          token={token}
          // readOnly: acá no hay pick que aprobar ni rechazar, son películas
          // que YA viste y puntuaste. Esconde feedback y re-puntuar en vez de
          // dejar botones que no tendrían a dónde escribir (id -1).
          readOnly
          onClose={() => setSelected(null)}
          onFeedback={() => {}}
          onRate={async () => false}
        />
      )}
    </PageTransition>
  );
}
