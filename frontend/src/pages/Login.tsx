import { FormEvent, useRef, useState } from "react";
import { useLocation } from "wouter";

import { GoogleSignInButton } from "@/components/GoogleSignInButton";
import { PageTransition } from "@/components/PageTransition";
import { API_BASE_URL, useAuth } from "@/hooks/useAuth";
import { useLang } from "@/lib/i18n";
import { PRIMARY_QUOTE } from "@/lib/quotes";

// El backend corre en el free tier de Render, que se duerme tras inactividad:
// la primera request puede tardar ~30-60s en despertar el server. Sin este
// aviso, la espera se ve como si login/registro estuviera roto.
const COLD_START_HINT_MS = 4000;

export default function Login() {
  const { login, register, guestLogin, claimAccount, googleLogin, user } = useAuth();
  const { t } = useLang();
  const [, navigate] = useLocation();
  // ?register=1 (CTA "Empezar gratis" del home) abre directo en modo registro.
  // ?claim=1 (banner de invitado) usa el mismo form, pero conservando la
  // cuenta de invitado en vez de crear una nueva y perder su historial.
  const [mode, setMode] = useState<"login" | "register" | "forgot" | "claim">(() => {
    const params = new URLSearchParams(window.location.search);
    if (params.has("claim")) return "claim";
    return params.has("register") ? "register" : "login";
  });
  const isClaiming = mode === "claim" && Boolean(user?.isGuest);
  const [username, setUsername] = useState("");
  const [password, setPassword] = useState("");
  const [email, setEmail] = useState("");
  const [loading, setLoading] = useState(false);
  const [slowHint, setSlowHint] = useState(false);
  const [error, setError] = useState("");
  const [forgotSent, setForgotSent] = useState(false);
  const [fieldErrors, setFieldErrors] = useState<{ username?: string; email?: string; password?: string }>({});
  const slowTimer = useRef<ReturnType<typeof setTimeout> | null>(null);

  const needsEmail = mode === "register" || mode === "claim";

  function validate(): boolean {
    const errs: typeof fieldErrors = {};
    if (username.trim().length < 3) errs.username = t("auth.errUsernameMin");
    if (needsEmail && !/^[^@\s]+@[^@\s]+\.[^@\s]+$/.test(email))
      errs.email = t("auth.errEmailInvalid");
    if (mode !== "forgot" && password.length < 8) errs.password = t("auth.errPasswordMin");
    setFieldErrors(errs);
    return Object.keys(errs).length === 0;
  }

  async function handleGoogle(idToken: string) {
    setLoading(true);
    setError("");
    try {
      await googleLogin(idToken);
      navigate("/recommend");
    } catch (err) {
      setError(err instanceof Error ? err.message : t("auth.errGoogle"));
    } finally {
      setLoading(false);
    }
  }

  async function handleGuest() {
    setLoading(true);
    setError("");
    setSlowHint(false);
    slowTimer.current = setTimeout(() => setSlowHint(true), COLD_START_HINT_MS);

    try {
      await guestLogin();
      navigate("/recommend");
    } catch (err) {
      setError(err instanceof Error ? err.message : t("auth.errGuest"));
    } finally {
      if (slowTimer.current) clearTimeout(slowTimer.current);
      setLoading(false);
      setSlowHint(false);
    }
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
      } else if (isClaiming) {
        await claimAccount(username, password, email);
      } else {
        await register(username, password, email);
      }
      navigate("/recommend");
    } catch (err) {
      setError(err instanceof Error ? err.message : t("auth.errAuth"));
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
              {t("auth.heroTitleLead")}{" "}
              <span className="text-accent italic font-serif normal-case tracking-normal">
                {t("auth.heroTitleAccent")}
              </span>
              .
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
                  {t("auth.tagRecovery")}
                </div>
                <h2 className="text-3xl font-black uppercase tracking-tighter">
                  {t("auth.forgotSentTitle")}
                </h2>
                <p className="text-sm text-muted-foreground mt-2">{t("auth.forgotSentBody")}</p>
              </div>
              <button
                type="button"
                onClick={() => {
                  setMode("login");
                  setForgotSent(false);
                }}
                className="w-full font-mono text-[10px] uppercase tracking-widest text-muted-foreground hover:text-accent transition-colors"
              >
                {t("auth.backToLogin")}
              </button>
            </div>
          ) : (
            <form onSubmit={handleSubmit} noValidate className="w-full max-w-sm space-y-8">
              <div>
                <div className="font-mono text-[10px] uppercase tracking-widest text-muted-foreground mb-2">
                  {isClaiming
                    ? t("auth.tagClaim")
                    : needsEmail
                      ? t("auth.tagRegister")
                      : mode === "forgot"
                        ? t("auth.tagRecovery")
                        : t("auth.tagLogin")}
                </div>
                <h2 className="text-3xl font-black uppercase tracking-tighter">
                  {isClaiming
                    ? t("auth.claimTitle")
                    : needsEmail
                      ? t("auth.registerTitle")
                      : mode === "forgot"
                        ? t("auth.forgotTitle")
                        : t("auth.loginTitle")}
                </h2>
                <p className="text-sm text-muted-foreground mt-2">
                  {isClaiming
                    ? t("auth.claimSubtitle")
                    : mode === "forgot"
                      ? t("auth.forgotSubtitle")
                      : t("auth.loginSubtitle")}
                </p>
              </div>

              <div className="space-y-6">
                <label className="block">
                  <span className="font-mono text-[10px] uppercase tracking-widest text-muted-foreground">
                    {t("auth.usernameLabel")}
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

                {needsEmail && (
                  <label className="block">
                    <span className="font-mono text-[10px] uppercase tracking-widest text-muted-foreground">
                      {t("auth.emailLabel")}
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
                      {t("auth.passwordLabel")}
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
                  : isClaiming
                    ? t("auth.submitClaim")
                    : needsEmail
                      ? t("auth.submitRegister")
                      : mode === "forgot"
                        ? t("auth.submitForgot")
                        : t("auth.submitLogin")}
              </button>

              {slowHint && (
                <p className="font-mono text-[10px] uppercase leading-relaxed tracking-widest text-muted-foreground">
                  {t("auth.slowHint")}
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
                  {t("auth.forgotLink")}
                </button>
              )}

              {!isClaiming && (
                <button
                  type="button"
                  onClick={() => {
                    setMode(mode === "login" ? "register" : "login");
                    setError("");
                  }}
                  className="w-full font-mono text-[10px] uppercase tracking-widest text-muted-foreground hover:text-accent transition-colors"
                >
                  {mode === "register"
                    ? t("auth.toLogin")
                    : mode === "forgot"
                      ? t("auth.backToLogin")
                      : t("auth.toRegister")}
                </button>
              )}

              {mode !== "forgot" && (
                <div className="space-y-3">
                  <div className="flex items-center gap-3 font-mono text-[10px] uppercase tracking-widest text-muted-foreground/60">
                    <span className="h-px flex-1 bg-foreground/10" />
                    {t("auth.or")}
                    <span className="h-px flex-1 bg-foreground/10" />
                  </div>

                  <GoogleSignInButton onCredential={handleGoogle} disabled={loading} />

                  {isClaiming ? (
                    <p className="font-mono text-[10px] uppercase leading-relaxed tracking-widest text-muted-foreground/60">
                      {t("auth.googleKeepsRatings")}
                    </p>
                  ) : (
                    <>
                      <button
                        type="button"
                        onClick={handleGuest}
                        disabled={loading}
                        className="w-full py-4 border-2 border-foreground/30 font-mono text-xs uppercase tracking-widest hover:border-accent hover:text-accent transition-colors disabled:opacity-60"
                      >
                        {t("auth.guestButton")}
                      </button>
                      <p className="font-mono text-[10px] uppercase leading-relaxed tracking-widest text-muted-foreground/60">
                        {t("auth.guestDisclaimer")}
                      </p>
                    </>
                  )}
                </div>
              )}

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
