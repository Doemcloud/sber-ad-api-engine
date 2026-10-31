import { useEffect, useRef, useState } from "react";
import type { Role } from "../types";
import { describe, when, type FeedEntry } from "../events";
import {
  IconBell, IconBot, IconChart, IconClose, IconDatabase, IconGrid, IconHome, IconLogout, IconMenu, IconPlus,
  IconSearch, IconSettings, IconShield,
} from "./Icons";

export type Page = "home" | "new" | "assistant" | "moderation" | "campaigns" | "review" | "stats" | "dicts" | "settings";

type NavItem = { page: Page; title: string; Icon: (p: { size?: number }) => JSX.Element };
// У менеджера и модератора разные кабинеты: менеджер заводит кампании (мастер и ассистент),
// модератор работает с очередью проверки. Переписка с ассистентом — только у менеджера.
export const NAV: Record<Role, NavItem[]> = {
  campaignManager: [
    { page: "home", title: "Главная", Icon: IconHome },
    { page: "new", title: "Новая кампания", Icon: IconPlus },
    { page: "assistant", title: "Ассистент", Icon: IconBot },
    { page: "campaigns", title: "Мои кампании", Icon: IconGrid },
    { page: "review", title: "Готовность к модерации", Icon: IconShield },
    { page: "stats", title: "Статистика", Icon: IconChart },
    { page: "dicts", title: "Аудитории и размещение", Icon: IconDatabase },
  ],
  campaignModerator: [
    { page: "moderation", title: "Очередь модерации", Icon: IconShield },
    { page: "campaigns", title: "Все кампании", Icon: IconGrid },
    { page: "stats", title: "Статистика", Icon: IconChart },
  ],
};

// Выдвижное меню: полоска иконок видна всегда, по наведению или кнопке ☰ выезжает целиком.
export function Sidebar({ page, role, open, onClose, onNavigate }: {
  page: Page; role: Role; open: boolean; onClose: () => void; onNavigate: (p: Page) => void;
}) {
  const go = (p: Page) => { onNavigate(p); onClose(); };
  return (
    <>
      {open && <div className="sidebar-overlay" onClick={onClose} />}
      <aside className={`sidebar ${open ? "open" : ""}`} aria-label="Навигация">
        <div className="sidebar-header">
          <strong>Навигация</strong>
          <button className="sidebar-close" onClick={onClose} aria-label="Закрыть меню"><IconClose size={16} /></button>
        </div>
        <nav className="sidebar-nav">
          {NAV[role].map(({ page: p, title, Icon }) => (
            <button key={p} className={`sidebar-link ${page === p ? "active" : ""}`} aria-label={title} aria-current={page === p ? "page" : undefined} onClick={() => go(p)}>
              <span className="nav-icon"><Icon size={19} /></span>
              <span className="side-label">{title}</span>
            </button>
          ))}
        </nav>
        <div className="sidebar-bottom">
          <button className={`sidebar-link ${page === "settings" ? "active" : ""}`} aria-label="Настройки" onClick={() => go("settings")}>
            <span className="nav-icon"><IconSettings size={19} /></span>
            <span className="side-label">Настройки</span>
          </button>
        </div>
      </aside>
    </>
  );
}

const initials = (n: string) => n.split(/\s+/).filter(Boolean).slice(0, 2).map((w) => w[0]).join("").toUpperCase();

interface TopbarProps {
  name: string;
  title: string;
  query: string;
  onQuery: (q: string) => void;
  onLogout: () => void;
  onMenu: () => void;
  onHome: () => void;
  notifications: FeedEntry[];
  unread: number;
  onOpenNotifications: () => void;
  onOpenEvent: (e: FeedEntry) => void;
}

export function Topbar(p: TopbarProps) {
  const [open, setOpen] = useState(false);
  const box = useRef<HTMLDivElement>(null);
  useEffect(() => {
    if (!open) return;
    const close = (e: MouseEvent) => { if (!box.current?.contains(e.target as Node)) setOpen(false); };
    const esc = (e: KeyboardEvent) => { if (e.key === "Escape") setOpen(false); };
    document.addEventListener("click", close);
    document.addEventListener("keydown", esc);
    return () => { document.removeEventListener("click", close); document.removeEventListener("keydown", esc); };
  }, [open]);

  return (
    <header className="topbar">
      <div className="topbar-left">
        <button className="menu-toggle" onClick={p.onMenu} aria-label="Открыть меню"><IconMenu size={20} /></button>
        <button className="brand-link" onClick={p.onHome}><span className="brand-icon">✦</span><span>Campaign AI</span></button>
        <span className="company-name">Личный кабинет предприятия</span>
      </div>
      <label className="search">
        <IconSearch size={16} />
        <input value={p.query} onChange={(e) => p.onQuery(e.target.value)} placeholder="Поиск кампаний, тематик, статусов" />
      </label>
      <div className="notification-wrapper" ref={box}>
        <button className="icon-btn" aria-label="Открыть уведомления" aria-expanded={open}
          onClick={(e) => { e.stopPropagation(); setOpen(!open); if (!open) p.onOpenNotifications(); }}>
          <IconBell size={21} />
          {p.unread > 0 && <span className="notification-count">{p.unread > 9 ? "9+" : p.unread}</span>}
        </button>
        {open && (
          <div className="notification-dropdown" role="dialog" aria-label="Уведомления">
            <h3>Уведомления</h3>
            {p.notifications.length === 0 && <div className="notification-empty">Новых событий нет</div>}
            {p.notifications.slice(0, 8).map((e) => {
              const v = describe(e);
              return (
                <button key={e.id} className="notification-item" onClick={() => { setOpen(false); p.onOpenEvent(e); }}>
                  <span className={`event-indicator ${v.tone}`} />
                  <span>{v.text}<small>{when(e.at)}</small></span>
                </button>
              );
            })}
          </div>
        )}
      </div>
      <div className="me">
        <div className="me-text"><b>{p.name}</b><span>{p.title}</span></div>
        <span className="avatar">{initials(p.name)}</span>
        <button className="logout" onClick={p.onLogout} title="Выйти" aria-label="Выйти"><IconLogout size={18} /></button>
      </div>
    </header>
  );
}

export function Footer({ role, onNavigate, onProblem }: { role: Role; onNavigate: (p: Page) => void; onProblem?: () => void }) {
  return (
    <footer className="footer">
      <nav className="footer-links">
        {NAV[role].filter((n) => n.page !== "review").map((n) => <button key={n.page} onClick={() => onNavigate(n.page)}>{n.title}</button>)}
        <button onClick={() => onNavigate("settings")}>Настройки</button>
      </nav>
      {onProblem && <button className="problem-button" onClick={onProblem}>Возникла проблема</button>}
    </footer>
  );
}

// Кнопка прокрутки: вниз, пока не долистали; наверх, когда страница прокручена.
export function ScrollButton({ target }: { target: HTMLElement | null }) {
  const [dir, setDir] = useState<"top" | "bottom" | null>(null);
  useEffect(() => {
    if (!target) { setDir(null); return; }
    const upd = () => {
      const scrollable = target.scrollHeight > target.clientHeight + 120;
      if (!scrollable) { setDir(null); return; }
      const nearBottom = target.scrollTop + target.clientHeight >= target.scrollHeight - 100;
      setDir(target.scrollTop > 180 && !nearBottom ? "top" : nearBottom ? "top" : "bottom");
    };
    upd();
    target.addEventListener("scroll", upd);
    const ro = new ResizeObserver(upd);
    ro.observe(target);
    return () => { target.removeEventListener("scroll", upd); ro.disconnect(); };
  }, [target]);
  if (!dir || !target) return null;
  return (
    <button className="scroll-button" aria-label={dir === "top" ? "Наверх" : "Вниз"}
      onClick={() => target.scrollTo({ top: dir === "top" ? 0 : target.scrollHeight, behavior: "smooth" })}>
      {dir === "top" ? "↑" : "↓"}
    </button>
  );
}
