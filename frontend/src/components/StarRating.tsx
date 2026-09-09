import { useRef, useState } from "react";

import { useLang } from "@/lib/i18n";

// clave del diccionario por rating; el texto lo resuelve t() en el componente
const LABEL_KEYS: Record<number, string> = {
  0.5: "modal.star0_5",
  1: "modal.star1",
  1.5: "modal.star1_5",
  2: "modal.star2",
  2.5: "modal.star2_5",
  3: "modal.star3",
  3.5: "modal.star3_5",
  4: "modal.star4",
  4.5: "modal.star4_5",
  5: "modal.star5",
};

const SIZES = {
  sm: "size-7",
  md: "size-9",
  lg: "size-11",
};

// px reales detrás de cada clase de arriba (Tailwind size-N = N*4px) -- hace
// falta el número para calcular cuánto agrandar el hit-target invisible
const SIZE_PX: Record<keyof typeof SIZES, number> = { sm: 28, md: 36, lg: 44 };

// mínimo táctil recomendado (Apple HIG / Material Design). El ícono visual
// puede quedar chico -- lo que tiene que medir esto es la ZONA DE TOQUE
// (reporte de Matías: en el celular las mitades de estrella son
// imposibles de acertar, miden 14-22px de ancho reales).
const MIN_TAP = 44;

const STAR_PATH = "M50 4 61 36 95 36 68 56 79 90 50 70 21 90 32 56 5 36 39 36Z";

function formatRating(value: number): string {
  return Number.isInteger(value) ? String(value) : `${Math.floor(value)}½`;
}

export function StarRating({
  value,
  onChange,
  disabled = false,
  size = "md",
  showLabel = true,
  label,
}: {
  value?: number | null;
  onChange: (rating: number) => void;
  disabled?: boolean;
  size?: keyof typeof SIZES;
  showLabel?: boolean;
  label?: string;
}) {
  const { t } = useLang();
  const [preview, setPreview] = useState<number | null>(null);
  // en touch no hay hover -- así que hoy el primer tap ya manda el request,
  // sin ningún paso para corregir un dedo que erró el target (reporte de
  // Matías: "difícil... cambiar de puntuación"). Con puntero coarse, el tap
  // arma PREVIEW nomás; recién un 2do tap en la MISMA estrella confirma y
  // llama a onChange. En mouse/teclado el hover ya cumple ese rol de
  // preview, así que ahí se sigue confirmando al primer click, como siempre.
  const [pendingTap, setPendingTap] = useState<number | null>(null);
  const [isCoarsePointer] = useState(
    () => typeof window !== "undefined" && (window.matchMedia?.("(hover: none)").matches ?? false),
  );
  const shown = preview ?? value ?? 0;

  function activate(rating: number) {
    if (isCoarsePointer) {
      if (pendingTap === rating) {
        setPendingTap(null);
        onChange(rating);
      } else {
        setPendingTap(rating);
        setPreview(rating);
      }
      return;
    }
    onChange(rating);
  }

  // En touch, acertar la mitad de una estrella (franja de ~14-22px en el
  // centro) con el dedo es imposible. En vez de tap ciego, la fila entera es
  // una pista deslizable: tocás y arrastrás, el relleno sigue el dedo en vivo
  // (snap a 0.5) y al soltar confirma. La precisión sale del arrastre con
  // feedback, no de pegarle a un target sub-dedo.
  const rowRef = useRef<HTMLDivElement>(null);
  const [dragging, setDragging] = useState(false);

  function ratingFromClientX(clientX: number): number {
    const el = rowRef.current;
    if (!el) return 0.5;
    const { left, width } = el.getBoundingClientRect();
    const ratio = Math.min(1, Math.max(0, (clientX - left) / width));
    // ceil, no round: cubrir la mitad derecha de una estrella la llena ENTERA
    // (igual que los botones por mitad y el relleno visual). Con round, el
    // centro de una estrella daba .5 y el entero solo salía pegándole al borde
    // exacto entre dos estrellas -> casi siempre medios puntos.
    return Math.min(5, Math.max(0.5, Math.ceil(ratio * 10) / 2)); // 0.5..5 en pasos de 0.5
  }

  function onDragStart(e: React.PointerEvent) {
    if (disabled) return;
    e.currentTarget.setPointerCapture(e.pointerId);
    setDragging(true);
    setPendingTap(null);
    setPreview(ratingFromClientX(e.clientX));
  }
  function onDragMove(e: React.PointerEvent) {
    if (!dragging) return;
    setPreview(ratingFromClientX(e.clientX));
  }
  function onDragEnd(e: React.PointerEvent) {
    if (!dragging) return;
    const rating = ratingFromClientX(e.clientX);
    setDragging(false);
    setPreview(null);
    onChange(rating);
  }

  const starPx = SIZE_PX[size];
  // cuánto crece el botón invisible más allá del ícono dibujado: vertical
  // repartido arriba/abajo, horizontal solo hacia el borde EXTERNO de cada
  // mitad (el borde interno queda fijo en el centro para no correr el
  // límite entre "media estrella" y "estrella entera"). Puede pisar la zona
  // del vecino -- a propósito, un target grande con overlap es preferible a
  // uno angosto e inalcanzable.
  const vPad = Math.max(0, (MIN_TAP - starPx) / 2);
  const hPad = Math.max(0, MIN_TAP - starPx / 2);

  return (
    <div className="text-center" onMouseLeave={() => setPreview(null)}>
      <div className="relative inline-block">
      <div
        ref={rowRef}
        role="radiogroup"
        aria-label={label ?? t("modal.yourRating")}
        className={`inline-flex items-center justify-center ${disabled ? "opacity-50" : ""}`}
      >
        {[0, 1, 2, 3, 4].map((index) => {
          const fill = Math.max(0, Math.min(1, shown - index));
          return (
            <span key={index} className={`relative block ${SIZES[size]}`}>
              <svg viewBox="0 0 100 100" aria-hidden="true" className="absolute inset-0 size-full text-foreground/20">
                <path d={STAR_PATH} fill="currentColor" />
              </svg>
              <svg
                viewBox="0 0 100 100"
                aria-hidden="true"
                className="pointer-events-none absolute inset-0 size-full text-accent"
                style={{ clipPath: `inset(0 ${100 - fill * 100}% 0 0)` }}
              >
                <path d={STAR_PATH} fill="currentColor" />
              </svg>
              {[0.5, 1].map((half) => {
                const rating = index + half;
                const isLeft = half === 0.5;
                return (
                  <button
                    key={half}
                    type="button"
                    role="radio"
                    aria-checked={value === rating}
                    aria-label={t("modal.starsAria", {
                      n: formatRating(rating),
                      label: t(LABEL_KEYS[rating]),
                    })}
                    title={t("modal.starsTitle", {
                      n: formatRating(rating),
                      label: t(LABEL_KEYS[rating]),
                    })}
                    disabled={disabled}
                    onMouseEnter={() => setPreview(rating)}
                    onFocus={() => setPreview(rating)}
                    onBlur={() => setPreview(null)}
                    onClick={() => activate(rating)}
                    style={{
                      top: -vPad,
                      bottom: -vPad,
                      left: isLeft ? -hPad : "50%",
                      right: isLeft ? "50%" : -hPad,
                    }}
                    className="absolute z-10 focus-visible:outline focus-visible:outline-2 focus-visible:outline-accent"
                  />
                );
              })}
            </span>
          );
        })}
      </div>
        {/* touch: capa deslizable sobre las estrellas (arriba de los botones
            por mitad, que quedan solo para mouse/teclado/lector) */}
        {isCoarsePointer && !disabled && (
          <div
            className="absolute inset-0 z-20 cursor-grab active:cursor-grabbing"
            style={{ touchAction: "none" }}
            onPointerDown={onDragStart}
            onPointerMove={onDragMove}
            onPointerUp={onDragEnd}
            onPointerCancel={onDragEnd}
          />
        )}
      </div>
      {showLabel && (
        <div className="mt-1 min-h-4 font-mono text-[9px] uppercase tracking-wider text-muted-foreground">
          {pendingTap !== null
            ? t("modal.tapToConfirm", { n: formatRating(pendingTap), label: t(LABEL_KEYS[pendingTap]) })
            : shown
              ? t("modal.starsTitle", { n: formatRating(shown), label: t(LABEL_KEYS[shown]) })
              : t("modal.pickRating")}
        </div>
      )}
    </div>
  );
}
