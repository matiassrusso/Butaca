import { AlertCircle, Loader2, Users } from "lucide-react";
import { useEffect, useRef, useState } from "react";
import { toast } from "sonner";
import { useLocation } from "wouter";

import { MovieModal, type Recommendation } from "@/components/MovieModal";
import { PageTransition } from "@/components/PageTransition";
import { PosterCard } from "@/components/PosterCard";
import { API_BASE_URL, useAuth } from "@/hooks/useAuth";
import { useLang } from "@/lib/i18n";

// "¿Qué vemos juntos?": la persona con la que vas a ver algo NO necesita
// cuenta de Butaca, alcanza con su username público de Letterboxd — el mismo
// feed RSS que ya usa el import por username. El backend
// (POST /recommend/together) mergea los dos historiales y devuelve una tanda
// efímera: nada se guarda en el perfil de nadie.

type KindFilter = "movie" | "series" | "both";

const KIND_OPTIONS: { value: KindFilter; labelKey: string }[] = [
  { value: "movie", labelKey: "common.movies" },
  { value: "series", labelKey: "common.series" },
  { value: "both", labelKey: "common.both" },
];

export default function Together() {
  const { isAuthenticated, loading: authLoading, token } = useAuth();
  const [, navigate] = useLocation();
  const { t } = useLang();

  const [username, setUsername] = useState("");
  const [kindFilter, setKindFilter] = useState<KindFilter>("movie");
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");
  const [picks, setPicks] = useState<Recommendation[] | null>(null);
  const [pairName, setPairName] = useState("");
  const [selectedRec, setSelectedRec] = useState<Recommendation | null>(null);
  // mismo ref que /recommend: el typewriter del "why" corre una sola vez por
  // póster y por sesión (MovieModal se desmonta al cerrar)
  const seenWhysRef = useRef<Map<number, string>>(new Map());

  useEffect(() => {
    if (!authLoading && !isAuthenticated) navigate("/login");
  }, [authLoading, isAuthenticated, navigate]);

  async function handleSubmit(event: React.FormEvent) {
    event.preventDefault();
    const friend = username.trim();
    if (!token || !friend || loading) return;

    setLoading(true);
    setError("");
    try {
      const formData = new FormData();
      formData.append("friend_username", friend);
      formData.append("kind_filter", kindFilter);
      // el idioma del backend sale del header Accept-Language, que apiLang.ts
      // ya inyecta envolviendo fetch — acá no va ningún campo de idioma
      const response = await fetch(`${API_BASE_URL}/recommend/together`, {
        method: "POST",
        headers: { Authorization: `Bearer ${token}` },
        body: formData,
      });
      if (!response.ok) {
        const body = await response.json().catch(() => null);
        throw new Error(body?.detail ?? t("together.failed"));
      }
      const data = (await response.json()) as { recommendations: Recommendation[] };
      if (!data.recommendations.length) throw new Error(t("together.empty"));
      setPicks(data.recommendations);
      setPairName(friend);
    } catch (err) {
      const message = err instanceof Error ? err.message : t("together.failed");
      setError(message);
      toast.error(message);
    } finally {
      setLoading(false);
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
      <main className="max-w-5xl mx-auto px-6 pt-16 pb-24">
        <header className="pb-8 border-b-2 border-foreground mb-8">
          <div className="font-mono text-[10px] uppercase tracking-widest text-muted-foreground mb-4 flex items-center gap-2">
            <Users className="w-3.5 h-3.5" />
            {t("together.tag")}
          </div>
          <h1 className="text-6xl md:text-7xl font-black uppercase tracking-tighter leading-[0.9]">
            {t("together.titlePrefix")}
            <span className="text-accent italic font-serif normal-case tracking-normal">
              {t("together.titleAccent")}
            </span>
            {t("together.titleSuffix")}
          </h1>
          <p className="font-mono text-xs text-muted-foreground mt-4 max-w-xl leading-relaxed">
            {t("together.intro")}
          </p>
        </header>

        {!picks && (
          <form onSubmit={handleSubmit} className="max-w-xl">
            <label
              htmlFor="together-username"
              className="block font-mono text-[10px] uppercase tracking-widest text-muted-foreground mb-2"
            >
              {t("together.label")}
            </label>
            <input
              id="together-username"
              value={username}
              onChange={(e) => setUsername(e.target.value)}
              placeholder={t("together.placeholder")}
              autoComplete="off"
              className="w-full px-4 py-3 bg-transparent border-2 border-foreground/20 focus:border-accent focus:outline-none font-mono text-sm"
            />
            <p className="font-mono text-[10px] text-muted-foreground mt-2">
              {t("together.noAccountNeeded")}
            </p>
            <p className="font-mono text-[10px] text-muted-foreground/70 mt-1">
              {t("together.warning")}
            </p>

            <div className="mt-8">
              <div className="font-mono text-[10px] uppercase tracking-widest text-muted-foreground mb-2">
                {t("together.kindLabel")}
              </div>
              <div className="flex gap-2">
                {KIND_OPTIONS.map((option) => (
                  <button
                    key={option.value}
                    type="button"
                    onClick={() => setKindFilter(option.value)}
                    className={`px-4 py-2 font-mono text-[10px] uppercase tracking-widest border transition-colors ${
                      kindFilter === option.value
                        ? "bg-accent text-accent-foreground border-accent"
                        : "border-foreground/30 hover:border-foreground"
                    }`}
                  >
                    {t(option.labelKey)}
                  </button>
                ))}
              </div>
            </div>

            <button
              type="submit"
              disabled={loading || !username.trim()}
              className="mt-8 px-8 py-4 bg-accent text-accent-foreground font-mono text-xs uppercase tracking-widest hover:bg-foreground hover:text-background transition-colors disabled:opacity-40 disabled:cursor-not-allowed"
            >
              {t("together.submit")}
            </button>
            {!username.trim() && (
              <p className="font-mono text-[10px] text-muted-foreground mt-3">{t("together.hint")}</p>
            )}
          </form>
        )}

        {loading && (
          <div className="py-20 text-center">
            <Loader2 className="w-7 h-7 text-accent animate-spin mx-auto mb-6" />
            <h3 className="text-2xl font-black uppercase tracking-tighter mb-3">
              {t("together.loadingTitle")}
            </h3>
            <p className="font-mono text-xs uppercase text-muted-foreground max-w-sm mx-auto">
              {t("together.loadingBody")}
            </p>
          </div>
        )}

        {error && !loading && (
          <div className="mt-6 p-4 border-2 border-destructive/50 flex items-start gap-3">
            <AlertCircle className="w-5 h-5 text-destructive shrink-0 mt-0.5" />
            <p className="font-mono text-xs text-destructive">{error}</p>
          </div>
        )}

        {picks && !loading && (
          <>
            <div className="mb-12">
              <div className="flex items-center gap-4 flex-wrap">
                <span className="font-mono text-xs px-2 py-1 border border-foreground/20 shrink-0">
                  {t("together.resultsBadge", { n: picks.length })}
                </span>
                <div className="h-px flex-grow bg-foreground/10 min-w-8" />
                <button
                  onClick={() => {
                    setPicks(null);
                    setError("");
                  }}
                  className="font-mono text-[10px] uppercase tracking-widest hover:text-accent transition-colors shrink-0"
                >
                  {t("together.tryAnother")}
                </button>
              </div>
              <p className="font-mono text-[10px] uppercase tracking-widest text-muted-foreground mt-3">
                {t("together.resultsFor", { name: pairName })}
              </p>
              <p className="font-mono text-[10px] text-muted-foreground/70 mt-1">
                {t("together.notSaved")}
              </p>
            </div>

            <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-10">
              {picks.map((rec, i) => (
                <PosterCard
                  key={rec.id}
                  rec={rec}
                  index={i + 1}
                  featured
                  onSelect={() => setSelectedRec(rec)}
                >
                  <div className="flex justify-between items-baseline gap-4 mb-4">
                    <h3 className="text-2xl font-black uppercase tracking-tighter leading-none group-hover:text-accent transition-colors">
                      {rec.title}
                    </h3>
                    <span className="font-mono text-xs text-muted-foreground shrink-0">{rec.year}</span>
                  </div>
                </PosterCard>
              ))}
            </div>
          </>
        )}

        {selectedRec && (
          <MovieModal
            key={selectedRec.id}
            rec={selectedRec}
            token={token}
            seenWhys={seenWhysRef}
            onClose={() => setSelectedRec(null)}
            // readOnly: la tanda es efímera y de a dos — puntuar o dar feedback
            // acá escribiría en el perfil de una sola persona un juicio que
            // salió del gusto mezclado de las dos
            readOnly
            onFeedback={() => {}}
            onRate={async () => false}
          />
        )}
      </main>
    </PageTransition>
  );
}
