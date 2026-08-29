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
const ZOOM_MOVEMENTS = 1.35;
const ZOOM_TITLES = 2.4;

function fade(value: number, start: number, end: number) {
  return Math.max(0, Math.min(1, (value - start) / (end - start)));
}

export default function VibesMap() {
  const { token, isAuthenticated } = useAuth();
  const { t, lang } = useLang();
  const [data, setData] = useState<MapResponse | null>(null);
  const [failed, setFailed] = useState(false);
  const [focus, setFocus] = useState<number | null>(null);
  const [hovered, setHovered] = useState<MapPoint | null>(null);
  const [selectedRec, setSelectedRec] = useState<Recommendation | null>(null);
  const [loadingVerdict, setLoadingVerdict] = useState<number | null>(null);
  const [kindFilter, setKindFilter] = useState<"all" | "movie" | "series">("all");
  const [query, setQuery] = useState("");
  // zoom/pan libre sobre el encuadre base (el focus de región calcula el base;
  // esto lo multiplica encima). Se resetea al cambiar de región.
  const [userZoom, setUserZoom] = useState(1);
  const [pan, setPan] = useState({ x: 0, y: 0 });
  const [reload, setReload] = useState(0);
  const dragRef = useRef<{ x: number; y: number; panX: number; panY: number } | null>(null);
  const draggedRef = useRef(false);
  const pointersRef = useRef(new Map<number, { x: number; y: number }>());
  const pinchRef = useRef<{ distance: number; zoom: number } | null>(null);
  const svgRef = useRef<SVGSVGElement | null>(null);
  const seenWhysRef = useRef<Map<number, string>>(new Map());

  const q = query.trim().toLowerCase();
  const matchCount =
    q === ""
      ? 0
      : (data?.points.filter(
          (p) => p.title.toLowerCase().includes(q) && (kindFilter === "all" || p.kind === kindFilter),
        ).length ?? 0);
  useEffect(() => {
    // cambiar de región reencuadra: el zoom/pan manual previo ya no aplica
    setUserZoom(1);
    setPan({ x: 0, y: 0 });
  }, [focus]);

  useEffect(() => {
    let cancelled = false;
    setFailed(false);
    fetch(`${API_BASE_URL}/vibes/map`, token ? { headers: { Authorization: `Bearer ${token}` } } : {})
      .then((response) => (response.ok ? response.json() : Promise.reject(new Error())))
      .then((body: MapResponse) => {
        if (!cancelled) {
          setData(body);
          setFailed(false);
        }
      })
      .catch(() => {
        if (!cancelled) setFailed(true);
      });
    return () => {
      cancelled = true;
    };
  }, [token, reload]);

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
    // encuadre base: el lienzo completo, o recortado a la región enfocada
    let bx = 0;
    let by = 0;
    let bw = VIEW_WIDTH;
    let bh = VIEW_HEIGHT;
    const inFocus = focus == null ? [] : placed.filter(({ point }) => point.group_id === focus);
    if (inFocus.length > 0) {
      const margin = 60;
      const minX = Math.min(...inFocus.map((p) => p.cx)) - margin;
      const minY = Math.min(...inFocus.map((p) => p.cy)) - margin;
      const width = Math.max(Math.max(...inFocus.map((p) => p.cx)) + margin - minX, 120);
      // se mantiene la proporción del lienzo: si no, el SVG estira el contenido
      bh = Math.max(
        Math.max(...inFocus.map((p) => p.cy)) + margin - minY,
        (width * VIEW_HEIGHT) / VIEW_WIDTH,
      );
      bw = (bh * VIEW_WIDTH) / VIEW_HEIGHT;
      bx = minX;
      by = minY;
    }
    // zoom/pan manual encima del base (centrado); pan en unidades de viewBox
    const w = bw / userZoom;
    const h = bh / userZoom;
    const x = bx + (bw - w) / 2 + pan.x;
    const y = by + (bh - h) / 2 + pan.y;
    return { viewBox: `${x} ${y} ${w} ${h}`, zoom: VIEW_HEIGHT / h };
  }, [placed, focus, userZoom, pan]);

  // territorios: una mancha translúcida por región (o por movimiento al enfocar)
  // dibujada detrás de los puntos, para que el mapa lea como áreas y no como
  // puntos sueltos en el vacío. Radio = alcance real de los miembros del grupo.
  const territories = useMemo(() => {
    if (placed.length === 0) return [];
    const level: "group_id" | "movement_id" = focus == null ? "group_id" : "movement_id";
    const acc = new Map<number, { x: number; y: number; n: number; group: number; pts: [number, number][] }>();
    for (const { point, cx, cy } of placed) {
      if (focus != null && point.group_id !== focus) continue;
      const id = point[level];
      const cur = acc.get(id) ?? { x: 0, y: 0, n: 0, group: point.group_id, pts: [] };
      cur.x += cx;
      cur.y += cy;
      cur.n += 1;
      cur.pts.push([cx, cy]);
      acc.set(id, cur);
    }
    return [...acc.entries()].map(([id, v]) => {
      const cx = v.x / v.n;
      const cy = v.y / v.n;
      const spread =
        v.pts.reduce((s, [px, py]) => s + Math.hypot(px - cx, py - cy), 0) / v.n;
      return {
        id,
        cx,
        cy,
        r: Math.max(spread * 1.9 + 14, 26),
        color: GROUP_COLORS[(v.group - 1) % GROUP_COLORS.length],
      };
    });
  }, [placed, focus]);

  // Las etiquetas de género se separan entre sí: son pocas y definen la vista
  // alejada. Los movimientos se revelan al hacer zoom, sin saltos bruscos.
  const genreCaptions = useMemo(() => {
    if (placed.length === 0) return [];
    const level = "group_id";
    const source = data?.groups;
    const centers = new Map<number, { x: number; y: number; n: number }>();
    for (const { point, cx, cy } of placed) {
      if (focus != null && point.group_id !== focus) continue;
      const id = point[level as "group_id" | "movement_id"];
      const current = centers.get(id) ?? { x: 0, y: 0, n: 0 };
      centers.set(id, { x: current.x + cx, y: current.y + cy, n: current.n + 1 });
    }
    const laid = [...centers.entries()]
      .sort((a, b) => b[1].n - a[1].n)
      .slice(0, centers.size)
      .map(([id, { x, y, n }]) => ({
        id,
        x: x / n,
        y: y / n,
        label: source?.find((cluster) => cluster.id === id)?.label ?? "",
      }))
      .filter((c) => c.label);

    // anti-colisión: las etiquetas nacen en el centroide del cluster y se
    // pisaban (Matías, 2026-08-20). Se separan empujándolas por el eje de menor
    // penetración — el texto es ancho y horizontal, así que casi siempre las
    // apila en vertical, que es lo legible. Tamaños en unidades de viewBox
    // (constantes en pantalla porque el render divide la tipografía por zoom).
    const lh = 17 / zoom; // alto de línea aprox
    const cw = 4.9 / zoom; // ancho por carácter aprox (mono, 15px)
    for (let iter = 0; iter < 80; iter++) {
      let moved = false;
      for (let i = 0; i < laid.length; i++) {
        for (let j = i + 1; j < laid.length; j++) {
          const a = laid[i];
          const b = laid[j];
          const minDx = (a.label.length * cw + b.label.length * cw) / 2 + 6 / zoom;
          const minDy = lh;
          const dx = b.x - a.x;
          const dy = b.y - a.y;
          const penX = minDx - Math.abs(dx);
          const penY = minDy - Math.abs(dy);
          if (penX <= 0 || penY <= 0) continue; // no se tocan
          moved = true;
          if (penY <= penX) {
            const push = (penY / 2 + 0.5) * (dy >= 0 ? 1 : -1);
            a.y -= push;
            b.y += push;
          } else {
            const push = (penX / 2 + 0.5) * (dx >= 0 ? 1 : -1);
            a.x -= push;
            b.x += push;
          }
        }
      }
      if (!moved) break;
    }
    return laid;
  }, [placed, focus, data, zoom]);

  const movementCaptions = useMemo(() => {
    if (!data) return [];
    const centers = new Map<number, { x: number; y: number; n: number }>();
    for (const { point, cx, cy } of placed) {
      if (focus != null && point.group_id !== focus) continue;
      const current = centers.get(point.movement_id) ?? { x: 0, y: 0, n: 0 };
      centers.set(point.movement_id, { x: current.x + cx, y: current.y + cy, n: current.n + 1 });
    }
    return [...centers.entries()]
      .sort((a, b) => b[1].n - a[1].n)
      .map(([id, center]) => ({
        id,
        x: center.x / center.n,
        y: center.y / center.n,
        label: data.movements.find((movement) => movement.id === id)?.label ?? "",
      }))
      .filter((caption) => caption.label);
  }, [data, placed, focus]);

  const movementOpacity = fade(zoom, ZOOM_MOVEMENTS, ZOOM_TITLES);
  const titleOpacity = fade(zoom, ZOOM_TITLES, ZOOM_TITLES + 1);
  const genreOpacity = 1 - fade(zoom, ZOOM_MOVEMENTS, ZOOM_TITLES);

  // zoom con rueda: listener nativo non-passive para poder frenar el scroll de
  // la página mientras se hace zoom sobre el mapa (React lo pone passive).
  useEffect(() => {
    const svg = svgRef.current;
    if (!svg) return;
    const onWheel = (e: WheelEvent) => {
      e.preventDefault();
      const factor = e.deltaY < 0 ? 1.15 : 1 / 1.15;
      setUserZoom((z) => Math.min(8, Math.max(1, z * factor)));
    };
    svg.addEventListener("wheel", onWheel, { passive: false });
    return () => svg.removeEventListener("wheel", onWheel);
  }, [data]);

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
      <main id="main-content" className="max-w-7xl mx-auto px-6 pt-16 pb-24">
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
                [new Intl.NumberFormat(lang === "en" ? "en-US" : "es-AR").format(data.points.length), t("map.statTitles")],
                [String(data.movements.length), t("map.statMovements")],
                [String(data.groups.length), t("map.statGenres")],
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
          <div className="flex items-center gap-3 font-mono text-xs text-muted-foreground">
            <p>{t("map.error")}</p>
            <button type="button" onClick={() => setReload((n) => n + 1)} className="border-2 border-foreground px-2 py-1 uppercase hover:border-accent hover:text-accent">
              {t("common.retry")}
            </button>
          </div>
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
            <div className="relative border-2 border-foreground bg-secondary/30 overflow-hidden">
              <svg
                ref={svgRef}
                viewBox={viewBox}
                className="w-full h-auto block touch-none transition-[view-box] duration-300 select-none"
                style={{ cursor: dragRef.current ? "grabbing" : "grab" }}
                role="img"
                aria-label={t("map.titleAccent")}
                onPointerDown={(e) => {
                  e.currentTarget.setPointerCapture(e.pointerId);
                  pointersRef.current.set(e.pointerId, { x: e.clientX, y: e.clientY });
                  const pointers = [...pointersRef.current.values()];
                  if (pointers.length === 2) {
                    pinchRef.current = { distance: Math.hypot(pointers[0].x - pointers[1].x, pointers[0].y - pointers[1].y), zoom: userZoom };
                    return;
                  }
                  dragRef.current = { x: e.clientX, y: e.clientY, panX: pan.x, panY: pan.y };
                  draggedRef.current = false;
                }}
                onPointerMove={(e) => {
                  if (pointersRef.current.has(e.pointerId)) pointersRef.current.set(e.pointerId, { x: e.clientX, y: e.clientY });
                  const pointers = [...pointersRef.current.values()];
                  if (pointers.length === 2 && pinchRef.current) {
                    const distance = Math.hypot(pointers[0].x - pointers[1].x, pointers[0].y - pointers[1].y);
                    setUserZoom(Math.min(8, Math.max(1, pinchRef.current.zoom * (distance / pinchRef.current.distance))));
                    return;
                  }
                  if (!dragRef.current || !svgRef.current) return;
                  const rect = svgRef.current.getBoundingClientRect();
                  const unitPerPx = VIEW_WIDTH / zoom / rect.width;
                  if (Math.abs(e.clientX - dragRef.current.x) + Math.abs(e.clientY - dragRef.current.y) > 3) {
                    draggedRef.current = true;
                  }
                  setPan({
                    x: dragRef.current.panX - (e.clientX - dragRef.current.x) * unitPerPx,
                    y: dragRef.current.panY - (e.clientY - dragRef.current.y) * unitPerPx,
                  });
                }}
                onPointerUp={(e) => {
                  pointersRef.current.delete(e.pointerId);
                  if (pointersRef.current.size < 2) pinchRef.current = null;
                  dragRef.current = null;
                }}
                onPointerCancel={(e) => {
                  pointersRef.current.delete(e.pointerId);
                  if (pointersRef.current.size < 2) pinchRef.current = null;
                  dragRef.current = null;
                }}
                onPointerLeave={(e) => {
                  pointersRef.current.delete(e.pointerId);
                  if (pointersRef.current.size < 2) pinchRef.current = null;
                  dragRef.current = null;
                  setHovered(null);
                }}
              >
                <defs>
                  <filter id="vibeBlur" x="-40%" y="-40%" width="180%" height="180%">
                    <feGaussianBlur stdDeviation={9 / zoom} />
                  </filter>
                  <pattern id="vibeGrid" width="26" height="26" patternUnits="userSpaceOnUse">
                    <circle cx="1.2" cy="1.2" r="1.1" fill="var(--foreground)" opacity="0.07" />
                  </pattern>
                </defs>

                {/* grilla sutil de fondo, para que no sea un vacío plano */}
                <rect x="-6000" y="-6000" width="12000" height="12000" fill="url(#vibeGrid)" />

                {/* territorios: manchas translúcidas por región (o por movimiento al
                    enfocar), difuminadas, detrás de los puntos */}
                <g filter="url(#vibeBlur)" className="pointer-events-none">
                  {territories.map((terr) => (
                    <circle
                      key={`terr-${terr.id}`}
                      cx={terr.cx}
                      cy={terr.cy}
                      r={terr.r}
                      fill={terr.color}
                      opacity={focus == null ? 0.17 : 0.09}
                    />
                  ))}
                </g>

                {placed.map(({ point, cx, cy }) => {
                  const matchKind = kindFilter === "all" || point.kind === kindFilter;
                  const matchQuery = q === "" || point.title.toLowerCase().includes(q);
                  const off = (focus != null && point.group_id !== focus) || !matchKind || !matchQuery;
                  const hit = q !== "" && matchQuery && matchKind;
                  const color = GROUP_COLORS[(point.group_id - 1) % GROUP_COLORS.length];
                  const r = (point.rated ? 7 : hit ? 6 : 4.5) / zoom;
                  const visibility = Math.max(0.32, titleOpacity, hit ? 0.55 : 0);
                  const shared = {
                    fill: point.rated ? "none" : hit ? "var(--accent)" : color,
                    stroke: point.rated ? color : hit ? "var(--accent)" : "none",
                    strokeWidth: (point.rated ? 2.5 : hit ? 2 : 0) / zoom,
                    opacity: visibility * (off ? 0.06 : point.rated || hit ? 1 : 0.75),
                    className: "cursor-pointer transition-[opacity] duration-200",
                    style: { pointerEvents: visibility > 0.05 ? "auto" : "none" },
                    onMouseEnter: () => setHovered(point),
                    onMouseLeave: () => setHovered(null),
                    onClick: () => {
                      if (!draggedRef.current) openPoint(point);
                    },
                    role: "button",
                    tabIndex: 0,
                    "aria-label": `${point.title} (${point.year})`,
                    onKeyDown: (event: React.KeyboardEvent<SVGCircleElement | SVGRectElement>) => {
                      if (event.key === "Enter" || event.key === " ") {
                        event.preventDefault();
                        openPoint(point);
                      }
                    },
                  } as const;
                  // series = cuadrado, pelis = círculo (Matías, 2026-08-20: había
                  // que poder distinguirlas de un vistazo)
                  return point.kind === "series" ? (
                    <rect
                      key={`${point.kind}-${point.tmdb_id}`}
                      x={cx - r}
                      y={cy - r}
                      width={r * 2}
                      height={r * 2}
                      {...shared}
                    >
                      <title>{`${point.title} (${point.year})`}</title>
                    </rect>
                  ) : (
                    <circle key={`${point.kind}-${point.tmdb_id}`} cx={cx} cy={cy} r={r} {...shared}>
                      <title>{`${point.title} (${point.year})`}</title>
                    </circle>
                  );
                })}

                {genreCaptions.map((caption) => (
                  <text
                    key={caption.id}
                    x={caption.x}
                    y={caption.y}
                    textAnchor="middle"
                    className="pointer-events-none uppercase"
                    style={{
                      fontFamily: "var(--font-mono)",
                      fontSize: (18 - 6 * (1 - genreOpacity)) / zoom,
                      letterSpacing: "0.12em",
                      fill: "var(--foreground)",
                      opacity: genreOpacity,
                      paintOrder: "stroke",
                      stroke: "var(--background)",
                      strokeWidth: 4 / zoom,
                      strokeLinejoin: "round",
                    }}
                  >
                    {caption.label}
                  </text>
                ))}
                {movementCaptions.map((caption) => (
                  <text
                    key={`movement-${caption.id}`}
                    x={caption.x}
                    y={caption.y}
                    textAnchor="middle"
                    className="pointer-events-none uppercase"
                    style={{
                      fontFamily: "var(--font-mono)",
                      fontSize: 11 / zoom,
                      letterSpacing: "0.08em",
                      fill: "var(--foreground)",
                      opacity: movementOpacity,
                      paintOrder: "stroke",
                      stroke: "var(--background)",
                      strokeWidth: 3 / zoom,
                      strokeLinejoin: "round",
                    }}
                  >
                    {caption.label}
                  </text>
                ))}
              </svg>

              <div className="absolute top-3 right-3 flex gap-1">
                <button type="button" onClick={() => setUserZoom((z) => Math.min(8, z * 1.25))} aria-label={t("map.zoomIn")} className="size-7 border-2 border-foreground bg-background font-mono hover:border-accent hover:text-accent">+</button>
                <button type="button" onClick={() => setUserZoom((z) => Math.max(1, z / 1.25))} aria-label={t("map.zoomOut")} className="size-7 border-2 border-foreground bg-background font-mono hover:border-accent hover:text-accent">−</button>
              </div>

              {(userZoom !== 1 || pan.x !== 0 || pan.y !== 0) && (
                <button
                  type="button"
                  onClick={() => {
                    setUserZoom(1);
                    setPan({ x: 0, y: 0 });
                  }}
                  className="absolute top-12 right-3 px-2 py-1 font-mono text-[9px] uppercase tracking-widest border-2 border-foreground bg-background hover:text-accent hover:border-accent transition-colors"
                >
                  {t("map.resetView")}
                </button>
              )}
              <div className="absolute top-3 left-3 pointer-events-none font-mono text-[9px] uppercase tracking-widest text-muted-foreground/70">
                {t("map.zoomHint")}
              </div>

              {hovered && (
                <div className="pointer-events-none absolute left-3 bottom-3 max-w-[90%] flex items-center gap-3 border-2 border-foreground bg-background px-3 py-2">
                  {hovered.poster_path && (
                    <img src={hovered.poster_path} alt="" width={32} height={48} loading="lazy" className="w-8 aspect-[2/3] object-cover" />
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
                <input
                  name="map-search"
                  autoComplete="off"
                  aria-label={t("map.search")}
                  value={query}
                  onChange={(e) => setQuery(e.target.value)}
                  placeholder={t("map.search")}
                  className="w-full px-3 py-2 bg-background border-2 border-foreground/30 focus:border-accent outline-none font-mono text-xs"
                />
                {q !== "" && (
                  <p className="mt-1.5 font-mono text-[9px] uppercase tracking-widest text-muted-foreground">
                    {matchCount > 0 ? t("map.searchCount", { n: matchCount }) : t("map.searchNone")}
                  </p>
                )}
              </div>

              <div>
                <div className="font-mono text-[10px] uppercase tracking-widest text-muted-foreground mb-2">
                  {t("map.shapeLegend")}
                </div>
                <div className="flex gap-1">
                  {(["all", "movie", "series"] as const).map((k) => (
                    <button
                      key={k}
                      type="button"
                      onClick={() => setKindFilter(k)}
                      aria-pressed={kindFilter === k}
                      className={`flex-1 py-1.5 font-mono text-[9px] uppercase tracking-widest border-2 transition-colors ${
                        kindFilter === k
                          ? "border-foreground bg-foreground/5"
                          : "border-foreground/20 hover:border-foreground/40"
                      }`}
                    >
                      {t(k === "all" ? "map.filterAll" : k === "movie" ? "map.filterMovies" : "map.filterSeries")}
                    </button>
                  ))}
                </div>
                <div className="mt-3 flex items-center gap-4 font-mono text-[9px] uppercase tracking-widest text-muted-foreground">
                  <span className="flex items-center gap-1.5">
                    <svg width="12" height="12" aria-hidden="true">
                      <circle cx="6" cy="6" r="4" fill="var(--foreground)" />
                    </svg>
                    {t("map.shapeMovie")}
                  </span>
                  <span className="flex items-center gap-1.5">
                    <svg width="12" height="12" aria-hidden="true">
                      <rect x="2" y="2" width="8" height="8" fill="var(--foreground)" />
                    </svg>
                    {t("map.shapeSeries")}
                  </span>
                </div>
              </div>

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
          onRate={async (rating, title, tmdbId, review) => {
            const finalTitle = title ?? selectedRec.title;
            try {
              const response = await fetch(`${API_BASE_URL}/profile/rate`, {
                method: "POST",
                headers: { "Content-Type": "application/json", Authorization: `Bearer ${token}` },
                body: JSON.stringify({
                  title: finalTitle,
                  rating,
                  tmdb_id: title ? tmdbId ?? null : selectedRec.tmdb_id,
                  kind: selectedRec.kind,
                  review,
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
