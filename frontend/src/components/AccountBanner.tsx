import { useState } from "react";
import { Link } from "wouter";
import { toast } from "sonner";

import { API_BASE_URL, useAuth } from "@/hooks/useAuth";

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

  if (loading || !user) return null;

  if (user.isGuest) {
    return (
      <Banner>
        <span>
          Estás como invitado. Poné usuario y contraseña para no perder tus puntuaciones.
        </span>
        <Link
          href="/login?claim=1"
          className="shrink-0 underline underline-offset-2 hover:opacity-70"
        >
          Crear mi cuenta
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
      toast.success("Te reenviamos el mail de verificación.");
    } catch {
      toast.error("No pude reenviar el mail. Probá más tarde.");
    } finally {
      setSending(false);
    }
  }

  return (
    <Banner>
      <span>Confirmá tu email para asegurar tu cuenta. Te mandamos un link al registrarte.</span>
      <div className="flex items-center gap-4 shrink-0">
        <button onClick={resend} disabled={sending} className="underline hover:opacity-70 disabled:opacity-50">
          {sending ? "Enviando…" : "Reenviar"}
        </button>
        <button onClick={() => setDismissed(true)} aria-label="Cerrar aviso" className="hover:opacity-70">
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
