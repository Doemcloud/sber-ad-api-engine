import { useEffect, useMemo, useState, type ReactNode } from "react";
import { api } from "../api";
import { describe, when, type FeedEntry } from "../events";
import type { CampaignListItem, CampaignStats } from "../types";

// «Главная» менеджера: сравнение запущенных кампаний, события, история изменений, баланс показов.
type Metric = "reach" | "impressions" | "clicks";
const METRIC: Record<Metric, string> = { reach: "По количеству просмотров", impressions: "Показы", clicks: "Клики" };
const QUOTA = 150_000_000; // демо: выделено показов на месяц для кабинета
const IMPORTANT = new Set(["DECLINE", "APPROVE", "ACTIVATE", "TO_MODERATION", "STOP", "RESUME_REQUEST"]);

const fmt = (n: number) => new Intl.NumberFormat("ru-RU").format(n);
const compact = (n: number) =>
  n >= 1_000_000 ? `${(n / 1_000_000).toLocaleString("ru-RU", { maximumFractionDigits: 1 })} млн`
    : n >= 10_000 ? `${Math.round(n / 1000).toLocaleString("ru-RU")} тыс.` : fmt(n);

interface Props {
  feed: FeedEntry[];
  onOpenCampaign: (id: number) => void;
  onNavigate: (p: "stats" | "campaigns" | "new") => void;
  children?: ReactNode; // футер
}

export default function HomePage({ feed, onOpenCampaign, onNavigate, children }: Props) {
  const [list, setList] = useState<CampaignListItem[]>([]);
  const [stats, setStats] = useState<Record<number, CampaignStats>>({});
  const [month, setMonth] = useState<Record<number, CampaignStats>>({});
  const [metric, setMetric] = useState<Metric>("reach");
  const [filter, setFilter] = useState<"all" | "active">("all");
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    api.campaigns().then(async (xs) => {
      setList(xs);
      const launched = xs.filter((c) => c.published || c.state === "STOPPED");
      const [all, m] = await Promise.all([
        Promise.all(launched.map((c) => api.stats(c.id, "all").catch(() => null))),
        Promise.all(launched.filter((c) => c.published).map((c) => api.stats(c.id, "month").catch(() => null))),
      ]);
      setStats(Object.fromEntries(all.filter(Boolean).map((s) => [s!.campaignId, s!])));
      setMonth(Object.fromEntries(m.filter(Boolean).map((s) => [s!.campaignId, s!])));
    }).catch((e: Error) => setError(e.message));
  }, []);

  const bars = useMemo(() => list
    .filter((c) => stats[c.id] && (filter === "all" || c.published))
    .map((c) => ({ id: c.id, name: c.name, live: c.published, value: stats[c.id][metric] }))
    .sort((a, b) => b.value - a.value), [list, stats, metric, filter]);
  const max = Math.max(...bars.map((b) => b.value), 1);

  const used = Object.values(month).reduce((s, x) => s + x.impressions, 0);
  const left = Math.max(QUOTA - used, 0);
  const pct = Math.min(100, Math.round((used / QUOTA) * 100));

  const events = feed.filter((e) => IMPORTANT.has(e.action)).slice(0, 5);
  const history = feed.slice(0, 7);
  const counts = {
    live: list.filter((c) => c.published).length,
    review: list.filter((c) => c.state === "ON_MODERATION").length,
    work: list.filter((c) => c.state === "NEEDS_WORK").length,
  };

  return (
    <div className="page home">
      <section className="page-heading">
        <h1>Главная</h1>
        <p>Контроль рекламных кампаний и выделенных показов</p>
      </section>
      {error && <div className="toast err">{error}</div>}

      <div className="dashboard-grid">
        <div className="main-column">
          <section className="card statistics-card">
            <div className="card-header">
              <div><h2>Статистика</h2><p>Сравнение запущенных рекламных кампаний</p></div>
            </div>
            <div className="statistics-filters">
              <label>Показатель
                <select value={metric} onChange={(e) => setMetric(e.target.value as Metric)}>
                  {(Object.keys(METRIC) as Metric[]).map((m) => <option key={m} value={m}>{METRIC[m]}</option>)}
                </select>
              </label>
              <label>Кампании
                <select value={filter} onChange={(e) => setFilter(e.target.value as "all" | "active")}>
                  <option value="all">Все запущенные кампании</option>
                  <option value="active">Только активные</option>
                </select>
              </label>
            </div>
            <div className="campaign-chart" role="list" aria-label={METRIC[metric]}>
              {bars.length === 0 && <div className="statistics-empty">{Object.keys(stats).length ? "Нет кампаний под фильтр" : "Данные статистики загружаются…"}</div>}
              {bars.map((b) => (
                <button key={b.id} className="campaign-bar-group" role="listitem" onClick={() => onOpenCampaign(b.id)}
                  title={`${b.name}: ${fmt(b.value)}${b.live ? "" : " (показы остановлены)"}`}>
                  <span className="campaign-bar-value">{compact(b.value)}</span>
                  <span className={`campaign-bar ${b.live ? "" : "stopped"}`} style={{ height: `${Math.max((b.value / max) * 190, 8)}px` }} />
                  <span className="campaign-bar-name">{b.name}</span>
                </button>
              ))}
            </div>
            <div className="statistics-note">
              Демо-данные: статистика моделируется по аудитории и размещению кампаний. Серые столбцы — остановленные кампании.
            </div>
            <div className="card-footer"><button className="secondary-button" onClick={() => onNavigate("stats")}>К статистике</button></div>
          </section>

          <section className="card">
            <div className="card-header"><div><h2>События</h2><p>Последние изменения и уведомления</p></div></div>
            <div className="event-list">
              {events.length === 0 && <div className="statistics-empty">Событий пока нет</div>}
              {events.map((e) => {
                const v = describe(e);
                return (
                  <button key={e.id} className="event-item" onClick={() => onOpenCampaign(e.campaignId)}>
                    <span className={`event-indicator ${v.tone}`} />
                    <span>{v.text}{e.comment && e.action === "DECLINE" ? `: «${e.comment}»` : ""}<small>{when(e.at)}</small></span>
                  </button>
                );
              })}
            </div>
            <div className="card-footer"><button className="secondary-button" onClick={() => onNavigate("campaigns")}>Ко всем рекламным кампаниям</button></div>
          </section>

          <section className="card">
            <div className="card-header"><div><h2>История изменений</h2><p>Последние действия в личном кабинете</p></div></div>
            <div className="history-list">
              {history.map((e) => {
                const v = describe(e);
                return (
                  <button key={e.id} className="history-row" onClick={() => onOpenCampaign(e.campaignId)}>
                    <span className="history-date">{when(e.at)}</span>
                    <span>{v.text}</span>
                    <span className={`status ${v.tone}`}>{v.status}</span>
                  </button>
                );
              })}
            </div>
          </section>
        </div>

        <aside className="side-column">
          <section className="card balance-card">
            <div className="card-header"><div><h2>Баланс показов</h2><p>Выделено на рекламные кампании в этом месяце</p></div></div>
            <div className="balance-value">{compact(left)}</div>
            <div className="balance-label">доступных показов</div>
            <div className="balance-progress"><span style={{ width: `${pct}%` }} /></div>
            <div className="balance-caption"><span>Использовано {compact(used)}</span><span>{pct}%</span></div>
          </section>
          <section className="card summary-card">
            <h2>Кампании</h2>
            <button className="summary-row" onClick={() => onNavigate("campaigns")}><span>Показы идут</span><b>{counts.live}</b></button>
            <button className="summary-row" onClick={() => onNavigate("campaigns")}><span>На модерации</span><b>{counts.review}</b></button>
            <button className="summary-row warn" onClick={() => onNavigate("campaigns")}><span>Нужны правки</span><b>{counts.work}</b></button>
            <button className="primary-button wide" onClick={() => onNavigate("new")}>＋ Новая кампания</button>
          </section>
        </aside>
      </div>
      {children}
    </div>
  );
}
