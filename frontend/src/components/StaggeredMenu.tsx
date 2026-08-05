import { gsap } from "gsap";
import { useCallback, useEffect, useLayoutEffect, useRef, useState } from "react";
import { createPortal } from "react-dom";
import { Link, useLocation } from "wouter";

import "./StaggeredMenu.css";

// Adaptado de React Bits (StaggeredMenu, variante JS+CSS) al sistema de
// diseño "Hybrid critic notebook" de Butaca: sin logo/header propio (Navbar
// ya tiene el suyo), e items que además de navegar pueden disparar una acción
// (tema, salir) — el dropdown que reemplaza mezclaba ambos.
//
// El panel va por portal a <body> porque la Navbar usa backdrop-blur, y un
// backdrop-filter convierte al elemento en containing block de sus
// descendientes position:fixed: adentro, el panel se anclaba a la navbar
// (alto de 66px) y desbordaba la página en horizontal.

export type StaggeredMenuItem = {
  label: string;
  ariaLabel: string;
  link?: string;
  onSelect?: () => void;
};

export type StaggeredMenuSocialItem = {
  label: string;
  link: string;
};

type StaggeredMenuProps = {
  position?: "left" | "right";
  items: StaggeredMenuItem[];
  socialItems?: StaggeredMenuSocialItem[];
  displaySocials?: boolean;
  displayItemNumbering?: boolean;
  eyebrow?: string;
  triggerLabel?: string;
  closeOnClickAway?: boolean;
  onMenuOpen?: () => void;
  onMenuClose?: () => void;
};

export function StaggeredMenu({
  position = "right",
  items,
  socialItems = [],
  displaySocials = true,
  displayItemNumbering = true,
  eyebrow,
  triggerLabel = "Menú",
  closeOnClickAway = true,
  onMenuOpen,
  onMenuClose,
}: StaggeredMenuProps) {
  const [open, setOpen] = useState(false);
  const [location] = useLocation();
  const openRef = useRef(false);
  const panelRef = useRef<HTMLDivElement>(null);
  const preLayersRef = useRef<HTMLDivElement>(null);
  const preLayerElsRef = useRef<HTMLDivElement[]>([]);
  const iconRef = useRef<HTMLSpanElement>(null);
  const toggleBtnRef = useRef<HTMLButtonElement>(null);

  const openTlRef = useRef<gsap.core.Timeline | null>(null);
  const closeTweenRef = useRef<gsap.core.Tween | null>(null);
  const spinTweenRef = useRef<gsap.core.Tween | null>(null);

  useLayoutEffect(() => {
    const ctx = gsap.context(() => {
      const panel = panelRef.current;
      const preContainer = preLayersRef.current;
      const icon = iconRef.current;
      if (!panel || !icon) return;

      const preLayers = preContainer
        ? Array.from(preContainer.querySelectorAll<HTMLDivElement>(".sm-prelayer"))
        : [];
      preLayerElsRef.current = preLayers;

      const offscreen = position === "left" ? -100 : 100;
      gsap.set([panel, ...preLayers], { xPercent: offscreen });
      gsap.set(icon, { rotate: 0, transformOrigin: "50% 50%" });
    });
    return () => ctx.revert();
  }, [position]);

  const buildOpenTimeline = useCallback(() => {
    const panel = panelRef.current;
    const layers = preLayerElsRef.current;
    if (!panel) return null;

    openTlRef.current?.kill();
    closeTweenRef.current?.kill();
    closeTweenRef.current = null;

    const itemEls = Array.from(panel.querySelectorAll<HTMLElement>(".sm-panel-itemLabel"));
    const numberEls = Array.from(
      panel.querySelectorAll<HTMLElement>(".sm-panel-list[data-numbering] .sm-panel-item"),
    );
    const socialTitle = panel.querySelector<HTMLElement>(".sm-socials-title");
    const socialLinks = Array.from(panel.querySelectorAll<HTMLElement>(".sm-socials-link"));

    const offscreen = position === "left" ? -100 : 100;

    if (itemEls.length) gsap.set(itemEls, { yPercent: 140, rotate: 10 });
    if (numberEls.length) gsap.set(numberEls, { "--sm-num-opacity": 0 } as gsap.TweenVars);
    if (socialTitle) gsap.set(socialTitle, { opacity: 0 });
    if (socialLinks.length) gsap.set(socialLinks, { y: 25, opacity: 0 });

    const tl = gsap.timeline({ paused: true });

    layers.forEach((el, i) => {
      tl.fromTo(el, { xPercent: offscreen }, { xPercent: 0, duration: 0.5, ease: "power4.out" }, i * 0.07);
    });
    const lastTime = layers.length ? (layers.length - 1) * 0.07 : 0;
    const panelInsertTime = lastTime + (layers.length ? 0.08 : 0);
    const panelDuration = 0.65;
    tl.fromTo(panel, { xPercent: offscreen }, { xPercent: 0, duration: panelDuration, ease: "power4.out" }, panelInsertTime);

    if (itemEls.length) {
      const itemsStart = panelInsertTime + panelDuration * 0.15;
      tl.to(
        itemEls,
        { yPercent: 0, rotate: 0, duration: 1, ease: "power4.out", stagger: { each: 0.1, from: "start" } },
        itemsStart,
      );
      if (numberEls.length) {
        tl.to(
          numberEls,
          { duration: 0.6, ease: "power2.out", "--sm-num-opacity": 1, stagger: { each: 0.08, from: "start" } } as gsap.TweenVars,
          itemsStart + 0.1,
        );
      }
    }

    if (socialTitle || socialLinks.length) {
      const socialsStart = panelInsertTime + panelDuration * 0.4;
      if (socialTitle) tl.to(socialTitle, { opacity: 1, duration: 0.5, ease: "power2.out" }, socialsStart);
      if (socialLinks.length) {
        tl.to(
          socialLinks,
          {
            y: 0,
            opacity: 1,
            duration: 0.55,
            ease: "power3.out",
            stagger: { each: 0.08, from: "start" },
            onComplete: () => gsap.set(socialLinks, { clearProps: "opacity" }),
          },
          socialsStart + 0.04,
        );
      }
    }

    openTlRef.current = tl;
    return tl;
  }, [position]);

  const playOpen = useCallback(() => {
    buildOpenTimeline()?.play(0);
  }, [buildOpenTimeline]);

  const playClose = useCallback(() => {
    openTlRef.current?.kill();
    openTlRef.current = null;

    const panel = panelRef.current;
    const layers = preLayerElsRef.current;
    if (!panel) return;

    const offscreen = position === "left" ? -100 : 100;
    closeTweenRef.current?.kill();
    closeTweenRef.current = gsap.to([...layers, panel], {
      xPercent: offscreen,
      duration: 0.32,
      ease: "power3.in",
      overwrite: "auto",
    });
  }, [position]);

  const animateIcon = useCallback((opening: boolean) => {
    const icon = iconRef.current;
    if (!icon) return;
    spinTweenRef.current?.kill();
    spinTweenRef.current = gsap.to(icon, {
      rotate: opening ? 225 : 0,
      duration: opening ? 0.8 : 0.35,
      ease: opening ? "power4.out" : "power3.inOut",
      overwrite: "auto",
    });
  }, []);

  const closeMenu = useCallback(() => {
    if (!openRef.current) return;
    openRef.current = false;
    setOpen(false);
    onMenuClose?.();
    playClose();
    animateIcon(false);
  }, [playClose, animateIcon, onMenuClose]);

  const toggleMenu = useCallback(() => {
    const target = !openRef.current;
    openRef.current = target;
    setOpen(target);
    if (target) {
      onMenuOpen?.();
      playOpen();
    } else {
      onMenuClose?.();
      playClose();
    }
    animateIcon(target);
  }, [playOpen, playClose, animateIcon, onMenuOpen, onMenuClose]);

  // cerrar al navegar (ítems que son links de wouter)
  useEffect(() => {
    closeMenu();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [location]);

  useEffect(() => {
    if (!open) return;
    function onKey(e: KeyboardEvent) {
      if (e.key === "Escape") closeMenu();
    }
    document.addEventListener("keydown", onKey);
    return () => document.removeEventListener("keydown", onKey);
  }, [open, closeMenu]);

  useEffect(() => {
    if (!closeOnClickAway || !open) return;
    function onDown(e: MouseEvent) {
      const target = e.target as Node;
      if (panelRef.current?.contains(target) || toggleBtnRef.current?.contains(target)) return;
      closeMenu();
    }
    document.addEventListener("mousedown", onDown);
    return () => document.removeEventListener("mousedown", onDown);
  }, [closeOnClickAway, open, closeMenu]);

  const handleSelect = (item: StaggeredMenuItem) => {
    item.onSelect?.();
    if (!item.link) closeMenu();
  };

  return (
    <>
      <button
        ref={toggleBtnRef}
        type="button"
        onClick={toggleMenu}
        aria-haspopup="menu"
        aria-expanded={open}
        aria-controls="staggered-menu-panel"
        aria-label={open ? "Cerrar menú" : "Abrir menú"}
        className={`sm-toggle inline-flex items-center gap-2 px-4 py-2 font-mono text-[10px] uppercase tracking-widest border transition-colors ${
          open
            ? "bg-accent text-accent-foreground border-accent"
            : "bg-foreground text-background border-foreground hover:bg-accent hover:text-accent-foreground hover:border-accent"
        }`}
      >
        {triggerLabel}
        <span ref={iconRef} className="sm-icon" aria-hidden="true">
          <span className="sm-icon-line" />
          <span className="sm-icon-line sm-icon-line-v" />
        </span>
      </button>

      {createPortal(
        <>
          <div ref={preLayersRef} className="sm-prelayers" data-position={position} aria-hidden="true">
            <div className="sm-prelayer sm-prelayer-1" />
            <div className="sm-prelayer sm-prelayer-2" />
          </div>

          <aside
            id="staggered-menu-panel"
            ref={panelRef}
            className="sm-panel"
            data-position={position}
            aria-hidden={!open}
          >
            <div className="sm-panel-inner">
              {eyebrow && <div className="sm-panel-eyebrow">{eyebrow}</div>}
              <ul className="sm-panel-list" data-numbering={displayItemNumbering || undefined}>
                {items.map((item, idx) => (
                  <li className="sm-panel-itemWrap" key={item.label + idx}>
                    {item.link ? (
                      <Link href={item.link} aria-label={item.ariaLabel} className="sm-panel-item">
                        <span className="sm-panel-itemLabel">{item.label}</span>
                      </Link>
                    ) : (
                      <button
                        type="button"
                        aria-label={item.ariaLabel}
                        onClick={() => handleSelect(item)}
                        className="sm-panel-item"
                      >
                        <span className="sm-panel-itemLabel">{item.label}</span>
                      </button>
                    )}
                  </li>
                ))}
              </ul>

              {displaySocials && socialItems.length > 0 && (
                <div className="sm-socials">
                  <h3 className="sm-socials-title">Socials</h3>
                  <ul className="sm-socials-list">
                    {socialItems.map((s) => (
                      <li key={s.label}>
                        <a href={s.link} target="_blank" rel="noopener noreferrer" className="sm-socials-link">
                          {s.label}
                        </a>
                      </li>
                    ))}
                  </ul>
                </div>
              )}
            </div>
          </aside>
        </>,
        document.body,
      )}
    </>
  );
}

export default StaggeredMenu;
