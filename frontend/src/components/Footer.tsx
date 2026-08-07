import { Github, Linkedin } from "lucide-react";
import { useEffect, useState } from "react";

import { API_BASE_URL } from "@/hooks/useAuth";
import { useLang } from "@/lib/i18n";
import { SECONDARY_QUOTE } from "@/lib/quotes";

type CatalogStats = { movies: number; series: number; genres: number };

const SOCIAL_LINKS = [
  { label: "LinkedIn", href: "https://www.linkedin.com/in/matias-russo-lacerna/", Icon: Linkedin },
  { label: "GitHub", href: "https://github.com/matiassrusso", Icon: Github },
];

const compactNumber = new Intl.NumberFormat("en", { notation: "compact" });

export function Footer() {
  const [stats, setStats] = useState<CatalogStats | null>(null);
  const { t } = useLang();

  useEffect(() => {
    let cancelled = false;
    fetch(`${API_BASE_URL}/catalog/stats`)
      .then((response) => (response.ok ? response.json() : null))
      .then((body: CatalogStats | null) => {
        if (!cancelled) setStats(body);
      })
      .catch(() => {
        if (!cancelled) setStats(null);
      });
    return () => {
      cancelled = true;
    };
  }, []);

  return (
    <footer className="bg-foreground text-background mt-24 px-6 py-12">
      <div className="container flex flex-col md:flex-row justify-between items-start gap-12">
        <div className="space-y-8">
          <div className="flex items-center gap-2 font-mono text-xs uppercase tracking-widest opacity-70">
            <span>Butaca</span>
            <span className="opacity-40">—</span>
            <span>{t("home.footer.tagline")}</span>
          </div>

          <div>
            <div className="font-mono text-[10px] uppercase tracking-widest opacity-50 mb-3">
              {t("home.footer.author")}
            </div>
            <div className="flex gap-3">
              {SOCIAL_LINKS.map(({ label, href, Icon }) => (
                <a
                  key={label}
                  href={href}
                  target="_blank"
                  rel="noopener noreferrer"
                  aria-label={label}
                  className="flex items-center gap-2 border border-background/30 px-3 py-2 font-mono text-[10px] uppercase tracking-widest opacity-70 hover:opacity-100 hover:border-background transition-all"
                >
                  <Icon size={14} aria-hidden="true" />
                  {label}
                </a>
              ))}
            </div>
          </div>

          {stats && (
            <div>
              <div className="font-mono text-[10px] uppercase tracking-widest opacity-50 mb-3">
                {t("home.footer.stats")}
              </div>
              <div className="flex gap-10">
                <div>
                  <div className="text-2xl font-black">{compactNumber.format(stats.movies)}</div>
                  <div className="font-mono text-[10px] uppercase tracking-widest opacity-50">{t("common.movies")}</div>
                </div>
                <div>
                  <div className="text-2xl font-black">{compactNumber.format(stats.series)}</div>
                  <div className="font-mono text-[10px] uppercase tracking-widest opacity-50">{t("common.series")}</div>
                </div>
                <div>
                  <div className="text-2xl font-black">{stats.genres}</div>
                  <div className="font-mono text-[10px] uppercase tracking-widest opacity-50">{t("home.footer.genres")}</div>
                </div>
              </div>
            </div>
          )}
        </div>

        <div className="text-right space-y-3">
          <div className="font-serif italic text-lg opacity-80 max-w-sm">
            "{SECONDARY_QUOTE.text}"
          </div>
          <div className="font-mono text-[10px] uppercase tracking-widest opacity-40">
            — {SECONDARY_QUOTE.author}
          </div>
          <p className="font-mono text-[10px] uppercase tracking-widest opacity-50">
            {t("home.footer.tmdbCredit")}{" "}
            <a
              href="https://www.themoviedb.org"
              target="_blank"
              rel="noopener noreferrer"
              className="underline hover:opacity-100 transition-opacity"
            >
              TMDB
            </a>
          </p>
        </div>
      </div>
    </footer>
  );
}
