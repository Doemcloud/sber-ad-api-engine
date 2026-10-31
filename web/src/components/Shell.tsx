import type { Role } from "../types";
import { IconBot, IconDatabase, IconGrid, IconSearch, IconSettings, IconShield } from "./Icons";

export type Page = "assistant" | "campaigns" | "review" | "dicts";

const NAV: { page: Page; title: string; Icon: (p: { size?: number }) => JSX.Element }[] = [
  { page: "assistant", title: "Ассистент", Icon: IconBot },
  { page: "campaigns", title: "Кампании", Icon: IconGrid },
  { page: "review", title: "Готовность к модерации", Icon: IconShield },
  { page: "dicts", title: "Аудитории и размещение", Icon: IconDatabase },
];

// Боковое меню: в покое — иконки, при наведении на любую его часть плавно раскрывается
// поверх рабочей области и показывает подписи (раскладка страницы при этом не прыгает).
export function Sidebar({ page, onNavigate }: { page: Page; onNavigate: (p: Page) => void }) {
  return (
    <aside className="sidebar">
      <div className="sidebar-panel">
        <div className="side-row brand-row" title="Рекламный кабинет СберБанк Онлайн">
          <div className="brand">С</div>
          <div className="side-label brand-label"><b>Рекламный кабинет</b><span>СберБанк Онлайн</span></div>
        </div>
        <nav>
          {NAV.map(({ page: p, title, Icon }) => (
            <button key={p} className={`nav-btn ${page === p ? "active" : ""}`} aria-label={title} onClick={() => onNavigate(p)}>
              <span className="nav-icon"><Icon size={20} /></span>
              <span className="side-label">{title}</span>
            </button>
          ))}
        </nav>
        <button className="nav-btn bottom" aria-label="Настройки" disabled>
          <span className="nav-icon"><IconSettings size={20} /></span>
          <span className="side-label">Настройки</span>
        </button>
      </div>
    </aside>
  );
}

export const USERS: Record<Role, { user: string; initials: string; label: string }> = {
  campaignManager: { user: "ivanov.p", initials: "ПИ", label: "Павел Иванов · менеджер" },
  campaignModerator: { user: "petrova.m", initials: "МП", label: "Мария Петрова · модератор" },
};

const CRUMB: Record<Page, string> = { assistant: "Ассистент", campaigns: "Кампании", review: "Готовность к модерации", dicts: "Аудитории и размещение" };

interface TopbarProps {
  page: Page;
  role: Role;
  query: string;
  onQuery: (q: string) => void;
  onRole: (r: Role) => void;
}

export function Topbar({ page, role, query, onQuery, onRole }: TopbarProps) {
  return (
    <div className="topbar">
      <div className="crumbs"><span className="muted">Рекламный кабинет СберБанк Онлайн</span><span className="sep">/</span><b>{CRUMB[page]}</b></div>
      <label className="search">
        <IconSearch size={16} />
        <input value={query} onChange={(e) => onQuery(e.target.value)} placeholder="Поиск кампаний, сегментов, мест размещения" />
      </label>
      <label className="role" title="Роль определяет доступные действия">
        <select value={role} onChange={(e) => onRole(e.target.value as Role)}>
          {(Object.keys(USERS) as Role[]).map((r) => <option key={r} value={r}>{USERS[r].label}</option>)}
        </select>
        <span className="avatar">{USERS[role].initials}</span>
      </label>
    </div>
  );
}
