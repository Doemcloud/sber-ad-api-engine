import { IconBot, IconChart, IconDatabase, IconGrid, IconLogout, IconSearch, IconSettings, IconShield } from "./Icons";

export type Page = "assistant" | "moderation" | "campaigns" | "review" | "stats" | "dicts" | "settings";
import type { Role } from "../types";

type NavItem = { page: Page; title: string; Icon: (p: { size?: number }) => JSX.Element };
// У менеджера и модератора разные кабинеты: менеджер заводит кампании с ассистентом,
// модератор работает с очередью проверки. Переписка с ассистентом — только у менеджера.
const NAV: Record<Role, NavItem[]> = {
  campaignManager: [
    { page: "assistant", title: "Ассистент", Icon: IconBot },
    { page: "campaigns", title: "Кампании", Icon: IconGrid },
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

// Боковое меню: в покое — иконки, при наведении на любую его часть плавно раскрывается
// поверх рабочей области и показывает подписи (раскладка страницы при этом не прыгает).
export function Sidebar({ page, role, onNavigate }: { page: Page; role: Role; onNavigate: (p: Page) => void }) {
  return (
    <aside className="sidebar">
      <div className="sidebar-panel">
        <div className="side-row brand-row" title="Рекламный кабинет СберБанк Онлайн">
          <div className="brand">С</div>
          <div className="side-label brand-label"><b>Рекламный кабинет</b><span>СберБанк Онлайн</span></div>
        </div>
        <nav>
          {NAV[role].map(({ page: p, title, Icon }) => (
            <button key={p} className={`nav-btn ${page === p ? "active" : ""}`} aria-label={title} onClick={() => onNavigate(p)}>
              <span className="nav-icon"><Icon size={20} /></span>
              <span className="side-label">{title}</span>
            </button>
          ))}
        </nav>
        <button className={`nav-btn bottom ${page === "settings" ? "active" : ""}`} aria-label="Настройки" onClick={() => onNavigate("settings")}>
          <span className="nav-icon"><IconSettings size={20} /></span>
          <span className="side-label">Настройки</span>
        </button>
      </div>
    </aside>
  );
}


const CRUMB: Record<Page, string> = { assistant: "Ассистент", moderation: "Очередь модерации", campaigns: "Кампании", review: "Проверка кампании", stats: "Статистика", dicts: "Аудитории и размещение", settings: "Настройки" };

interface TopbarProps {
  page: Page;
  name: string;
  title: string;
  query: string;
  onQuery: (q: string) => void;
  onLogout: () => void;
}

const initials = (n: string) => n.split(/\s+/).filter(Boolean).slice(0, 2).map((w) => w[0]).join("").toUpperCase();

export function Topbar({ page, name, title, query, onQuery, onLogout }: TopbarProps) {
  return (
    <div className="topbar">
      <div className="crumbs"><span className="muted">Рекламный кабинет СберБанк Онлайн</span><span className="sep">/</span><b>{CRUMB[page]}</b></div>
      <label className="search">
        <IconSearch size={16} />
        <input value={query} onChange={(e) => onQuery(e.target.value)} placeholder="Поиск кампаний, сегментов, мест размещения" />
      </label>
      <div className="me">
        <div className="me-text"><b>{name}</b><span>{title}</span></div>
        <span className="avatar">{initials(name)}</span>
        <button className="logout" onClick={onLogout} title="Выйти" aria-label="Выйти"><IconLogout size={18} /></button>
      </div>
    </div>
  );
}
