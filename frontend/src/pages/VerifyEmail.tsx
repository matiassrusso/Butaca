import { useEffect, useRef, useState } from "react";
import { useLocation } from "wouter";

import { PageTransition } from "@/components/PageTransition";
import { API_BASE_URL } from "@/hooks/useAuth";
import { useLang } from "@/lib/i18n";

type Status = "verifying" | "done" | "error";

export default function VerifyEmail() {
  const { t } = useLang();
  const [, navigate] = useLocation();
  const token = new URLSearchParams(window.location.search).get("token") ?? "";
  const [status, setStatus] = useState<Status>(token ? "verifying" : "error");
  // vacío = "falta el token"; se traduce al renderizar y no al montar, así el
  // texto sigue el cambio de idioma
  const [error, setError] = useState("");
  // StrictMode double-invokes effects in dev; the token is single-use, so the
  // second call would 400 and flip a real success to error
  const ran = useRef(false);

  useEffect(() => {
    if (!token || ran.current) return;
    ran.current = true;

    fetch(`${API_BASE_URL}/auth/verify-email`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ token }),
    })
      .then(async (response) => {
        if (!response.ok) {
          const body = await response.json().catch(() => null);
          throw new Error(body?.detail ?? t("auth.errVerifyFailed"));
        }
        setStatus("done");
      })
      .catch((err) => {
        setError(err instanceof Error ? err.message : t("auth.errVerifyFailed"));
        setStatus("error");
      });
  }, [token]);

  return (
    <PageTransition>
      <main className="min-h-[calc(100vh-4rem)] flex items-center justify-center p-12">
        <div className="w-full max-w-sm space-y-8">
          <div>
            <div className="font-mono text-[10px] uppercase tracking-widest text-muted-foreground mb-2">
              {t("auth.verifyTag")}
            </div>
            <h2 className="text-3xl font-black uppercase tracking-tighter">
              {status === "done"
                ? t("auth.verifyDoneTitle")
                : status === "error"
                  ? t("auth.verifyErrorTitle")
                  : t("auth.verifyingTitle")}
            </h2>
          </div>

          {status === "verifying" && (
            <p className="font-mono text-xs uppercase tracking-widest text-muted-foreground">
              {t("auth.verifyingBody")}
            </p>
          )}

          {status === "error" && (
            <div className="p-4 border-2 border-destructive/50 font-mono text-xs text-destructive">
              {error || t("auth.verifyNoToken")} {t("auth.verifyErrorHint")}
            </div>
          )}

          {status !== "verifying" && (
            <button
              type="button"
              onClick={() => navigate("/")}
              className="w-full py-4 bg-foreground text-background font-mono text-xs uppercase tracking-widest hover:bg-accent transition-colors"
            >
              {t("auth.verifyGoHome")}
            </button>
          )}
        </div>
      </main>
    </PageTransition>
  );
}
