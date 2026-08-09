import { CornerDownLeft, Loader2, RotateCcw } from "lucide-react";
import { useEffect, useRef, useState } from "react";
import { useLocation } from "wouter";

import { PageTransition } from "@/components/PageTransition";
import { API_BASE_URL, useAuth } from "@/hooks/useAuth";
import { useLang } from "@/lib/i18n";

// Charla libre con el agente de Butaca (aprobado por Matías, 2026-08-09): la
// versión conversacional de lo que hoy solo se puede pedir por el wizard de
// /recommend. La voz del agente es la MISMA de todo el sitio -- el backend
// arma el prompt con las constantes compartidas de llm_client.
//
// La conversación vive SOLO acá, en estado de React: no hay tabla de chats en
// la base, el cliente manda el historial entero en cada turno y el backend lo
// recorta. Salir de la página la pierde, a propósito.
//
// Sin streaming a propósito (decisión de la tarea): SSE detrás del proxy de
// Render es complejidad grande para lo que acá resuelve un "Escribiendo…".

type Message = { role: "user" | "agent"; content: string };

const MAX_CHARS = 1000; // igual que ChatMessage.content en backend/app/models.py

export default function Chat() {
  const { isAuthenticated, loading: authLoading, token } = useAuth();
  const [, navigate] = useLocation();
  const { t } = useLang();

  const [messages, setMessages] = useState<Message[]>([]);
  const [draft, setDraft] = useState("");
  const [sending, setSending] = useState(false);
  const [error, setError] = useState("");
  const endRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    if (!authLoading && !isAuthenticated) navigate("/login");
  }, [authLoading, isAuthenticated, navigate]);

  // el último mensaje tiene que quedar a la vista sin que el usuario scrollee
  useEffect(() => {
    endRef.current?.scrollIntoView({ behavior: "smooth", block: "end" });
  }, [messages, sending]);

  async function send(text: string) {
    const content = text.trim().slice(0, MAX_CHARS);
    if (!content || sending || !token) return;

    const next: Message[] = [...messages, { role: "user", content }];
    setMessages(next);
    setDraft("");
    setSending(true);
    setError("");

    try {
      const response = await fetch(`${API_BASE_URL}/chat`, {
        method: "POST",
        headers: { "Content-Type": "application/json", Authorization: `Bearer ${token}` },
        body: JSON.stringify({ messages: next }),
      });
      const body = await response.json().catch(() => null);
      if (!response.ok) {
        // el backend manda el motivo real (límite diario, agente caído) ya
        // traducido por errors.py -- mostrarlo vale más que un genérico
        setError(typeof body?.detail === "string" ? body.detail : t("chat.error"));
        return;
      }
      setMessages([...next, { role: "agent", content: body.reply }]);
    } catch {
      setError(t("chat.error"));
    } finally {
      setSending(false);
    }
  }

  if (authLoading || !isAuthenticated) {
    return (
      <div className="min-h-screen flex items-center justify-center">
        <Loader2 className="w-8 h-8 animate-spin text-accent" />
      </div>
    );
  }

  const starters = [t("chat.starter1"), t("chat.starter2"), t("chat.starter3")];

  return (
    <PageTransition>
      <main className="max-w-2xl mx-auto px-6 pt-16 pb-24">
        <header className="pb-8 border-b-2 border-foreground mb-8">
          <div className="font-mono text-[10px] uppercase tracking-widest text-muted-foreground mb-4">
            {t("chat.tag")}
          </div>
          <h1 className="text-6xl md:text-7xl font-black uppercase tracking-tighter leading-[0.9]">
            {t("chat.titlePrefix")}
            <span className="text-accent italic font-serif normal-case tracking-normal">
              {t("chat.titleAccent")}
            </span>
          </h1>
          <p className="font-mono text-xs text-muted-foreground mt-4">{t("chat.intro")}</p>
        </header>

        {messages.length === 0 && !sending && (
          <div className="mb-8">
            <p className="font-mono text-[10px] uppercase tracking-widest text-muted-foreground mb-3">
              {t("chat.starterHint")}
            </p>
            <div className="flex flex-col gap-2">
              {starters.map((starter) => (
                <button
                  key={starter}
                  onClick={() => send(starter)}
                  className="text-left px-4 py-3 border-2 border-foreground/20 hover:border-accent hover:text-accent transition-colors text-sm"
                >
                  {starter}
                </button>
              ))}
            </div>
          </div>
        )}

        <div className="space-y-6">
          {messages.map((message, index) => (
            <div
              key={index}
              className={message.role === "user" ? "pl-10 md:pl-24 text-right" : ""}
            >
              <div className="font-mono text-[10px] uppercase tracking-widest text-muted-foreground mb-2">
                {message.role === "user" ? t("chat.you") : t("chat.agent")}
              </div>
              <p
                className={
                  message.role === "user"
                    ? "inline-block text-left px-4 py-3 border-2 border-foreground/20 text-sm whitespace-pre-wrap"
                    : "border-l-2 border-accent pl-4 text-base leading-relaxed whitespace-pre-wrap"
                }
              >
                {message.content}
              </p>
            </div>
          ))}

          {sending && (
            <div>
              <div className="font-mono text-[10px] uppercase tracking-widest text-muted-foreground mb-2">
                {t("chat.agent")}
              </div>
              <p className="border-l-2 border-accent pl-4 font-mono text-xs uppercase tracking-widest text-muted-foreground flex items-center gap-2">
                <Loader2 className="w-3.5 h-3.5 animate-spin text-accent" />
                {t("chat.thinking")}
              </p>
            </div>
          )}

          {error && (
            <div className="p-4 border-2 border-destructive/50 font-mono text-xs text-destructive">
              {error}
            </div>
          )}
          <div ref={endRef} />
        </div>

        <form
          onSubmit={(event) => {
            event.preventDefault();
            send(draft);
          }}
          className="sticky bottom-6 mt-8 flex items-stretch gap-0 border-2 border-foreground bg-background"
        >
          <input
            value={draft}
            onChange={(event) => setDraft(event.target.value)}
            maxLength={MAX_CHARS}
            placeholder={t("chat.placeholder")}
            aria-label={t("chat.placeholder")}
            disabled={sending}
            className="flex-1 px-4 py-3 bg-transparent text-sm placeholder:text-muted-foreground focus:outline-none disabled:opacity-50"
          />
          <button
            type="submit"
            disabled={sending || !draft.trim()}
            className="px-5 font-mono text-[10px] uppercase tracking-widest bg-accent text-accent-foreground hover:bg-foreground hover:text-background transition-colors disabled:opacity-40 disabled:pointer-events-none flex items-center gap-2"
          >
            {t("chat.send")}
            <CornerDownLeft className="w-3.5 h-3.5" />
          </button>
        </form>

        {messages.length > 0 && (
          <button
            onClick={() => {
              setMessages([]);
              setError("");
            }}
            className="mt-4 font-mono text-[10px] uppercase tracking-widest text-muted-foreground hover:text-accent transition-colors flex items-center gap-2"
          >
            <RotateCcw className="w-3 h-3" />
            {t("chat.reset")}
          </button>
        )}
      </main>
    </PageTransition>
  );
}
