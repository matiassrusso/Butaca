import { Loader2, Send } from "lucide-react";
import { FormEvent, useState } from "react";
import { Link } from "wouter";
import { toast } from "sonner";

import { PageTransition } from "@/components/PageTransition";
import { API_BASE_URL, useAuth } from "@/hooks/useAuth";
import { useLang } from "@/lib/i18n";

const MAX_MESSAGE_LENGTH = 4000;

export default function Feedback() {
  const { token } = useAuth();
  const { t } = useLang();
  const [message, setMessage] = useState("");
  const [email, setEmail] = useState("");
  const [sending, setSending] = useState(false);
  const [sent, setSent] = useState(false);

  async function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const trimmedMessage = message.trim();
    if (!trimmedMessage || sending) return;

    setSending(true);
    try {
      const response = await fetch(`${API_BASE_URL}/site-feedback`, {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
          ...(token ? { Authorization: `Bearer ${token}` } : {}),
        },
        body: JSON.stringify({ message: trimmedMessage, email: email.trim() }),
      });
      if (!response.ok) throw new Error();
      setSent(true);
    } catch {
      toast.error(t("feedback.error"));
    } finally {
      setSending(false);
    }
  }

  return (
    <PageTransition>
      <main className="max-w-2xl mx-auto px-6 pt-16 pb-24">
        <header className="pb-8 border-b-2 border-foreground mb-8">
          <div className="font-mono text-[10px] uppercase tracking-widest text-muted-foreground mb-4">
            {t("feedback.kicker")}
          </div>
          <h1 className="text-5xl md:text-6xl font-black uppercase tracking-tighter leading-[0.9]">
            {t("feedback.titlePrefix")} {" "}
            <span className="text-accent italic font-serif normal-case tracking-normal">
              {t("feedback.titleAccent")}
            </span>
          </h1>
          <p className="font-mono text-xs text-muted-foreground mt-5 leading-relaxed">
            {t("feedback.intro")}
          </p>
        </header>

        {sent ? (
          <section className="border-2 border-foreground p-6 md:p-8">
            <p className="font-mono text-[10px] uppercase tracking-widest text-accent mb-3">
              {t("feedback.sentKicker")}
            </p>
            <h2 className="text-3xl font-black uppercase tracking-tighter mb-4">{t("feedback.thanks")}</h2>
            <p className="text-sm leading-relaxed text-muted-foreground mb-6">{t("feedback.thanksBody")}</p>
            <Link
              href="/"
              className="inline-flex px-5 py-3 bg-accent text-accent-foreground font-mono text-[10px] uppercase tracking-widest hover:bg-foreground hover:text-background transition-colors"
            >
              {t("feedback.backHome")} →
            </Link>
          </section>
        ) : (
          <form onSubmit={submit} className="space-y-6" noValidate>
            <div>
              <label htmlFor="site-feedback-message" className="block font-mono text-[10px] uppercase tracking-widest mb-2">
                {t("feedback.messageLabel")}
              </label>
              <textarea
                id="site-feedback-message"
                value={message}
                onChange={(event) => setMessage(event.target.value)}
                required
                maxLength={MAX_MESSAGE_LENGTH}
                rows={8}
                placeholder={t("feedback.messagePlaceholder")}
                className="w-full resize-y border-2 border-foreground bg-background px-4 py-3 text-sm leading-relaxed placeholder:text-muted-foreground/70 focus:outline-none focus:border-accent"
              />
              <p className="mt-2 text-right font-mono text-[10px] text-muted-foreground" aria-live="polite">
                {message.length}/{MAX_MESSAGE_LENGTH}
              </p>
            </div>

            <div>
              <label htmlFor="site-feedback-email" className="block font-mono text-[10px] uppercase tracking-widest mb-2">
                {t("feedback.emailLabel")}
              </label>
              <input
                id="site-feedback-email"
                type="email"
                value={email}
                onChange={(event) => setEmail(event.target.value)}
                maxLength={320}
                placeholder={t("feedback.emailPlaceholder")}
                className="w-full border-2 border-foreground bg-background px-4 py-3 text-sm placeholder:text-muted-foreground/70 focus:outline-none focus:border-accent"
              />
              <p className="mt-2 font-mono text-[10px] uppercase tracking-widest text-muted-foreground">
                {t("feedback.emailHint")}
              </p>
            </div>

            <button
              type="submit"
              disabled={sending || !message.trim()}
              className="inline-flex items-center gap-2 px-6 py-3 bg-accent text-accent-foreground font-mono text-[10px] uppercase tracking-widest hover:bg-foreground hover:text-background disabled:opacity-50 disabled:cursor-not-allowed transition-colors"
            >
              {sending ? <Loader2 className="size-4 animate-spin" aria-hidden="true" /> : <Send className="size-4" aria-hidden="true" />}
              {sending ? t("feedback.sending") : t("feedback.submit")}
            </button>
          </form>
        )}
      </main>
    </PageTransition>
  );
}
