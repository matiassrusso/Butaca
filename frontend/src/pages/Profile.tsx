import { Loader2 } from "lucide-react";
import { useEffect, useState } from "react";
import { toast } from "sonner";
import { useLocation } from "wouter";

import { PageTransition } from "@/components/PageTransition";
import { API_BASE_URL, useAuth } from "@/hooks/useAuth";
import { useLang, type Lang } from "@/lib/i18n";

type GenreWeight = { genre: string; weight: number };
type DecadeCount = { decade: number; count: number };
type PersonCount = { name: string; count: number };

type TasteProfile = {
  matched_count: number;
  total_count: number;
  genre_breakdown: GenreWeight[];
  decade_breakdown: DecadeCount[];
  top_directors: PersonCount[];
  top_actors: PersonCount[];
};

type ProfileSummary = {
  username: string;
  email: string | null;
  email_verified: boolean;
  member_since: string;
  rated_count: number;
  session_count: number;
  feedback_count: number;
  watchlist_count: number;
  top_title: string | null;
  avatar_url: string | null;
};

// created_at viene como "YYYY-MM-DD HH:MM:SS" UTC de ambos backends
function formatMemberSince(value: string, lang: Lang): string {
  const date = new Date(value.replace(" ", "T") + "Z");
  if (Number.isNaN(date.getTime())) return "";
  return date.toLocaleDateString(lang === "en" ? "en-US" : "es-AR", {
    month: "long",
    year: "numeric",
  });
}

const RADAR_SIZE = 360;
const RADAR_CENTER = RADAR_SIZE / 2;
const RADAR_RADIUS = 140;

function GenreRadar({ genres }: { genres: GenreWeight[] }) {
  const n = genres.length;
  const maxWeight = Math.max(...genres.map((g) => g.weight), 1);

  const pointFor = (index: number, fraction: number) => {
    const angle = (Math.PI * 2 * index) / n - Math.PI / 2;
    return {
      x: RADAR_CENTER + Math.cos(angle) * RADAR_RADIUS * fraction,
      y: RADAR_CENTER + Math.sin(angle) * RADAR_RADIUS * fraction,
    };
  };

  const dataPoints = genres.map((g, i) => pointFor(i, g.weight / maxWeight));
  const dataPath = dataPoints.map((p) => `${p.x},${p.y}`).join(" ");

  return (
    <svg viewBox={`0 0 ${RADAR_SIZE} ${RADAR_SIZE}`} className="w-full h-auto max-w-md mx-auto">
      {[0.25, 0.5, 0.75, 1].map((ring) => (
        <circle key={ring} cx={RADAR_CENTER} cy={RADAR_CENTER} r={RADAR_RADIUS * ring} fill="none" stroke="currentColor" strokeOpacity={0.08} />
      ))}
      {genres.map((_, i) => {
        const edge = pointFor(i, 1);
        return (
          <line key={i} x1={RADAR_CENTER} y1={RADAR_CENTER} x2={edge.x} y2={edge.y} stroke="currentColor" strokeOpacity={0.06} />
        );
      })}
      <polygon points={dataPath} fill="var(--color-accent)" fillOpacity={0.18} stroke="var(--color-accent)" strokeWidth={2} />
      {dataPoints.map((p, i) => (
        <circle key={i} cx={p.x} cy={p.y} r={4} fill="var(--color-accent)" />
      ))}
      {genres.map((g, i) => {
        const label = pointFor(i, 1.16);
        return (
          <text
            key={g.genre}
            x={label.x}
            y={label.y}
            textAnchor="middle"
            dominantBaseline="middle"
            className="fill-current font-mono uppercase"
            style={{ fontSize: 10, letterSpacing: "0.1em" }}
          >
            {g.genre}
          </text>
        );
      })}
    </svg>
  );
}

function DecadeHeatmap({ decades }: { decades: DecadeCount[] }) {
  const maxCount = Math.max(...decades.map((d) => d.count), 1);

  return (
    <div className="space-y-3">
      {decades.map((d) => {
        const pct = d.count / maxCount;
        return (
          <div key={d.decade} className="flex items-center gap-4">
            <span className="font-mono text-[10px] uppercase tracking-widest text-muted-foreground w-16 shrink-0">
              {d.decade}s
            </span>
            <div className="flex-1 h-8 bg-foreground/5">
              <div className="h-full bg-accent" style={{ width: `${pct * 100}%`, opacity: 0.3 + pct * 0.7 }} />
            </div>
            <span className="font-mono text-xs w-8 text-right">{d.count}</span>
          </div>
        );
      })}
    </div>
  );
}

function PeopleList({ people }: { people: PersonCount[] }) {
  const { t } = useLang();
  return (
    <ol className="space-y-3">
      {people.map((p, i) => (
        <li key={p.name} className="flex items-baseline justify-between py-2 border-b border-foreground/5">
          <span className="flex items-baseline gap-4">
            <span className="font-mono text-xs text-muted-foreground w-6">{String(i + 1).padStart(2, "0")}</span>
            <span className="font-medium">{p.name}</span>
          </span>
          <span className="font-mono text-xs text-accent">
            {t("profile.watchedCount", { n: p.count })}
          </span>
        </li>
      ))}
    </ol>
  );
}

// Tu cuenta de Letterboxd (pedido de Matías, 2026-07-31). No es cosmético: el
// backend solo persiste un import por username si es el tuyo, así que un amigo
// probando la página con su usuario ya no te pisa el perfil. La reclama sola el
// primer import; esto existe para corregirla o desvincularla.
function LetterboxdAccount() {
  const { user, saveLetterboxdUsername } = useAuth();
  const { t } = useLang();
  const [value, setValue] = useState(user?.letterboxdUsername ?? "");
  const [saving, setSaving] = useState(false);

  useEffect(() => {
    setValue(user?.letterboxdUsername ?? "");
  }, [user?.letterboxdUsername]);

  const dirty = value.trim() !== (user?.letterboxdUsername ?? "");

  async function save() {
    setSaving(true);
    try {
      await saveLetterboxdUsername(value.trim());
      toast.success(t(value.trim() ? "profile.letterboxdSaved" : "profile.letterboxdUnlinked"));
    } catch {
      toast.error(t("profile.letterboxdError"));
    } finally {
      setSaving(false);
    }
  }

  return (
    <div className="mt-10 border-2 border-foreground p-5">
      <label
        htmlFor="letterboxd-account"
        className="block font-mono text-[10px] uppercase tracking-widest text-muted-foreground mb-2"
      >
        {t("profile.letterboxdLabel")}
      </label>
      <div className="flex flex-wrap items-center gap-3">
        <input
          id="letterboxd-account"
          value={value}
          onChange={(e) => setValue(e.target.value)}
          placeholder={t("profile.letterboxdPlaceholder")}
          className="flex-1 min-w-40 bg-transparent border-b-2 border-foreground/30 py-2 font-mono text-sm placeholder:text-muted-foreground focus:outline-none focus:border-accent"
        />
        <button
          onClick={save}
          disabled={!dirty || saving}
          className="px-4 py-2 font-mono text-[10px] uppercase tracking-widest border border-foreground/30 hover:border-accent hover:text-accent disabled:opacity-40 disabled:hover:border-foreground/30 disabled:hover:text-foreground transition-colors"
        >
          {saving ? t("profile.letterboxdSaving") : t("common.save")}
        </button>
      </div>
      <p className="font-mono text-[10px] uppercase leading-relaxed text-muted-foreground/60 mt-3">
        {t("profile.letterboxdNote")}
      </p>
    </div>
  );
}

export default function Profile() {
  const { isAuthenticated, loading: authLoading, token, user, deleteAccount } = useAuth();
  const { t, lang } = useLang();
  const [, navigate] = useLocation();
  const [profile, setProfile] = useState<TasteProfile | null>(null);
  const [summary, setSummary] = useState<ProfileSummary | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");

  // danger zone: delete account (two-step — type username + password)
  const [confirmUsername, setConfirmUsername] = useState("");
  const [deletePassword, setDeletePassword] = useState("");
  const [deleting, setDeleting] = useState(false);
  const [deleteError, setDeleteError] = useState("");

  async function handleDeleteAccount() {
    setDeleting(true);
    setDeleteError("");
    try {
      await deleteAccount(deletePassword);
      toast.success(t("profile.deleteSuccess"));
      navigate("/");
    } catch (err) {
      setDeleteError(err instanceof Error ? err.message : t("profile.deleteError"));
    } finally {
      setDeleting(false);
    }
  }

  useEffect(() => {
    if (!authLoading && !isAuthenticated) {
      navigate("/login");
    }
  }, [authLoading, isAuthenticated, navigate]);

  useEffect(() => {
    if (!token) {
      setLoading(false);
      return;
    }

    let cancelled = false;
    setLoading(true);
    setError("");

    // el summary (cuenta + actividad) es independiente del mapa de afinidad:
    // si TMDb falla, el header del perfil se muestra igual
    fetch(`${API_BASE_URL}/profile/summary`, {
      headers: { Authorization: `Bearer ${token}` },
    })
      .then((response) => (response.ok ? response.json() : null))
      .then((body: ProfileSummary | null) => {
        if (!cancelled && body) setSummary(body);
      })
      .catch(() => {});

    fetch(`${API_BASE_URL}/profile/taste`, {
      headers: { Authorization: `Bearer ${token}` },
    })
      .then(async (response) => {
        if (!response.ok) {
          const body = await response.json().catch(() => null);
          throw new Error(body?.detail ?? t("profile.tasteError"));
        }
        return response.json();
      })
      .then((body: TasteProfile) => {
        if (!cancelled) setProfile(body);
      })
      .catch((err) => {
        if (!cancelled) setError(err instanceof Error ? err.message : t("profile.tasteError"));
      })
      .finally(() => {
        if (!cancelled) setLoading(false);
      });

    return () => {
      cancelled = true;
    };
  }, [token]);

  if (authLoading || !isAuthenticated) {
    return (
      <div className="min-h-screen flex items-center justify-center">
        <Loader2 className="w-8 h-8 animate-spin text-accent" />
      </div>
    );
  }

  const hasProfile = profile && profile.matched_count > 0;

  return (
    <PageTransition>
      <main className="max-w-7xl mx-auto px-6 pt-16 pb-24">
        {/* Perfil real (feedback #20): identidad + actividad, no solo el mapa */}
        <header className="pb-10 border-b-2 border-foreground mb-16">
          <div className="flex flex-col md:flex-row md:items-end gap-8">
            {/* avatar: still de la peli mejor puntuada (feedback #16), cae a la inicial */}
            <div className="shrink-0">
              {summary?.avatar_url ? (
                <img
                  src={summary.avatar_url}
                  alt={
                    summary.top_title
                      ? t("profile.avatarAlt", { title: summary.top_title })
                      : t("profile.avatarFallbackAlt")
                  }
                  className="size-28 md:size-32 object-cover border-2 border-foreground"
                />
              ) : (
                <div className="size-28 md:size-32 grid place-items-center bg-foreground text-background border-2 border-foreground font-black text-5xl uppercase">
                  {user?.username?.[0]?.toUpperCase() ?? "?"}
                </div>
              )}
            </div>

            <div className="min-w-0">
              <div className="font-mono text-[10px] uppercase tracking-widest text-muted-foreground mb-3">
                {t("profile.kicker")}
              </div>
              <h1 className="text-5xl md:text-6xl font-black uppercase tracking-tighter leading-[0.9] break-words">
                {user?.username}
              </h1>
              <p className="font-mono text-[10px] uppercase tracking-widest text-muted-foreground mt-4">
                {summary?.member_since &&
                  t("profile.memberSince", {
                    date: formatMemberSince(summary.member_since, lang),
                  })}
                {summary?.email && (
                  <>
                    {" · "}
                    <span className="normal-case tracking-normal">{summary.email}</span>
                    {summary.email_verified ? (
                      <span className="text-accent"> {t("profile.emailVerified")}</span>
                    ) : (
                      <span> · {t("profile.emailUnverified")}</span>
                    )}
                  </>
                )}
              </p>
              {summary?.avatar_url && summary.top_title && (
                <p className="font-mono text-[10px] uppercase tracking-widest text-muted-foreground/60 mt-1">
                  {t("profile.avatarFrom", { title: summary.top_title })}
                </p>
              )}
            </div>
          </div>

          <LetterboxdAccount />

          {summary && (
            <div className="grid grid-cols-2 md:grid-cols-4 gap-0 mt-10 border-2 border-foreground">
              {[
                { label: t("profile.statWatched"), value: summary.rated_count },
                { label: t("profile.statSessions"), value: summary.session_count },
                { label: t("profile.statWatchlist"), value: summary.watchlist_count },
                { label: t("profile.statFeedback"), value: summary.feedback_count },
              ].map((stat, i) => (
                <div
                  key={stat.label}
                  className={`px-5 py-4 border-foreground/20 ${i % 2 === 1 ? "border-l" : ""} ${
                    i > 0 ? "md:border-l" : ""
                  } ${i >= 2 ? "border-t md:border-t-0" : ""}`}
                >
                  <div className="text-3xl font-black tracking-tighter">{stat.value}</div>
                  <div className="font-mono text-[10px] uppercase tracking-widest text-muted-foreground">
                    {stat.label}
                  </div>
                </div>
              ))}
            </div>
          )}
        </header>

        <div className="flex items-baseline gap-4 mb-10">
          <span className="font-mono text-xs px-2 py-1 border border-foreground/20">
            {t("profile.affinityMap")}
          </span>
          <div className="h-px flex-grow bg-foreground/10" />
          {profile && profile.matched_count < profile.total_count && (
            <span className="font-mono text-xs text-muted-foreground shrink-0">
              {t("profile.matchedCount", {
                matched: profile.matched_count,
                total: profile.total_count,
              })}
            </span>
          )}
        </div>

        {loading && (
          <div className="py-20 text-center">
            <Loader2 className="w-7 h-7 text-accent animate-spin mx-auto mb-4" />
            <p className="font-mono text-xs uppercase text-muted-foreground">{t("profile.loading")}</p>
          </div>
        )}

        {!loading && error && (
          <div className="p-4 border-2 border-destructive/50 font-mono text-xs text-destructive">{error}</div>
        )}

        {!loading && !error && !hasProfile && (
          <div className="p-10 border-2 border-dashed border-foreground/20 text-center">
            <h2 className="text-2xl font-black uppercase tracking-tighter mb-2">
              {t("profile.emptyTitle")}
            </h2>
            <p className="font-mono text-xs uppercase text-muted-foreground mb-5">
              {t("profile.emptyBody")}
            </p>
            <button
              onClick={() => navigate("/recommend")}
              className="inline-flex items-center gap-2 px-6 py-3 bg-accent text-accent-foreground font-mono text-xs uppercase tracking-widest hover:bg-foreground hover:text-background transition-colors"
            >
              {t("profile.goRecommend")}
            </button>
          </div>
        )}

        {!loading && !error && hasProfile && profile && (
          <>
            <div className="grid grid-cols-1 lg:grid-cols-12 gap-16 mb-20">
              {profile.genre_breakdown.length > 0 && (
                <div className="lg:col-span-6">
                  <div className="flex items-baseline gap-4 mb-8">
                    <span className="font-mono text-xs px-2 py-1 border border-foreground/20">
                      {t("profile.genreSignature")}
                    </span>
                    <div className="h-px flex-grow bg-foreground/10" />
                  </div>
                  <GenreRadar genres={profile.genre_breakdown} />
                </div>
              )}

              {profile.decade_breakdown.length > 0 && (
                <div className="lg:col-span-6">
                  <div className="flex items-baseline gap-4 mb-8">
                    <span className="font-mono text-xs px-2 py-1 border border-foreground/20">
                      {t("profile.decadeTimeline")}
                    </span>
                    <div className="h-px flex-grow bg-foreground/10" />
                  </div>
                  <DecadeHeatmap decades={profile.decade_breakdown} />
                </div>
              )}
            </div>

            <div className="grid grid-cols-1 md:grid-cols-2 gap-16 border-t-2 border-foreground pt-16">
              {profile.top_directors.length > 0 && (
                <div>
                  <div className="flex items-baseline gap-4 mb-8">
                    <span className="font-mono text-xs px-2 py-1 border border-foreground/20">
                      {t("profile.directors")}
                    </span>
                    <div className="h-px flex-grow bg-foreground/10" />
                  </div>
                  <PeopleList people={profile.top_directors} />
                </div>
              )}

              {profile.top_actors.length > 0 && (
                <div>
                  <div className="flex items-baseline gap-4 mb-8">
                    <span className="font-mono text-xs px-2 py-1 border border-foreground/20">
                      {t("profile.cast")}
                    </span>
                    <div className="h-px flex-grow bg-foreground/10" />
                  </div>
                  <PeopleList people={profile.top_actors} />
                </div>
              )}
            </div>
          </>
        )}

        <section className="mt-24 border-t-2 border-destructive/40 pt-10">
          <div className="font-mono text-[10px] uppercase tracking-widest text-destructive mb-3">
            {t("profile.dangerZone")}
          </div>
          <h2 className="text-2xl font-black uppercase tracking-tighter mb-2">
            {t("profile.deleteTitle")}
          </h2>
          <p className="font-mono text-[10px] uppercase tracking-widest text-muted-foreground max-w-md mb-6">
            {t("profile.deleteBody")}
          </p>

          <div className="max-w-md space-y-4">
            <label className="block">
              <span className="font-mono text-[10px] uppercase tracking-widest text-muted-foreground">
                {t("profile.deleteConfirmLabel", { username: user?.username ?? "" })}
              </span>
              <input
                value={confirmUsername}
                onChange={(e) => setConfirmUsername(e.target.value)}
                autoComplete="off"
                className="mt-2 w-full bg-transparent border-b-2 border-foreground py-2 font-mono text-sm focus:outline-none focus:border-destructive"
              />
            </label>
            <label className="block">
              <span className="font-mono text-[10px] uppercase tracking-widest text-muted-foreground">
                {t("profile.deletePassword")}
              </span>
              <input
                type="password"
                value={deletePassword}
                onChange={(e) => setDeletePassword(e.target.value)}
                className="mt-2 w-full bg-transparent border-b-2 border-foreground py-2 font-mono text-sm focus:outline-none focus:border-destructive"
              />
            </label>

            <button
              onClick={handleDeleteAccount}
              disabled={deleting || confirmUsername !== user?.username || !deletePassword}
              className="w-full py-3 border-2 border-destructive text-destructive font-mono text-xs uppercase tracking-widest hover:bg-destructive hover:text-destructive-foreground transition-colors disabled:opacity-40 disabled:cursor-not-allowed disabled:hover:bg-transparent disabled:hover:text-destructive"
            >
              {deleting ? t("profile.deleting") : t("profile.deleteButton")}
            </button>

            {deleteError && (
              <div className="p-3 border-2 border-destructive/50 font-mono text-xs text-destructive">
                {deleteError}
              </div>
            )}
          </div>
        </section>
      </main>
    </PageTransition>
  );
}
