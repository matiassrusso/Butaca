import { useEffect, useRef, useState } from "react";

import { useLang } from "@/lib/i18n";

// Botón propio (no el que renderiza Google) para que entre en el sistema
// "Hybrid critic notebook": mono uppercase, radius 0, borde grueso.
//
// Por eso el flujo es `initTokenClient` (access token vía popup) y no el de
// ID token: ese obliga a usar `renderButton` de Google, que es un widget que
// él mismo dibuja y no se puede restilar. El logo sí es el oficial, que es lo
// que piden las guidelines de branding.

const GSI_SRC = "https://accounts.google.com/gsi/client";
const CLIENT_ID = import.meta.env.VITE_GOOGLE_CLIENT_ID as string | undefined;

type TokenClient = { requestAccessToken: () => void };

declare global {
  interface Window {
    google?: {
      accounts: {
        oauth2: {
          initTokenClient: (config: {
            client_id: string;
            scope: string;
            callback: (response: { access_token?: string; error?: string }) => void;
            error_callback?: (error: { type?: string }) => void;
          }) => TokenClient;
        };
      };
    };
  }
}

function loadGsi(): Promise<void> {
  if (window.google?.accounts?.oauth2) return Promise.resolve();
  const existing = document.querySelector<HTMLScriptElement>(`script[src="${GSI_SRC}"]`);
  if (existing) {
    return new Promise((resolve, reject) => {
      existing.addEventListener("load", () => resolve());
      existing.addEventListener("error", () => reject(new Error("gsi")));
    });
  }
  return new Promise((resolve, reject) => {
    const script = document.createElement("script");
    script.src = GSI_SRC;
    script.async = true;
    script.onload = () => resolve();
    script.onerror = () => reject(new Error("gsi"));
    document.head.appendChild(script);
  });
}

function GoogleLogo() {
  return (
    <svg viewBox="0 0 18 18" className="size-4 shrink-0" aria-hidden="true">
      <path
        fill="#4285F4"
        d="M17.64 9.2c0-.64-.06-1.25-.16-1.84H9v3.48h4.84a4.14 4.14 0 0 1-1.8 2.72v2.26h2.91c1.7-1.57 2.69-3.88 2.69-6.62Z"
      />
      <path
        fill="#34A853"
        d="M9 18c2.43 0 4.47-.8 5.96-2.18l-2.91-2.26c-.81.54-1.84.86-3.05.86-2.35 0-4.34-1.58-5.05-3.71H.96v2.33A9 9 0 0 0 9 18Z"
      />
      <path
        fill="#FBBC05"
        d="M3.95 10.71a5.4 5.4 0 0 1 0-3.42V4.96H.96a9 9 0 0 0 0 8.08l2.99-2.33Z"
      />
      <path
        fill="#EA4335"
        d="M9 3.58c1.32 0 2.51.45 3.44 1.35l2.58-2.59C13.46.89 11.43 0 9 0A9 9 0 0 0 .96 4.96l2.99 2.33C4.66 5.16 6.65 3.58 9 3.58Z"
      />
    </svg>
  );
}

type Props = {
  onCredential: (accessToken: string) => void;
  disabled?: boolean;
  label?: string;
};

export function GoogleSignInButton({ onCredential, disabled, label }: Props) {
  const { t } = useLang();
  const [ready, setReady] = useState(false);
  const clientRef = useRef<TokenClient | null>(null);
  // el cliente de Google se crea una sola vez, así que el callback se lee de
  // un ref para no recrearlo en cada render del padre
  const callbackRef = useRef(onCredential);
  callbackRef.current = onCredential;

  useEffect(() => {
    if (!CLIENT_ID) return;
    let cancelled = false;

    loadGsi()
      .then(() => {
        if (cancelled || !window.google) return;
        clientRef.current = window.google.accounts.oauth2.initTokenClient({
          client_id: CLIENT_ID,
          scope: "openid email profile",
          callback: (response) => {
            if (response.access_token) callbackRef.current(response.access_token);
          },
          // cerrar el popup sin elegir cuenta no es un error que mostrar
          error_callback: () => undefined,
        });
        setReady(true);
      })
      .catch(() => {
        // sin conexión con Google el botón no aparece; el resto del login
        // (usuario/contraseña, invitado) sigue funcionando
      });

    return () => {
      cancelled = true;
    };
  }, []);

  if (!CLIENT_ID || !ready) return null;

  return (
    <button
      type="button"
      disabled={disabled}
      onClick={() => clientRef.current?.requestAccessToken()}
      className="group w-full flex items-center justify-center gap-3 py-4 border-2 border-foreground bg-background font-mono text-xs uppercase tracking-widest hover:bg-foreground hover:text-background transition-colors disabled:opacity-60"
    >
      {/* blanco fijo, no bg-background: el recuadro tiene que quedar claro en
          los dos temas y también en hover (donde el botón se invierte a
          tinta). Las guidelines de Google piden el logo sobre fondo claro. */}
      <span className="grid place-items-center size-6 bg-white">
        <GoogleLogo />
      </span>
      {label ?? t("auth.googleButton")}
    </button>
  );
}
