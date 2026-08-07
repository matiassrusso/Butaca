import { useState } from "react";
import { Link } from "wouter";
import { toast } from "sonner";

import { API_BASE_URL, useAuth } from "@/hooks/useAuth";
import { useLang } from "@/lib/i18n";

// Un solo banner para los dos avisos de cuenta, porque son excluyentes: un
// invitado no tiene mail que verificar, y quien tiene mail no es invitado.
//
// El de invitado NO se puede descartar a propósito: es el único aviso de que
// esa sesión se pierde con los datos del navegador, y descartarlo lo dejaría
// sin saberlo hasta que ya perdió el historial.

export function AccountBanner() {
  const { user, token, loading } = useAuth();
  const [dismissed, setDismissed] = useState(false);
  const [sending, setSending] = useState(false);
  const { t } = useLang();

  if (loading || !user) return null;

  if (user.isGuest) {
    return (
      <Banner>
        <span>{t("home.banner.guest")}</span>
        <Link
          href="/login?claim=1"
          className="shrink-0 underline underline-offset-2 hover:opacity-70"
        >
          {t("home.banner.guestCta")}
        </Link>
      </Banner>
    );
  }

  // prompt no bloqueante: solo si hay un mail de verdad sin verificar
  if (!user.email || user.emailVerified || dismissed) return null;

  async function resend() {
    if (!token) return;
    setSending(true);
    try {
      const response = await fetch(`${API_BASE_URL}/auth/verify-email/resend`, {
        method: "POST",
        headers: { Authorization: `Bearer ${token}` },
      });
      if (!response.ok) throw new Error();
      toast.success(t("home.banner.resendOk"));
    } catch {
      toast.error(t("home.banner.resendError"));
    } finally {
      setSending(false);
    }
  }

  return (
    <Banner>
      <span>{t("home.banner.verify")}</span>
      <div className="flex items-center gap-4 shrink-0">
        <button onClick={resend} disabled={sending} className="underline hover:opacity-70 disabled:opacity-50">
          {sending ? t("home.banner.sending") : t("home.banner.resend")}
        </button>
        <button
          onClick={() => setDismissed(true)}
          aria-label={t("home.banner.dismissAria")}
          className="hover:opacity-70"
        >
          ✕
        </button>
      </div>
    </Banner>
  );
}

function Banner({ children }: { children: React.ReactNode }) {
  return (
    <div className="bg-accent text-accent-foreground">
      <div className="max-w-7xl mx-auto px-6 py-2.5 flex items-center justify-between gap-4 font-mono text-[10px] uppercase tracking-widest">
        {children}
      </div>
    </div>
  );
}
