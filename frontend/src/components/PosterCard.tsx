import { Eye, Film, ThumbsDown, ThumbsUp } from "lucide-react";
import type { ReactNode } from "react";

import type { FeedbackStatus, Recommendation } from "@/components/MovieModal";
import { useTiltCard } from "@/hooks/useTiltCard";
import { isUnknownMatch } from "@/lib/match";

// Pedido de Matías (2026-07-31): "la idea es que siempre sea lo mismo no
// importa dónde estés" — el póster interactivo (tilt 3D + glare, badge de
// match, tag de serie, icono de feedback, click para abrir el modal) vive acá
// una sola vez en vez de estar copiado en Home, Recommend e History, que era
// donde se desincronizaban (History ni siquiera era clickeable).
//
// Lo que NO entra acá es el bloque de texto de abajo: cada pantalla pasa el
// suyo como children, porque la densidad de info que tiene sentido en la home
// no es la misma que en la grilla de picks.

export function PosterCard({
  rec,
  onSelect,
  children,
  index = 0,
  feedback,
  showScore = true,
  featured = false,
}: {
  rec: Recommendation;
  onSelect: () => void;
  children: ReactNode;
  // escalona la animación de entrada en una grilla; 0 = sin delay
  index?: number;
  feedback?: FeedbackStatus;
  // false para el visitante sin sesión: sin perfil real detrás, un número
  // sería inventado (mismo criterio que el why del LLM)
  showScore?: boolean;
  // badge grande en círculo (grilla de picks de /recommend) vs chico en
  // esquina (home, archivo)
  featured?: boolean;
}) {
  const { wrapRef, onMouseMove, onMouseLeave } = useTiltCard();
  const poster = rec.poster_path ?? rec.backdrop_path;
  const unknown = isUnknownMatch(rec.match_score);

  return (
    <button
      type="button"
      onClick={onSelect}
      aria-label={`Ver detalle de ${rec.title}`}
      className="animate-reveal text-left group block w-full focus:outline-none focus-visible:ring-2 focus-visible:ring-accent"
      style={{ animationDelay: `${index * 100}ms`, perspective: "1000px" }}
    >
      <div
        ref={wrapRef}
        onMouseMove={onMouseMove}
        onMouseLeave={onMouseLeave}
        className={`${featured ? "mb-6" : "mb-4"} relative transition-transform duration-200 ease-out`}
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

        {showScore &&
          (featured ? (
            <div
              className="absolute -top-3 -right-3 size-16 bg-accent flex items-center justify-center text-accent-foreground font-mono font-bold shadow-2xl shadow-accent/30 ring-1 ring-background/40"
              style={{ transform: "translateZ(40px)" }}
              title={unknown ? "Match desconocido: todavía no hay evidencia real en tu perfil" : undefined}
            >
              {unknown ? (
                <span className="text-xs leading-tight text-center">S/D</span>
              ) : (
                <span className="text-lg">{rec.match_score}%</span>
              )}
            </div>
          ) : (
            <div
              className="absolute top-2 right-2 px-2 py-1 bg-accent text-accent-foreground font-mono text-xs font-bold"
              style={{ transform: "translateZ(40px)" }}
              title={unknown ? "Match desconocido: todavía no hay evidencia real en tu perfil" : undefined}
            >
              {unknown ? "Match desconocido" : `${rec.match_score}% match`}
            </div>
          ))}

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

        {!rec.refined && (
          <span
            className="absolute bottom-3 right-3 font-mono text-[9px] uppercase px-1.5 py-1 bg-background border border-foreground/20 text-muted-foreground"
            title="Elegido por el motor de recomendación, sin pasar por la IA"
          >
            heurístico
          </span>
        )}
      </div>
      {children}
    </button>
  );
}
