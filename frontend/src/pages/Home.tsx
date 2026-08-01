import { motion, useScroll, useTransform } from "framer-motion";
import { useEffect, useRef, useState } from "react";
import { toast } from "sonner";
import { Link } from "wouter";

import { MovieModal, type FeedbackStatus, type Recommendation } from "@/components/MovieModal";
import { PageTransition } from "@/components/PageTransition";
import { PosterCard } from "@/components/PosterCard";
import { API_BASE_URL, useAuth } from "@/hooks/useAuth";

type RecommendationSession = {
  id: number;
  recommendations: Recommendation[];
};

// /weekly no persiste sesión — id siempre null a diferencia de /history
type RecommendResponse = {
  recommendations: (Omit<Recommendation, "id"> & { id: number | null })[];
};

const STEPS = [
  {
    number: "01",
    title: "Subí tu export de Letterboxd",
    desc: "Settings → Data → Export en Letterboxd. Subí tu ratings.csv o reviews.csv acá.",
  },
  {
    number: "02",
    title: "Leemos tus ratings y reviews",
    desc: "Buscamos patrones de tono, ritmo y sensibilidad en lo que venís premiando o rechazando.",
  },
  {
    number: "03",
    title: "Recibís picks con razón",
    desc: "Cada recomendación viene con una explicación basada en tu propio historial, no en un ranking genérico.",
  },
];

// Ritmo del marquee. Menos segundos = más rápido.
const MARQUEE_SECONDS_PER_NAME = 0.5;

// 50 actores + 15 directores, mezclados a mano para que los directores queden
// repartidos y no en bloque. Curada a propósito y no traída de
// /person/popular de TMDb: esa lista ordena por clics en el sitio de TMDb, no
// por relevancia, y hoy arranca con nombres del cine adulto.
const MARQUEE_NAMES = [
  "Meryl Streep", "Denzel Washington", "Martin Scorsese", "Cate Blanchett", "Tom Hanks",
  "Al Pacino", "Christopher Nolan", "Viola Davis", "Robert De Niro", "Frances McDormand",
  "Leonardo DiCaprio", "Akira Kurosawa", "Nicole Kidman", "Daniel Day-Lewis", "Julianne Moore",
  "Wes Anderson", "Joaquin Phoenix", "Charlize Theron", "Anthony Hopkins", "Tilda Swinton",
  "Stanley Kubrick", "Morgan Freeman", "Kate Winslet", "Brad Pitt", "Bong Joon-ho",
  "Christian Bale", "Emma Thompson", "Samuel L. Jackson", "Judi Dench", "Alfred Hitchcock",
  "Gary Oldman", "Helen Mirren", "Michelle Yeoh", "Greta Gerwig", "Jack Nicholson",
  "Sigourney Weaver", "Harrison Ford", "Ralph Fiennes", "Quentin Tarantino", "Penélope Cruz",
  "Marion Cotillard", "Willem Dafoe", "Guillermo del Toro", "Isabelle Huppert", "Mads Mikkelsen",
  "Ethan Hawke", "Saoirse Ronan", "Steven Spielberg", "Oscar Isaac", "Amy Adams",
  "Ryan Gosling", "Denis Villeneuve", "Toni Collette", "Mahershala Ali", "Rachel Weisz",
  "Javier Bardem", "Sofia Coppola", "Naomi Watts", "Song Kang-ho", "Jessica Chastain",
  "Francis Ford Coppola", "Adam Driver", "Lupita Nyong'o", "Timothée Chalamet", "Pedro Almodóvar",
];

// El póster (tilt, glare, badge, click) sale de PosterCard, compartido con
// /recommend y /history — acá solo va el bloque de texto de abajo.
//
// El "why" NO va acá (pedido de Matías, 2026-07-31): afuera solo póster,
// título, año y match; el veredicto se lee al abrir el detalle, con el
// typewriter. De paso empareja las cards — un why de 2 líneas contra uno de 5
// dejaba la grilla del weekly visiblemente despareja.
function PickText({ rec }: { rec: Recommendation }) {
  return (
    <>
      <h3 className="text-lg font-black uppercase tracking-tighter leading-none mb-1 group-hover:text-accent transition-colors">
        {rec.title}
      </h3>
      <p className="font-mono text-[10px] text-muted-foreground">
        {rec.year}
        {rec.kind === "series" ? " · Serie" : ""}
      </p>
    </>
  );
}

export default function Home() {
  const { isAuthenticated, token } = useAuth();
  const { scrollY } = useScroll();
  const heroY = useTransform(scrollY, [0, 600], [0, -80]);
  const heroOpacity = useTransform(scrollY, [0, 500], [1, 0.3]);
  const [latestSession, setLatestSession] = useState<RecommendationSession | null>(null);
  const [selectedRec, setSelectedRec] = useState<Recommendation | null>(null);
  const [feedbackState, setFeedbackState] = useState<Record<number, FeedbackStatus>>({});
  const [weeklyPicks, setWeeklyPicks] = useState<Recommendation[]>([]);
  // el typewriter del "why" vive en el modal pero su memoria (qué why ya se
  // animó) tiene que sobrevivir a que el modal se desmonte al cerrarlo, así
  // que la ref vive acá — sin esto la home mostraba el texto completo de una,
  // sin animación, a diferencia de /recommend (pedido de Matías: "que siempre
  // sea lo mismo no importa dónde estés")
  const seenWhysRef = useRef<Map<number, string>>(new Map());

  async function submitFeedback(recommendationId: number, status: FeedbackStatus) {
    // los picks semanales no vienen de una sesión persistida (son las
    // mismas 5 pelis para todo el mundo, no un pedido individual), así que
    // no tienen un id real — se les asigna -1 al mapear la respuesta de
    // /weekly, y el feedback no aplica ahí
    if (!token || recommendationId < 0) return;
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

  // pedido de Matías (2026-07-31): "Ya la vi" → elegir cuánto te gustó queda
  // en el perfil real (rated_items) — a diferencia de submitFeedback, esto
  // no depende de un recommendation_id real, así que anda también desde las
  // semanales (id -1, sin fila en recommendations_served). title/tmdbId
  // opcionales: el botón "no estoy de acuerdo" del modal reusa esto para
  // votar películas similares, no rec en sí.
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
        toast.info(`Tu ${body.rating}/5 de Letterboxd tiene prioridad. Cambialo ahí y volvé a importar.`);
        return true;
      }
      toast.success(`Guardado en tu perfil: ${finalTitle}`);
      return true;
    } catch {
      toast.error("No se pudo guardar el puntaje.");
      return false;
    }
  }

  // ?register=1 hace que /login arranque en modo registro (feedback: el CTA
  // "Empezar gratis" caía en "Entrá" y el usuario nuevo tenía que buscar el
  // link chico de abajo).
  const ctaHref = isAuthenticated ? "/recommend" : "/login?register=1";
  const ctaLabel = isAuthenticated ? "Ir a mis recomendaciones" : "Empezar gratis";

  useEffect(() => {
    if (!token) {
      setLatestSession(null);
      return;
    }

    let cancelled = false;
    fetch(`${API_BASE_URL}/history`, { headers: { Authorization: `Bearer ${token}` } })
      .then((response) => (response.ok ? response.json() : null))
      .then((body: { sessions: RecommendationSession[] } | null) => {
        if (!cancelled) setLatestSession(body?.sessions[0] ?? null);
      })
      .catch(() => {
        if (!cancelled) setLatestSession(null);
      });

    return () => {
      cancelled = true;
    };
  }, [token]);

  // pedido de Matías (2026-07-30): 5 recomendaciones semanales, iguales para
  // todos — públicas, no hace falta sesión. Con token, /weekly ADEMÁS
  // personaliza match_score/why contra el historial real del usuario.
  useEffect(() => {
    let cancelled = false;
    fetch(`${API_BASE_URL}/weekly`, token ? { headers: { Authorization: `Bearer ${token}` } } : {})
      .then((response) => (response.ok ? response.json() : null))
      .then((body: RecommendResponse | null) => {
        if (cancelled || !body) return;
        // sin sesión persistida no hay id real — -1 en vez de null para no
        // ensanchar el type Recommendation compartido con /recommend, que
        // sí siempre trae un id válido
        setWeeklyPicks(body.recommendations.map((rec) => ({ ...rec, id: rec.id ?? -1 })));
      })
      .catch(() => {
        if (!cancelled) setWeeklyPicks([]);
      });
    return () => {
      cancelled = true;
    };
  }, [token]);

  const currentPicks = latestSession?.recommendations.slice(0, 3) ?? [];

  return (
    <PageTransition>
      {/* Hero — cinematic, layered */}
      <section className="relative overflow-hidden border-b-2 border-foreground min-h-[92vh] flex items-end pb-16 pt-24">
        <div aria-hidden className="absolute inset-0 -z-10">
          <div className="orb bg-accent size-[42vw] top-[-8vw] left-[-6vw]" />
          <div className="orb bg-foreground/40 dark:bg-accent/50 size-[35vw] bottom-[-10vw] right-[-8vw]" style={{ animationDelay: "-6s" }} />
          <div className="orb bg-accent/40 size-[22vw] top-[30%] right-[20%]" style={{ animationDelay: "-12s" }} />
          <div className="grain-layer" />
        </div>

        <motion.div style={{ y: heroY, opacity: heroOpacity }} className="max-w-7xl mx-auto px-6 w-full">
          <motion.div
            initial={{ opacity: 0, y: 20 }}
            animate={{ opacity: 1, y: 0 }}
            transition={{ duration: 0.6 }}
            className="flex items-center gap-3 mb-10 font-mono text-[10px] uppercase tracking-[0.3em] text-foreground"
          >
            <span className="size-2 bg-accent rounded-full animate-pulse" />
            <span>Basado en tu historial de Letterboxd</span>
          </motion.div>

          <h1 className="text-[15vw] md:text-[11vw] font-black tracking-tighter leading-[0.85] uppercase mb-10">
            {["Pelis que", "te", "conocen."].map((word, i) => (
              <motion.span
                key={word}
                initial={{ opacity: 0, y: 80, rotateX: -60 }}
                animate={{ opacity: 1, y: 0, rotateX: 0 }}
                transition={{ duration: 0.9, delay: 0.1 + i * 0.12, ease: [0.16, 1, 0.3, 1] }}
                className={`inline-block mr-6 origin-bottom ${i === 1 ? "text-accent italic font-serif normal-case tracking-normal" : ""}`}
                style={{ transformStyle: "preserve-3d" }}
              >
                {word}
              </motion.span>
            ))}
          </h1>

          <div className="flex flex-col md:flex-row justify-between items-start md:items-end gap-8">
            <motion.p
              initial={{ opacity: 0 }}
              animate={{ opacity: 1 }}
              transition={{ delay: 0.7 }}
              className="max-w-md font-mono text-xs uppercase leading-relaxed text-muted-foreground"
            >
              [Teoría] Subí tu export de Letterboxd. Leemos tus ratings, tus reviews, tus
              patrones. Después recomendamos con explicaciones basadas en tu gusto real,
              no en un ranking genérico.
            </motion.p>
            <motion.div
              initial={{ opacity: 0, y: 20 }}
              animate={{ opacity: 1, y: 0 }}
              transition={{ delay: 0.9 }}
              className="flex flex-col items-start md:items-end gap-3"
            >
              {!isAuthenticated && (
                <span className="font-mono text-[10px] uppercase text-muted-foreground">
                  Sync con Letterboxd →
                </span>
              )}
              <Link
                href={ctaHref}
                className="group relative overflow-hidden px-10 py-4 bg-foreground text-background font-mono text-xs uppercase tracking-widest transition-transform hover:-translate-y-0.5"
              >
                <span className="relative z-10">{ctaLabel}</span>
                <span className="absolute inset-0 bg-accent translate-y-full group-hover:translate-y-0 transition-transform duration-500" />
                <span className="relative z-10 ml-2 inline-block group-hover:translate-x-1 transition-transform">→</span>
              </Link>
            </motion.div>
          </div>
        </motion.div>
      </section>

      {/* Marquee — directors ticker. Decorativo: los nombres se repiten para el
          loop, así que no aporta nada a un lector de pantalla. */}
      <div
        aria-hidden="true"
        className="border-b-2 border-foreground bg-foreground text-background py-5 overflow-hidden"
      >
        {/* El separador va como padding de cada item, no como gap del contenedor:
            con gap, el ancho total es (2n items + 2n-1 gaps) y el -50% de la
            animación no cae en la costura entre las dos copias — de ahí el
            salto visible cada vuelta. */}
        {/* La duración sale del largo de la lista para que la velocidad no
            cambie si se agregan o sacan nombres — subí o bajá MARQUEE_SECONDS_PER_NAME
            para ajustar el ritmo. */}
        <div
          className="flex whitespace-nowrap animate-marquee font-serif italic text-2xl md:text-3xl"
          style={{ animationDuration: `${MARQUEE_NAMES.length * MARQUEE_SECONDS_PER_NAME}s` }}
        >
          {[...MARQUEE_NAMES, ...MARQUEE_NAMES].map((name, i) => (
            <span key={i} className="flex items-center gap-16 pr-16">
              {name}
              <span className="text-accent">✦</span>
            </span>
          ))}
        </div>
      </div>

      {weeklyPicks.length > 0 && (
        <section className="max-w-7xl mx-auto px-6 py-24 border-b-2 border-foreground">
          <div className="flex items-baseline gap-4 mb-10">
            <span className="font-mono text-xs px-2 py-1 border border-foreground/20">
              [Recomendaciones de la semana]
            </span>
            <div className="h-px flex-grow bg-foreground/10" />
          </div>
          <p className="font-serif italic text-lg text-muted-foreground mb-10 max-w-2xl">
            3 de tendencia esta semana + 2 de otras épocas, todo TMDb real — las mismas para
            todo el mundo —
            {isAuthenticated ? (
              " esto es lo que tu perfil dice sobre cada una."
            ) : (
              <>
                {" "}
                <Link href="/login" className="text-accent underline decoration-dotted hover:text-foreground">
                  Iniciá sesión
                </Link>{" "}
                para ver qué tan bien va cada una con vos.
              </>
            )}
          </p>
          <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-5 gap-6">
            {weeklyPicks.map((rec, i) => (
              <PosterCard
                key={rec.tmdb_id ?? rec.title}
                rec={rec}
                index={i}
                // sin sesión no hay perfil real detrás del "probablemente te
                // guste": mostrar score/why sería un dato inventado (mismo
                // criterio que el why del LLM)
                showScore={isAuthenticated}
                onSelect={() => setSelectedRec(rec)}
              >
                <PickText rec={rec} />
              </PosterCard>
            ))}
          </div>
        </section>
      )}

      {currentPicks.length > 0 && (
        <section className="max-w-7xl mx-auto px-6 py-24 border-b-2 border-foreground">
          <div className="flex items-baseline gap-4 mb-10">
            <span className="font-mono text-xs px-2 py-1 border border-foreground/20">[Current picks]</span>
            <div className="h-px flex-grow bg-foreground/10" />
            <Link
              href="/history"
              className="font-mono text-[10px] uppercase tracking-widest text-muted-foreground hover:text-foreground transition-colors"
            >
              Ver todo →
            </Link>
          </div>
          <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-8">
            {currentPicks.map((rec, i) => (
              <PosterCard key={rec.id} rec={rec} index={i} onSelect={() => setSelectedRec(rec)}>
                <PickText rec={rec} />
              </PosterCard>
            ))}
          </div>
        </section>
      )}

      <div id="how-it-works" className="max-w-7xl mx-auto px-6">
        {/* Methodology */}
        <section className="py-24 grid grid-cols-1 md:grid-cols-12 gap-12">
          <div className="md:col-span-4">
            <motion.h2
              initial={{ opacity: 0, x: -30 }}
              whileInView={{ opacity: 1, x: 0 }}
              viewport={{ once: true }}
              transition={{ duration: 0.6 }}
              className="text-5xl font-black uppercase tracking-tighter mb-4"
            >
              La metodología
            </motion.h2>
            <p className="font-mono text-xs uppercase leading-relaxed text-muted-foreground">
              Detrás de cada elección hay un patrón rastreable en tu historial — nunca un
              ranking global.
            </p>
          </div>
          <div className="md:col-span-8 grid grid-cols-1 md:grid-cols-3 gap-8">
            {STEPS.map((step, i) => (
              <motion.div
                key={step.number}
                initial={{ opacity: 0, y: 30 }}
                whileInView={{ opacity: 1, y: 0 }}
                viewport={{ once: true, margin: "-40px" }}
                transition={{ duration: 0.6, delay: i * 0.15 }}
                className="space-y-4"
              >
                <div className="font-mono text-xl font-bold text-accent">[{step.number}]</div>
                <h4 className="text-sm font-bold uppercase tracking-widest">{step.title}</h4>
                <p className="text-sm leading-relaxed text-foreground/80">{step.desc}</p>
              </motion.div>
            ))}
          </div>
        </section>

        {/* CTA */}
        <section className="py-24 border-t-2 border-foreground text-center">
          <h2 className="text-4xl md:text-6xl font-black uppercase tracking-tighter mb-6">
            ¿Lista tu próxima{" "}
            <span className="text-accent italic font-serif normal-case tracking-normal">peli?</span>
          </h2>
          <p className="font-mono text-xs uppercase text-muted-foreground mb-10 max-w-xl mx-auto">
            Subí tu historial y recibí recomendaciones personalizadas en menos de un minuto.
          </p>
          <Link
            href={ctaHref}
            className="inline-flex items-center gap-2 px-10 py-4 bg-accent text-accent-foreground font-mono text-xs uppercase tracking-widest hover:bg-foreground hover:text-background transition-colors"
          >
            {ctaLabel} →
          </Link>
        </section>
      </div>

      {selectedRec && (
        <MovieModal
          rec={selectedRec}
          token={token}
          feedback={feedbackState[selectedRec.id]}
          seenWhys={seenWhysRef}
          onClose={() => setSelectedRec(null)}
          onFeedback={(status) => submitFeedback(selectedRec.id, status)}
          onRate={(rating, title, tmdbId) => rateTitle(selectedRec, rating, title, tmdbId)}
        />
      )}
    </PageTransition>
  );
}
