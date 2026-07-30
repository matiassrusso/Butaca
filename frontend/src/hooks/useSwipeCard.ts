import { useRef } from "react";

const SWIPE_THRESHOLD = 100; // px de arrastre para que cuente como swipe, no un click accidental
const FLY_OUT_DISTANCE = 600;

// arrastre horizontal estilo Tinder, imperativo (escribe directo al DOM vía
// ref, mismo patrón que useTiltCard) para que el poster siga al dedo/mouse
// sin esperar un re-render de React en cada pointermove
export function useSwipeCard(onSwipeRight: () => void, onSwipeLeft: () => void) {
  const cardRef = useRef<HTMLDivElement>(null);
  const startXRef = useRef<number | null>(null);

  function setTransform(dx: number, withTransition: boolean) {
    const el = cardRef.current;
    if (!el) return;
    el.style.transition = withTransition ? "transform 0.25s ease, opacity 0.25s ease" : "";
    el.style.transform = `translateX(${dx}px) rotate(${dx / 20}deg)`;
    el.style.opacity = String(Math.max(1 - Math.abs(dx) / 400, 0.3));
  }

  function onPointerDown(e: React.PointerEvent<HTMLDivElement>) {
    e.currentTarget.setPointerCapture(e.pointerId);
    startXRef.current = e.clientX;
  }

  function onPointerMove(e: React.PointerEvent<HTMLDivElement>) {
    if (startXRef.current === null) return;
    setTransform(e.clientX - startXRef.current, false);
  }

  function onPointerUp(e: React.PointerEvent<HTMLDivElement>) {
    if (startXRef.current === null) return;
    const dx = e.clientX - startXRef.current;
    startXRef.current = null;

    if (dx > SWIPE_THRESHOLD) {
      setTransform(FLY_OUT_DISTANCE, true);
      onSwipeRight();
    } else if (dx < -SWIPE_THRESHOLD) {
      setTransform(-FLY_OUT_DISTANCE, true);
      onSwipeLeft();
    } else {
      setTransform(0, true);
    }
  }

  return { cardRef, onPointerDown, onPointerMove, onPointerUp };
}
