import { FormEvent, useState } from "react";
import { useLocation } from "wouter";

import { PageTransition } from "@/components/PageTransition";
import { API_BASE_URL } from "@/hooks/useAuth";
import { useLang } from "@/lib/i18n";

export default function ResetPassword() {
  const { t } = useLang();
  const [, navigate] = useLocation();
  const token = new URLSearchParams(window.location.search).get("token") ?? "";
  const [password, setPassword] = useState("");
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");
  const [done, setDone] = useState(false);

  async function handleSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setLoading(true);
    setError("");

    try {
      const response = await fetch(`${API_BASE_URL}/auth/reset-password`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ token, password }),
      });

      if (!response.ok) {
        const body = await response.json().catch(() => null);
        throw new Error(body?.detail ?? t("auth.errResetFailed"));
      }

      setDone(true);
    } catch (err) {
      setError(err instanceof Error ? err.message : t("auth.errResetFailed"));
    } finally {
      setLoading(false);
    }
  }

  return (
    <PageTransition>
      <main className="min-h-[calc(100vh-4rem)] flex items-center justify-center p-12">
        <div className="w-full max-w-sm space-y-8">
          <div>
            <div className="font-mono text-[10px] uppercase tracking-widest text-muted-foreground mb-2">
              {t("auth.tagRecovery")}
            </div>
            <h2 className="text-3xl font-black uppercase tracking-tighter">
              {done ? t("auth.resetDoneTitle") : t("auth.resetTitle")}
            </h2>
          </div>

          {!token && !done && (
            <div className="p-4 border-2 border-destructive/50 font-mono text-xs text-destructive">
              {t("auth.resetNoToken")}
            </div>
          )}

          {done ? (
            <button
              type="button"
              onClick={() => navigate("/login")}
              className="w-full py-4 bg-foreground text-background font-mono text-xs uppercase tracking-widest hover:bg-accent transition-colors"
            >
              {t("auth.resetGoToLogin")}
            </button>
          ) : (
            <form onSubmit={handleSubmit} className="space-y-8">
              <label className="block">
                <span className="font-mono text-[10px] uppercase tracking-widest text-muted-foreground">
                  {t("auth.resetNewPassword")}
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

              <button
                type="submit"
                disabled={loading || !token}
                className="w-full py-4 bg-foreground text-background font-mono text-xs uppercase tracking-widest hover:bg-accent transition-colors disabled:opacity-60"
              >
                {loading ? "..." : t("auth.resetSubmit")}
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
