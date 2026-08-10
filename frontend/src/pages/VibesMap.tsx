import { Loader2 } from "lucide-react";
import { useEffect, useMemo, useRef, useState } from "react";
import { toast } from "sonner";

import { MovieModal, type Recommendation } from "@/components/MovieModal";
import { PageTransition } from "@/components/PageTransition";
import { API_BASE_URL, useAuth } from "@/hooks/useAuth";
import { useLang } from "@/lib/i18n";

// El mapa de vibras: los ~1000 embeddings de la Fase 4 (que hasta ahora solo
// alimentaban el picker de movimientos, invisibles para el usuario) proyectados
// a 2D y explorables. Las coordenadas salen del backend ya calculadas
// (vibes_clustering.project_2d, layout jerárquico anclado a los clusters de
// Leiden — PCA directo daba una mancha: 9% de varianza en dos componentes).

type MapPoint = {
  tmdb_id: number;
  kind: string;
  title: string;
  year: number;
  poster_path: string | null;
  x: number;
  y: number;
  group_id: number;
  movement_id: number;
  rated: boolean;
};

type MapCluster = { id: number; label: string; size: number };
type MapResponse = { points: MapPoint[]; groups: MapCluster[]; movements: MapCluster[] };

// Paleta de tinta de imprenta, no arcoíris de dashboard: todos los tonos van a
// media luminosidad (L≈0.55-0.68 en oklch) para que se lean tanto sobre el
// papel del tema claro (L 0.97) como sobre el obsidiana del oscuro (L 0.14),
// sin necesidad de dos paletas ni de mirar el tema desde JS.
const GROUP_COLORS = [
  "oklch(0.58 0.19 42)", // terracota (el acento de la marca)
  "oklch(0.55 0.13 250)", // azul tinta
  "oklch(0.58 0.11 145)", // verde oliva
  "oklch(0.68 0.14 85)", // mostaza
  "oklch(0.55 0.15 330)", // ciruela
  "oklch(0.60 0.10 200)", // petróleo
  "oklch(0.52 0.16 20)", // ladrillo
];

const VIEW_WIDTH = 1000;
const VIEW_HEIGHT = 680;
const PADDING = 44;

export default function VibesMap() {
  const { token, isAuthenticated } = useAuth();
  const { t } = useLang();
  const [data, setData] = useState<MapResponse | null>(null);
  const [failed, setFailed] = useState(false);
  const [focus, setFocus] = useState<number | null>(null);
  const [hovered, setHovered] = useState<MapPoint | null>(null);
  const [selectedRec, setSelectedRec] = useState<Recommendation | null>(null);
  const [loadingVerdict, setLoadingVerdict] = useState<number | null>(null);
  const seenWhysRef = useRef<Map<number, string>>(new Map());

  useEffect(() => {
    let cancelled = false;
    fetch(`${API_BASE_URL}/vibes/map`, token ? { headers: { Authorization: `Bearer ${token}` } } : {})
      .then((response) => (response.ok ? response.json() : Promise.reject(new Error())))
      .then((body: MapResponse) => {
        if (!cancelled) setData(body);
      })
      .catch(() => {
        if (!cancelled) setFailed(true);
      });
    return () => {
      cancelled = true;
    };
  }, [token]);

  // los puntos vienen en un espacio centrado en 0 de tamaño variable: se
  // reescalan una sola vez al viewBox, no en cada render de cada círculo.
  const placed = useMemo(() => {
    const points = data?.points ?? [];
    if (points.length === 0) return [];
    const xs = points.map((p) => p.x);
    const ys = points.map((p) => p.y);
    const minX = Math.min(...xs);
    const minY = Math.min(...ys);
    const spanX = Math.max(...xs) - minX || 1;
    const spanY = Math.max(...ys) - minY || 1;
    return points.map((point) => ({
      point,
      cx: PADDING + ((point.x - minX) / spanX) * (VIEW_WIDTH - PADDING * 2),
      // el eje Y del SVG crece hacia abajo: sin el flip el mapa sale espejado
      cy: VIEW_HEIGHT - PADDING - ((point.y - minY) / spanY) * (VIEW_HEIGHT - PADDING * 2),
    }));
  }, [data]);

  // enfocar una región recorta el viewBox a sus puntos: sin eso, sus 15
  // movimientos quedan apretados en un rincón y las etiquetas se pisan entre
  // sí. `zoom` reescala radios y tipografía para que se vean igual de grandes.
  const { viewBox, zoom } = useMemo(() => {
    const inFocus = focus == null ? [] : placed.filter(({ point }) => point.group_id === focus);
    if (inFocus.length === 0) {
      return { viewBox: `0 0 ${VIEW_WIDTH} ${VIEW_HEIGHT}`, zoom: 1 };
    }
    const margin = 60;
    const minX = Math.min(...inFocus.map((p) => p.cx)) - margin;
    const minY = Math.min(...inFocus.map((p) => p.cy)) - margin;
    const width = Math.max(Math.max(...inFocus.map((p) => p.cx)) + margin - minX, 120);
    // se mantiene la proporción del lienzo: si no, el SVG estira el contenido
    const height = Math.max(
      Math.max(...inFocus.map((p) => p.cy)) + margin - minY,
      (width * VIEW_HEIGHT) / VIEW_WIDTH,
    );
    return {
      viewBox: `${minX} ${minY} ${(height * VIEW_WIDTH) / VIEW_HEIGHT} ${height}`,
      zoom: VIEW_HEIGHT / height,
    };
  }, [placed, focus]);

  // etiquetas dibujadas encima del mapa: las regiones (L1) siempre, y los
  // movimientos (L2) solo de la región enfocada — los 69 juntos son ilegibles.
  const captions = useMemo(() => {
    if (placed.length === 0) return [];
    const level = focus == null ? "group_id" : "movement_id";
    const source = focus == null ? data?.groups : data?.movements;
    const centers = new Map<number, { x: number; y: number; n: number }>();
    for (const { point, cx, cy } of placed) {
      if (focus != null && point.group_id !== focus) continue;
      const id = point[level as "group_id" | "movement_id"];
      const current = centers.get(id) ?? { x: 0, y: 0, n: 0 };
      centers.set(id, { x: current.x + cx, y: current.y + cy, n: current.n + 1 });
    }
    return (
      [...centers.entries()]
        // los movimientos chicos de una región son muchos y quedan encimados:
        // se rotulan los más grandes, el resto se lee pasando el mouse
        .sort((a, b) => b[1].n - a[1].n)
        .slice(0, focus == null ? centers.size : 8)
        .map(([id, { x, y, n }]) => ({
          id,
          x: x / n,
          y: y / n,
          label: source?.find((cluster) => cluster.id === id)?.label ?? "",
        }))
    );
  }, [placed, focus, data]);

  async function openPoint(point: MapPoint) {
    // sin sesión el veredicto no existe (necesita el perfil de gusto): se abre
    // el modal con lo que sí es cierto — el movimiento donde cayó el título.
    if (!token) {
      const movement = data?.movements.find((m) => m.id === point.movement_id)?.label ?? "";
      setSelectedRec({
        id: -1,
        tmdb_id: point.tmdb_id,
        title: point.title,
        year: point.year,
        kind: point.kind,
        why: t("map.guestWhy", { movement }),
        match_score: 50, // "match desconocido": sin perfil, cualquier número sería inventado
        tags: [],
        poster_path: point.poster_path,
        backdrop_path: null,
        overview: "",
        vote_average: null,
        refined: false,
      });
      return;
    }
    setLoadingVerdict(point.tmdb_id);
    try {
      const response = await fetch(
        `${API_BASE_URL}/titles/${point.tmdb_id}/verdict?kind=${encodeURIComponent(point.kind)}`,
        { headers: { Authorization: `Bearer ${token}` } },
      );
      if (!response.ok) throw new Error();
      const rec: Omit<Recommendation, "id"> & { id: number | null } = await response.json();
      setSelectedRec({ ...rec, id: rec.id ?? -1 });
    } catch {
      toast.error(t("modal.verdictError"));
    } finally {
      setLoadingVerdict(null);
    }
  }

  return (
    <PageTransition>
      <main className="max-w-7xl mx-auto px-6 pt-16 pb-24">
        <header className="pb-8 border-b-2 border-foreground mb-8">
          <div className="font-mono text-[10px] uppercase tracking-widest text-muted-foreground mb-4">
            {t("map.tag")}
          </div>
          <h1 className="text-5xl md:text-7xl font-black uppercase tracking-tighter leading-[0.9]">
            {t("map.titlePrefix")}
            <span className="text-accent italic font-serif normal-case tracking-normal">
              {t("map.titleAccent")}
            </span>
            {t("map.titleSuffix")}
          </h1>
          <p className="mt-6 max-w-3xl font-mono text-xs leading-relaxed text-muted-foreground">
            {t("map.intro")}
          </p>
          {data && data.points.length > 0 && (
            <div className="mt-6 flex flex-wrap gap-8">
              {[
                [data.points.length.toLocaleString(), t("map.statTitles")],
                [String(data.movements.length), t("map.statMovements")],
                ["2.048", t("map.statDimensions")],
              ].map(([value, label]) => (
                <div key={label}>
                  <div className="text-3xl font-black">{value}</div>
                  <div className="font-mono text-[10px] uppercase tracking-widest text-muted-foreground">
                    {label}
                  </div>
                </div>
              ))}
            </div>
          )}
        </header>

        {failed && (
          <p className="font-mono text-xs text-muted-foreground">{t("map.error")}</p>
        )}

        {!failed && !data && (
          <div className="flex items-center gap-3 font-mono text-[10px] uppercase tracking-widest text-muted-foreground py-24">
            <Loader2 className="w-4 h-4 animate-spin text-accent" />
            {t("map.loading")}
          </div>
        )}

        {data && data.points.length === 0 && (
          <p className="font-mono text-xs text-muted-foreground py-12">{t("map.empty")}</p>
        )}

        {data && data.points.length > 0 && (
          <div className="grid lg:grid-cols-[1fr_260px] gap-8 items-start">
            <div className="relative border-2 border-foreground bg-secondary/30">
              <svg
                viewBox={viewBox}
                className="w-full h-auto block touch-pan-y transition-[view-box] duration-300"
                role="img"
                aria-label={t("map.titleAccent")}
              >
                {placed.map(({ point, cx, cy }) => {
                  const dimmed = focus != null && point.group_id !== focus;
                  const color = GROUP_COLORS[(point.group_id - 1) % GROUP_COLORS.length];
                  return (
                    <circle
                      key={`${point.kind}-${point.tmdb_id}`}
                      cx={cx}
                      cy={cy}
                      r={(point.rated ? 7 : 4.5) / zoom}
                      fill={point.rated ? "none" : color}
                      stroke={point.rated ? color : "none"}
                      strokeWidth={point.rated ? 2.5 / zoom : 0}
                      opacity={dimmed ? 0.1 : point.rated ? 1 : 0.72}
                      className="cursor-pointer transition-opacity"
                      onMouseEnter={() => setHovered(point)}
                      onMouseLeave={() => setHovered(null)}
                      onClick={() => openPoint(point)}
                    >
                      {/* nativo, para que en touch (sin hover) igual haya algo */}
                      <title>{`${point.title} (${point.year})`}</title>
                    </circle>
                  );
                })}

                {captions.map((caption) => (
                  <text
                    key={caption.id}
                    x={caption.x}
                    y={caption.y}
                    textAnchor="middle"
                    className="pointer-events-none uppercase"
                    style={{
                      fontFamily: "var(--font-mono)",
                      fontSize: 15 / zoom,
                      letterSpacing: "0.12em",
                      fill: "var(--foreground)",
                      paintOrder: "stroke",
                      stroke: "var(--background)",
                      strokeWidth: 4 / zoom,
                      strokeLinejoin: "round",
                    }}
                  >
                    {caption.label}
                  </text>
                ))}
              </svg>

              {hovered && (
                <div className="pointer-events-none absolute left-3 bottom-3 max-w-[90%] flex items-center gap-3 border-2 border-foreground bg-background px-3 py-2">
                  {hovered.poster_path && (
                    <img src={hovered.poster_path} alt="" className="w-8 aspect-[2/3] object-cover" />
                  )}
                  <div className="min-w-0">
                    <div className="text-sm font-black uppercase tracking-tight truncate">
                      {hovered.title}
                    </div>
                    <div className="font-mono text-[9px] uppercase tracking-widest text-muted-foreground truncate">
                      {hovered.year} · {t("map.tooltipMovement")}:{" "}
                      {data.movements.find((m) => m.id === hovered.movement_id)?.label}
                    </div>
                  </div>
                </div>
              )}

              {loadingVerdict != null && (
                <div className="absolute inset-0 flex items-center justify-center bg-background/70">
                  <div className="flex items-center gap-2 font-mono text-[10px] uppercase tracking-widest">
                    <Loader2 className="w-4 h-4 animate-spin text-accent" />
                    {t("map.verdictLoading")}
                  </div>
                </div>
              )}
            </div>

            <aside className="space-y-6">
              <div>
                <div className="font-mono text-[10px] uppercase tracking-widest text-muted-foreground mb-3">
                  {t("map.legendTitle")}
                </div>
                <ul className="space-y-1">
                  {data.groups.map((group) => (
                    <li key={group.id}>
                      <button
                        type="button"
                        onClick={() => setFocus(focus === group.id ? null : group.id)}
                        aria-pressed={focus === group.id}
                        className={`w-full flex items-center gap-2 px-2 py-1.5 text-left border transition-colors ${
                          focus === group.id
                            ? "border-foreground bg-foreground/5"
                            : "border-transparent hover:border-foreground/20"
                        }`}
                      >
                        <span
                          aria-hidden="true"
                          className="w-3 h-3 shrink-0"
                          style={{ backgroundColor: GROUP_COLORS[(group.id - 1) % GROUP_COLORS.length] }}
                        />
                        <span className="flex-1 min-w-0 truncate font-mono text-[10px] uppercase tracking-widest">
                          {group.label}
                        </span>
                        <span className="font-mono text-[10px] text-muted-foreground">{group.size}</span>
                      </button>
                    </li>
                  ))}
                </ul>
                <p className="mt-3 font-mono text-[9px] leading-relaxed text-muted-foreground">
                  {t("map.legendHint")}
                </p>
                {focus != null && (
                  <button
                    type="button"
                    onClick={() => setFocus(null)}
                    className="mt-3 w-full py-2 font-mono text-[10px] uppercase tracking-widest border border-foreground/30 hover:border-accent hover:text-accent transition-colors"
                  >
                    {t("map.legendClear")}
                  </button>
                )}
              </div>

              <div className="border-t-2 border-foreground/10 pt-4">
                <div className="flex items-center gap-2 mb-2">
                  <svg width="16" height="16" aria-hidden="true">
                    <circle cx="8" cy="8" r="5" fill="none" stroke="var(--foreground)" strokeWidth="2.5" />
                  </svg>
                  <span className="font-mono text-[10px] uppercase tracking-widest">{t("map.yours")}</span>
                </div>
                <p className="font-mono text-[9px] leading-relaxed text-muted-foreground">
                  {isAuthenticated ? t("map.yoursHint") : t("map.yoursGuest")}
                </p>
              </div>
            </aside>
          </div>
        )}
      </main>

      {selectedRec && (
        <MovieModal
          rec={selectedRec}
          token={token}
          seenWhys={seenWhysRef}
          onClose={() => setSelectedRec(null)}
          // el mapa no sirve picks de una sesión de recomendación, así que no
          // hay recommendation_id contra el que registrar feedback — puntuar
          // sí anda, /profile/rate no lo necesita
          onFeedback={() => undefined}
          readOnly={!token}
          onRate={async (rating, title, tmdbId) => {
            const finalTitle = title ?? selectedRec.title;
            try {
              const response = await fetch(`${API_BASE_URL}/profile/rate`, {
                method: "POST",
                headers: { "Content-Type": "application/json", Authorization: `Bearer ${token}` },
                body: JSON.stringify({
                  title: finalTitle,
                  rating,
                  tmdb_id: title ? tmdbId ?? null : selectedRec.tmdb_id,
                }),
              });
              if (!response.ok) throw new Error();
              const body = await response.json();
              if (body.status === "preserved") {
                toast.info(t("modal.ratePreserved", { n: body.rating }));
                return true;
              }
              toast.success(t("modal.rateSaved", { title: finalTitle }));
              return true;
            } catch {
              toast.error(t("modal.rateError"));
              return false;
            }
          }}
        />
      )}
    </PageTransition>
  );
}
