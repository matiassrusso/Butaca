import { FormEvent, useRef, useState } from "react";
import { useLocation } from "wouter";

import { PageTransition } from "@/components/PageTransition";
import { useAuth } from "@/hooks/useAuth";

// El backend corre en el free tier de Render, que se duerme tras inactividad:
// la primera request puede tardar ~30-60s en despertar el server. Sin este
// aviso, la espera se ve como si login/registro estuviera roto.
const COLD_START_HINT_MS = 4000;

export default function Login() {
  const { login, register } = useAuth();
  const [, navigate] = useLocation();
  const [mode, setMode] = useState<"login" | "register">("login");
  const [username, setUsername] = useState("");
  const [password, setPassword] = useState("");
  const [loading, setLoading] = useState(false);
  const [slowHint, setSlowHint] = useState(false);
  const [error, setError] = useState("");
  const slowTimer = useRef<ReturnType<typeof setTimeout> | null>(null);

  async function handleSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setLoading(true);
    setError("");
    setSlowHint(false);
    slowTimer.current = setTimeout(() => setSlowHint(true), COLD_START_HINT_MS);

    try {
      if (mode === "login") {
        await login(username, password);
      } else {
        await register(username, password);
      }
      navigate("/recommend");
    } catch (err) {
      setError(err instanceof Error ? err.message : "Falló la autenticación.");
    } finally {
      if (slowTimer.current) clearTimeout(slowTimer.current);
      setLoading(false);
      setSlowHint(false);
    }
  }

  return (
    <PageTransition>
      <main className="grid grid-cols-1 lg:grid-cols-2 min-h-[calc(100vh-4rem)]">
        <div className="bg-foreground text-background p-12 lg:p-16 flex flex-col justify-between gap-16">
          <div className="font-mono text-[10px] uppercase tracking-widest opacity-60">
            [Access · PeliPick]
          </div>
          <div>
            <h1 className="text-6xl md:text-7xl xl:text-8xl font-black uppercase tracking-tighter leading-[0.85] mb-8">
              Volvé a la{" "}
              <span className="text-accent italic font-serif normal-case tracking-normal">función</span>.
            </h1>
            <p className="font-serif italic text-2xl leading-snug opacity-80 max-w-md">
              "Cinema is a matter of what's in the frame and what's out."
            </p>
          </div>
          <div className="font-mono text-[10px] uppercase tracking-widest opacity-40">
            — Martin Scorsese
          </div>
        </div>

        <div className="p-12 lg:p-16 flex items-center">
          <form onSubmit={handleSubmit} className="w-full max-w-sm space-y-8">
            <div>
              <div className="font-mono text-[10px] uppercase tracking-widest text-muted-foreground mb-2">
                {mode === "register" ? "[Registro nuevo]" : "[Volvés]"}
              </div>
              <h2 className="text-3xl font-black uppercase tracking-tighter">
                {mode === "register" ? "Creá tu cuenta" : "Entrá"}
              </h2>
              <p className="text-sm text-muted-foreground mt-2">
                Necesitamos un usuario para guardar tu historial y tus recomendaciones.
              </p>
            </div>

            <div className="space-y-6">
              <label className="block">
                <span className="font-mono text-[10px] uppercase tracking-widest text-muted-foreground">
                  Usuario
                </span>
                <input
                  value={username}
                  onChange={(event) => setUsername(event.target.value)}
                  minLength={3}
                  required
                  className="mt-2 w-full bg-transparent border-b-2 border-foreground py-3 font-mono placeholder:text-muted-foreground focus:outline-none focus:border-accent"
                />
              </label>

              <label className="block">
                <span className="font-mono text-[10px] uppercase tracking-widest text-muted-foreground">
                  Password
                </span>
                <input
                  type="password"
                  value={password}
                  onChange={(event) => setPassword(event.target.value)}
                  minLength={8}
                  required
                  className="mt-2 w-full bg-transparent border-b-2 border-foreground py-3 font-mono focus:outline-none focus:border-accent"
                />
              </label>
            </div>

            <button
              type="submit"
              disabled={loading}
              className="w-full py-4 bg-foreground text-background font-mono text-xs uppercase tracking-widest hover:bg-accent transition-colors disabled:opacity-60"
            >
              {loading ? "..." : mode === "register" ? "Crear cuenta →" : "Entrar →"}
            </button>

            {slowHint && (
              <p className="font-mono text-[10px] uppercase leading-relaxed tracking-widest text-muted-foreground">
                Despertando el servidor... la primera vez puede tardar hasta un minuto.
                Esperá sin recargar.
              </p>
            )}

            <button
              type="button"
              onClick={() => {
                setMode(mode === "login" ? "register" : "login");
                setError("");
              }}
              className="w-full font-mono text-[10px] uppercase tracking-widest text-muted-foreground hover:text-accent transition-colors"
            >
              {mode === "login" ? "¿Primera vez? Registrate" : "¿Ya tenés cuenta? Entrá"}
            </button>

            {error ? (
              <div className="p-4 border-2 border-destructive/50 font-mono text-xs text-destructive">
                {error}
              </div>
            ) : null}
          </form>
        </div>
      </main>
    </PageTransition>
  );
}
