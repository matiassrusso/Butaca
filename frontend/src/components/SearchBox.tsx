import { Film, Loader2, Search, X } from "lucide-react";
import { useEffect, useRef, useState } from "react";
import { toast } from "sonner";

import { MovieModal, type Recommendation } from "@/components/MovieModal";
import { API_BASE_URL, useAuth } from "@/hooks/useAuth";

// Pedido de Matías (2026-07-31): "un buscador arriba a la derecha, para que el
// usuario pueda buscar CUALQUIER película o serie, y que Butaca le calcule la
// probabilidad de que le guste, y que la IA le diga qué opina de esa película
// para él".
//
// El veredicto sale de GET /titles/{id}/verdict, que corre exactamente la misma
// tubería que /weekly — así el número y el tono son los mismos que ve en la
// home y en /recommend, no un cálculo aparte.

type SearchResult = {
  tmdb_id: number | null;
  title: string;
  year: number;
  kind: string;
  poster_path: string | null;
};

const DEBOUNCE_MS = 300;

export function SearchBox() {
  const { token } = useAuth();
  const [query, setQuery] = useState("");
  const [results, setResults] = useState<SearchResult[]>([]);
  const [open, setOpen] = useState(false);
  const [searching, setSearching] = useState(false);
  const [verdictFor, setVerdictFor] = useState<number | null>(null);
  const [selectedRec, setSelectedRec] = useState<Recommendation | null>(null);
  const boxRef = useRef<HTMLDivElement>(null);
  const seenWhysRef = useRef<Map<number, string>>(new Map());

  // cerrar con click afuera / Escape — mismo patrón que el dropdown del avatar.
  // Mientras el modal está abierto NO se cierra: el modal es un portal fuera de
  // boxRef, así que cualquier click adentro (votar, por ejemplo) contaría como
  // "click afuera" y mataría la lista de resultados que queremos conservar.
  useEffect(() => {
    if (!open || selectedRec) return;
    function onDown(e: MouseEvent) {
      if (boxRef.current && !boxRef.current.contains(e.target as Node)) setOpen(false);
    }
    function onKey(e: KeyboardEvent) {
      if (e.key === "Escape") setOpen(false);
    }
    document.addEventListener("mousedown", onDown);
    document.addEventListener("keydown", onKey);
    return () => {
      document.removeEventListener("mousedown", onDown);
      document.removeEventListener("keydown", onKey);
    };
  }, [open, selectedRec]);

  useEffect(() => {
    const trimmed = query.trim();
    if (trimmed.length < 2 || !token) {
      setResults([]);
      setSearching(false);
      return;
    }

    let cancelled = false;
    setSearching(true);
    // debounce: sin esto sale un request por tecla y TMDb devuelve resultados
    // de una query vieja después de una nueva
    const timer = setTimeout(() => {
      fetch(`${API_BASE_URL}/titles/search?q=${encodeURIComponent(trimmed)}`, {
        headers: { Authorization: `Bearer ${token}` },
      })
        .then((response) => (response.ok ? response.json() : null))
        .then((body: { titles: SearchResult[] } | null) => {
          if (cancelled) return;
          setResults(body?.titles ?? []);
          setOpen(true);
        })
        .catch(() => {
          if (!cancelled) setResults([]);
        })
        .finally(() => {
          if (!cancelled) setSearching(false);
        });
    }, DEBOUNCE_MS);

    return () => {
      cancelled = true;
      clearTimeout(timer);
    };
  }, [query, token]);

  async function openVerdict(item: SearchResult) {
    if (item.tmdb_id == null || !token) return;
    setVerdictFor(item.tmdb_id);
    try {
      const response = await fetch(
        `${API_BASE_URL}/titles/${item.tmdb_id}/verdict?kind=${encodeURIComponent(item.kind)}`,
        { headers: { Authorization: `Bearer ${token}` } },
      );
      if (!response.ok) throw new Error();
      const rec: Omit<Recommendation, "id"> & { id: number | null } = await response.json();
      // sin sesión persistida detrás no hay id real — -1, igual que /weekly
      setSelectedRec({ ...rec, id: rec.id ?? -1 });
      // la búsqueda queda como está a propósito (pedido de Matías,
      // 2026-07-31): antes se borraba al abrir un resultado, así que puntuar
      // cinco de Spider-Man obligaba a re-escribir "spiderman" cinco veces.
      // Se limpia con la X o vaciando el input, no sola.
    } catch {
      toast.error("No pude analizar ese título.");
    } finally {
      setVerdictFor(null);
    }
  }

  return (
    <>
      <div ref={boxRef} className="relative hidden sm:block">
        <div className="flex items-center gap-2 px-3 py-2 border border-foreground/20 focus-within:border-accent transition-colors">
          <Search className="w-3.5 h-3.5 text-muted-foreground shrink-0" />
          <input
            value={query}
            onChange={(e) => setQuery(e.target.value)}
            onFocus={() => results.length > 0 && setOpen(true)}
            placeholder="Buscar peli o serie…"
            aria-label="Buscar cualquier película o serie"
            className="w-40 lg:w-56 bg-transparent font-mono text-[10px] uppercase tracking-widest placeholder:text-muted-foreground focus:outline-none"
          />
          {searching && <Loader2 className="w-3.5 h-3.5 animate-spin text-accent shrink-0" />}
          {query && !searching && (
            <button
              type="button"
              onClick={() => {
                setQuery("");
                setResults([]);
                setOpen(false);
              }}
              aria-label="Limpiar búsqueda"
              className="shrink-0 text-muted-foreground hover:text-accent transition-colors"
            >
              <X className="w-3.5 h-3.5" />
            </button>
          )}
        </div>

        {open && (
          <div className="absolute right-0 mt-2 w-80 max-h-96 overflow-y-auto border-2 border-foreground bg-background shadow-xl">
            {results.length === 0 ? (
              <p className="px-4 py-3 font-mono text-[10px] uppercase tracking-widest text-muted-foreground">
                Sin resultados
              </p>
            ) : (
              results.map((item) => (
                <button
                  key={`${item.kind}-${item.tmdb_id}`}
                  onClick={() => openVerdict(item)}
                  disabled={verdictFor != null}
                  className="w-full flex items-center gap-3 px-3 py-2 text-left hover:bg-accent/10 disabled:opacity-50 transition-colors"
                >
                  {item.poster_path ? (
                    <img src={item.poster_path} alt="" className="w-8 aspect-[2/3] object-cover shrink-0" />
                  ) : (
                    <div className="w-8 aspect-[2/3] bg-secondary flex items-center justify-center shrink-0">
                      <Film className="w-3 h-3 text-muted-foreground/40" />
                    </div>
                  )}
                  <span className="min-w-0 flex-1">
                    <span className="block text-sm truncate">{item.title}</span>
                    <span className="block font-mono text-[9px] uppercase text-muted-foreground">
                      {item.year}
                      {item.kind === "series" ? " · Serie" : ""}
                    </span>
                  </span>
                  {verdictFor === item.tmdb_id && (
                    <Loader2 className="w-3.5 h-3.5 animate-spin text-accent shrink-0" />
                  )}
                </button>
              ))
            )}
            {verdictFor != null && (
              <p className="px-4 py-2 border-t border-foreground/10 font-mono text-[9px] uppercase tracking-widest text-muted-foreground">
                Calculando qué tanto va con vos…
              </p>
            )}
          </div>
        )}
      </div>

      {selectedRec && (
        <MovieModal
          rec={selectedRec}
          token={token}
          seenWhys={seenWhysRef}
          onClose={() => setSelectedRec(null)}
          // el veredicto del buscador no sale de una sesión persistida, así que
          // no hay recommendation_id contra el que registrar feedback — pero
          // puntuar sí anda, /profile/rate no lo necesita
          onFeedback={() => undefined}
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
              toast.success(`Guardado en tu perfil: ${finalTitle}`);
              return true;
            } catch {
              toast.error("No se pudo guardar el puntaje.");
              return false;
            }
          }}
        />
      )}
    </>
  );
}
