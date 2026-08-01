import { useState } from "react";

const LABELS: Record<number, string> = {
  0.5: "No te gustó nada",
  1: "Muy mala",
  1.5: "Mala",
  2: "Floja",
  2.5: "Regular",
  3: "Te gustó",
  3.5: "Te gustó bastante",
  4: "Te gustó mucho",
  4.5: "Te encantó",
  5: "Una favorita",
};

const SIZES = {
  sm: "size-7",
  md: "size-9",
  lg: "size-11",
};

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
  label = "Tu rating",
}: {
  value?: number | null;
  onChange: (rating: number) => void;
  disabled?: boolean;
  size?: keyof typeof SIZES;
  showLabel?: boolean;
  label?: string;
}) {
  const [preview, setPreview] = useState<number | null>(null);
  const shown = preview ?? value ?? 0;

  return (
    <div className="text-center" onMouseLeave={() => setPreview(null)}>
      <div
        role="radiogroup"
        aria-label={label}
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
                return (
                  <button
                    key={half}
                    type="button"
                    role="radio"
                    aria-checked={value === rating}
                    aria-label={`${formatRating(rating)} estrellas: ${LABELS[rating]}`}
                    title={`${formatRating(rating)} estrellas · ${LABELS[rating]}`}
                    disabled={disabled}
                    onMouseEnter={() => setPreview(rating)}
                    onFocus={() => setPreview(rating)}
                    onBlur={() => setPreview(null)}
                    onClick={() => onChange(rating)}
                    className={`absolute inset-y-0 z-10 focus-visible:outline focus-visible:outline-2 focus-visible:outline-accent ${
                      half === 0.5 ? "left-0 w-1/2" : "right-0 w-1/2"
                    }`}
                  />
                );
              })}
            </span>
          );
        })}
      </div>
      {showLabel && (
        <div className="mt-1 min-h-4 font-mono text-[9px] uppercase tracking-wider text-muted-foreground">
          {shown ? `${formatRating(shown)} estrellas · ${LABELS[shown]}` : "Elegí tu rating"}
        </div>
      )}
    </div>
  );
}
