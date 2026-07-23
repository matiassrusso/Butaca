import { FormEvent, useRef, useState } from "react";
import { useLocation } from "wouter";

import { PageTransition } from "@/components/PageTransition";
import { API_BASE_URL, useAuth } from "@/hooks/useAuth";
import { PRIMARY_QUOTE } from "@/lib/quotes";

// El backend corre en el free tier de Render, que se duerme tras inactividad:
// la primera request puede tardar ~30-60s en despertar el server. Sin este
// aviso, la espera se ve como si login/registro estuviera roto.
const COLD_START_HINT_MS = 4000;

export default function Login() {
  const { login, register } = useAuth();
  const [, navigate] = useLocation();
  // ?register=1 (CTA "Empezar gratis" del home) abre directo en modo registro.
  const [mode, setMode] = useState<"login" | "register" | "forgot">(() =>
    new URLSearchParams(window.location.search).has("register") ? "register" : "login",
  );
  const [username, setUsername] = useState("");
  const [password, setPassword] = useState("");
  const [email, setEmail] = useState("");
  const [loading, setLoading] = useState(false);
  const [slowHint, setSlowHint] = useState(false);
  const [error, setError] = useState("");
  const [forgotSent, setForgotSent] = useState(false);
  const [fieldErrors, setFieldErrors] = useState<{ username?: string; email?: string; password?: string }>({});
  const slowTimer = useRef<ReturnType<typeof setTimeout> | null>(null);

  function validate(): boolean {
    const errs: typeof fieldErrors = {};
    if (username.trim().length < 3) errs.username = "Mínimo 3 caracteres.";
    if (mode === "register" && !/^[^@\s]+@[^@\s]+\.[^@\s]+$/.test(email))
      errs.email = "Ingresá un email válido.";
    if (mode !== "forgot" && password.length < 8) errs.password = "Mínimo 8 caracteres.";
    setFieldErrors(errs);
    return Object.keys(errs).length === 0;
  }

  async function handleSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (!validate()) return;
    setLoading(true);
    setError("");
    setSlowHint(false);
    slowTimer.current = setTimeout(() => setSlowHint(true), COLD_START_HINT_MS);

    try {
      if (mode === "forgot") {
        await fetch(`${API_BASE_URL}/auth/forgot-password`, {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ username }),
        });
        setForgotSent(true);
        return;
      }
      if (mode === "login") {
        await login(username, password);
      } else {
        await register(username, password, email);
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
            [Access · Butaca]
          </div>
          <div>
            <h1 className="text-6xl md:text-7xl xl:text-8xl font-black uppercase tracking-tighter leading-[0.85] mb-8">
              Volvé a la{" "}
              <span className="text-accent italic font-serif normal-case tracking-normal">función</span>.
            </h1>
            <p className="font-serif italic text-2xl leading-snug opacity-80 max-w-md">
              "{PRIMARY_QUOTE.text}"
            </p>
          </div>
          <div className="font-mono text-[10px] uppercase tracking-widest opacity-40">
            — {PRIMARY_QUOTE.author}
          </div>
        </div>

        <div className="p-12 lg:p-16 flex items-center">
          {mode === "forgot" && forgotSent ? (
            <div className="w-full max-w-sm space-y-8">
              <div>
                <div className="font-mono text-[10px] uppercase tracking-widest text-muted-foreground mb-2">
                  [Recuperación]
                </div>
                <h2 className="text-3xl font-black uppercase tracking-tighter">Listo</h2>
                <p className="text-sm text-muted-foreground mt-2">
                  Si ese usuario existe, le llegó un mail con instrucciones para elegir una
                  nueva contraseña.
                </p>
              </div>
              <button
                type="button"
                onClick={() => {
                  setMode("login");
                  setForgotSent(false);
                }}
                className="w-full font-mono text-[10px] uppercase tracking-widest text-muted-foreground hover:text-accent transition-colors"
              >
                ← Volver a entrar
              </button>
            </div>
          ) : (
            <form onSubmit={handleSubmit} noValidate className="w-full max-w-sm space-y-8">
              <div>
                <div className="font-mono text-[10px] uppercase tracking-widest text-muted-foreground mb-2">
                  {mode === "register" ? "[Registro nuevo]" : mode === "forgot" ? "[Recuperación]" : "[Volvés]"}
                </div>
                <h2 className="text-3xl font-black uppercase tracking-tighter">
                  {mode === "register" ? "Creá tu cuenta" : mode === "forgot" ? "Recuperá tu clave" : "Entrá"}
                </h2>
                <p className="text-sm text-muted-foreground mt-2">
                  {mode === "forgot"
                    ? "Ingresá tu usuario y te mandamos un link para elegir una nueva contraseña."
                    : "Necesitamos un usuario para guardar tu historial y tus recomendaciones."}
                </p>
              </div>

              <div className="space-y-6">
                <label className="block">
                  <span className="font-mono text-[10px] uppercase tracking-widest text-muted-foreground">
                    Usuario
                  </span>
                  <input
                    value={username}
                    onChange={(event) => {
                      setUsername(event.target.value);
                      if (fieldErrors.username) setFieldErrors((e) => ({ ...e, username: undefined }));
                    }}
                    aria-invalid={!!fieldErrors.username}
                    className={`mt-2 w-full bg-transparent border-b-2 py-3 font-mono placeholder:text-muted-foreground focus:outline-none focus:border-accent ${
                      fieldErrors.username ? "border-destructive" : "border-foreground"
                    }`}
                  />
                  {fieldErrors.username && (
                    <span className="mt-2 block font-mono text-[10px] uppercase tracking-widest text-destructive">
                      {fieldErrors.username}
                    </span>
                  )}
                </label>

                {mode === "register" && (
                  <label className="block">
                    <span className="font-mono text-[10px] uppercase tracking-widest text-muted-foreground">
                      Email
                    </span>
                    <input
                      type="email"
                      value={email}
                      onChange={(event) => {
                        setEmail(event.target.value);
                        if (fieldErrors.email) setFieldErrors((e) => ({ ...e, email: undefined }));
                      }}
                      aria-invalid={!!fieldErrors.email}
                      className={`mt-2 w-full bg-transparent border-b-2 py-3 font-mono placeholder:text-muted-foreground focus:outline-none focus:border-accent ${
                        fieldErrors.email ? "border-destructive" : "border-foreground"
                      }`}
                    />
                    {fieldErrors.email && (
                      <span className="mt-2 block font-mono text-[10px] uppercase tracking-widest text-destructive">
                        {fieldErrors.email}
                      </span>
                    )}
                  </label>
                )}

                {mode !== "forgot" && (
                  <label className="block">
                    <span className="font-mono text-[10px] uppercase tracking-widest text-muted-foreground">
                      Password
                    </span>
                    <input
                      type="password"
                      value={password}
                      onChange={(event) => {
                        setPassword(event.target.value);
                        if (fieldErrors.password) setFieldErrors((e) => ({ ...e, password: undefined }));
                      }}
                      aria-invalid={!!fieldErrors.password}
                      className={`mt-2 w-full bg-transparent border-b-2 py-3 font-mono focus:outline-none focus:border-accent ${
                        fieldErrors.password ? "border-destructive" : "border-foreground"
                      }`}
                    />
                    {fieldErrors.password && (
                      <span className="mt-2 block font-mono text-[10px] uppercase tracking-widest text-destructive">
                        {fieldErrors.password}
                      </span>
                    )}
                  </label>
                )}
              </div>

              <button
                type="submit"
                disabled={loading}
                className="w-full py-4 bg-foreground text-background font-mono text-xs uppercase tracking-widest hover:bg-accent transition-colors disabled:opacity-60"
              >
                {loading
                  ? "..."
                  : mode === "register"
                    ? "Crear cuenta →"
                    : mode === "forgot"
                      ? "Mandar mail →"
                      : "Entrar →"}
              </button>

              {slowHint && (
                <p className="font-mono text-[10px] uppercase leading-relaxed tracking-widest text-muted-foreground">
                  Despertando el servidor... la primera vez puede tardar hasta un minuto.
                  Esperá sin recargar.
                </p>
              )}

              {mode === "login" && (
                <button
                  type="button"
                  onClick={() => {
                    setMode("forgot");
                    setError("");
                  }}
                  className="w-full font-mono text-[10px] uppercase tracking-widest text-muted-foreground hover:text-accent transition-colors"
                >
                  ¿Olvidaste tu contraseña?
                </button>
              )}

              <button
                type="button"
                onClick={() => {
                  setMode(mode === "login" ? "register" : "login");
                  setError("");
                }}
                className="w-full font-mono text-[10px] uppercase tracking-widest text-muted-foreground hover:text-accent transition-colors"
              >
                {mode === "register"
                  ? "¿Ya tenés cuenta? Entrá"
                  : mode === "forgot"
                    ? "← Volver a entrar"
                    : "¿Primera vez? Registrate"}
              </button>

              {error ? (
                <div className="p-4 border-2 border-destructive/50 font-mono text-xs text-destructive">
                  {error}
                </div>
              ) : null}
            </form>
          )}
        </div>
      </main>
    </PageTransition>
  );
}
