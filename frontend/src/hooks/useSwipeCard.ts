import { useRef, useState } from "react";

const SWIPE_THRESHOLD = 100; // px de arrastre para que cuente como swipe, no un click accidental
const FLY_OUT_DISTANCE = 600;

export type SwipeDirection = "right" | "left" | "up" | "down";

// arrastre estilo Tinder, imperativo (escribe directo al DOM vía ref, mismo
// patrón que useTiltCard) para que el poster siga al dedo/mouse sin esperar un
// re-render de React en cada pointermove.
//
// El eje dominante decide la dirección; cada pantalla habilita solo los
// handlers que necesita y el resto de los gestos vuelve a su lugar.
export function useSwipeCard(handlers: Partial<Record<SwipeDirection, () => void>>) {
  const cardRef = useRef<HTMLDivElement>(null);
  const startRef = useRef<{ x: number; y: number } | null>(null);
  // solo para el cartel de feedback ("me encantó" / "no la vi") mientras
  // arrastrás — el movimiento del poster NO pasa por acá, va directo al DOM
  const [hint, setHint] = useState<SwipeDirection | null>(null);

  function setTransform(dx: number, dy: number, withTransition: boolean) {
    const el = cardRef.current;
    if (!el) return;
    el.style.transition = withTransition ? "transform 0.25s ease, opacity 0.25s ease" : "";
    // la rotación sale solo del eje horizontal: rotar en un swipe vertical se
    // ve como un glitch, no como un gesto
    el.style.transform = `translate(${dx}px, ${dy}px) rotate(${dx / 20}deg)`;
    el.style.opacity = String(Math.max(1 - Math.max(Math.abs(dx), Math.abs(dy)) / 400, 0.3));
  }

  function directionOf(dx: number, dy: number): SwipeDirection | null {
    const horizontal = Math.abs(dx) > Math.abs(dy);
    if (horizontal) {
      if (dx > SWIPE_THRESHOLD) return "right";
      if (dx < -SWIPE_THRESHOLD) return "left";
      return null;
    }
    if (dy < -SWIPE_THRESHOLD) return "up";
    if (dy > SWIPE_THRESHOLD) return "down";
    return null;
  }

  function onPointerDown(e: React.PointerEvent<HTMLDivElement>) {
    e.currentTarget.setPointerCapture(e.pointerId);
    startRef.current = { x: e.clientX, y: e.clientY };
  }

  function onPointerMove(e: React.PointerEvent<HTMLDivElement>) {
    const start = startRef.current;
    if (!start) return;
    const dx = e.clientX - start.x;
    const dy = e.clientY - start.y;
    setTransform(dx, dy, false);
    const direction = directionOf(dx, dy);
    setHint(direction && handlers[direction] ? direction : null);
  }

  function onPointerUp(e: React.PointerEvent<HTMLDivElement>) {
    const start = startRef.current;
    if (!start) return;
    const dx = e.clientX - start.x;
    const dy = e.clientY - start.y;
    startRef.current = null;
    setHint(null);

    const direction = directionOf(dx, dy);
    if (!direction || !handlers[direction]) {
      setTransform(0, 0, true);
      return;
    }
    const flyOut: Record<SwipeDirection, [number, number]> = {
      right: [FLY_OUT_DISTANCE, 0],
      left: [-FLY_OUT_DISTANCE, 0],
      up: [0, -FLY_OUT_DISTANCE],
      down: [0, FLY_OUT_DISTANCE],
    };
    setTransform(...flyOut[direction], true);
    handlers[direction]?.();
  }

  return { cardRef, hint, onPointerDown, onPointerMove, onPointerUp };
}
