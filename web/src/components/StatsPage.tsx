import { useEffect, useMemo, useRef, useState, type MouseEvent } from "react";
import { api } from "../api";
import { fmtDate, plural } from "../checklist";
import type { CampaignListItem, CampaignStats, Dicts, StatDay, StatShare } from "../types";
import { StateBadge } from "./CampaignView";

// Статистика кампаний: охват, показы, клики, CTR, динамика по дням и состав аудитории
// (возраст, пол, города, платформы, места размещения). Для запущенных — факт, для остальных — прогноз.

const fmt = (n: number) =>
  n >= 1_000_000 ? `${(n / 1_000_000).toLocaleString("ru-RU", { maximumFractionDigits: 1 })} млн`
    : n >= 10_000 ? `${(n / 1000).toLocaleString("ru-RU", { maximumFractionDigits: 0 })} тыс.`
      : n.toLocaleString("ru-RU");
const pct = (x: number) => `${(x * 100).toLocaleString("ru-RU", { maximumFractionDigits: 1 })}%`;
const dayLabel = (iso: string) => new Date(`${iso}T00:00:00`).toLocaleDateString("ru-RU", { day: "numeric", month: "short" });

type Metric = "impressions" | "reach" | "clicks";
const METRIC: Record<Metric, string> = { impressions: "Показы", reach: "Охват за день", clicks: "Клики" };

function Tile({ label, value, hint }: { label: string; value: string; hint?: string }) {
  return <div className="stat-tile"><div className="stat-label">{label}</div><div className="stat-value">{value}</div>{hint && <div className="stat-hint">{hint}</div>}</div>;
}

// Горизонтальные бары: одна величина — один цвет, значение у конца бара, подробности по наведению.
function Bars({ title, items, unit }: { title: string; items: StatShare[]; unit: string }) {
  const max = Math.max(...items.map((x) => x.share), 0.0001);
  return (
    <section className="panel pad stat-card">
      <h3>{title}</h3>
      <div className="bars" role="list">
        {items.map((x) => (
          <div key={x.key} className="bar-row" role="listitem" title={`${x.label}: ${pct(x.share)} · ${fmt(x.count)} ${unit}`}>
            <span className="bar-label">{x.label}</span>
            <span className="bar-track"><span className="bar-fill" style={{ width: `${(x.share / max) * 100}%` }} /></span>
            <span className="bar-value">{pct(x.share)}</span>
          </div>
        ))}
        {!items.length && <div className="muted small">Нет данных</div>}
      </div>
    </section>
  );
}

// Линия по дням: одна метрика за раз (одна ось), перекрестие и подсказка при наведении.
function Trend({ days, metric }: { days: StatDay[]; metric: Metric }) {
  const [hover, setHover] = useState<number | null>(null);
  const ref = useRef<SVGSVGElement>(null);
  const W = 720, H = 220, L = 52, R = 14, T = 14, B = 28;
  const vals = days.map((d) => d[metric]);
  const top = niceMax(Math.max(...vals, 1));
  const x = (i: number) => L + (days.length <= 1 ? 0 : (i / (days.length - 1)) * (W - L - R));
  const y = (v: number) => T + (1 - v / top) * (H - T - B);
  const path = vals.map((v, i) => `${i ? "L" : "M"}${x(i).toFixed(1)},${y(v).toFixed(1)}`).join(" ");
  const area = `${path} L${x(vals.length - 1)},${H - B} L${x(0)},${H - B} Z`;
  const ticks = [0, 0.25, 0.5, 0.75, 1].map((k) => top * k);
  const step = Math.max(1, Math.ceil(days.length / 7));

  function move(e: MouseEvent<SVGSVGElement>) {
    const r = ref.current!.getBoundingClientRect();
    const px = ((e.clientX - r.left) / r.width) * W;
    const i = Math.round(((px - L) / (W - L - R)) * (days.length - 1));
    setHover(Math.min(days.length - 1, Math.max(0, i)));
  }

  return (
    <div className="trend">
      <svg ref={ref} viewBox={`0 0 ${W} ${H}`} role="img" aria-label={`${METRIC[metric]} по дням`} onMouseMove={move} onMouseLeave={() => setHover(null)}>
        {ticks.map((t) => (
          <g key={t}>
            <line x1={L} x2={W - R} y1={y(t)} y2={y(t)} className="grid" />
            <text x={L - 8} y={y(t) + 4} className="axis" textAnchor="end">{fmt(Math.round(t))}</text>
          </g>
        ))}
        {days.map((d, i) => i % step === 0 && (
          <text key={d.date} x={x(i)} y={H - 8} className="axis" textAnchor="middle">{dayLabel(d.date)}</text>
        ))}
        <path d={area} className="area" />
        <path d={path} className="line" />
        <circle cx={x(vals.length - 1)} cy={y(vals[vals.length - 1] ?? 0)} r={4} className="dot" />
        {hover !== null && (
          <g>
            <line x1={x(hover)} x2={x(hover)} y1={T} y2={H - B} className="cross" />
            <circle cx={x(hover)} cy={y(vals[hover])} r={5} className="dot" />
          </g>
        )}
      </svg>
      {hover !== null && (
        <div className="tooltip" style={{ left: `${(x(hover) / W) * 100}%` }}>
          <b>{dayLabel(days[hover].date)}</b>
          <span>Показы: {fmt(days[hover].impressions)}</span>
          <span>Охват: {fmt(days[hover].reach)}</span>
          <span>Клики: {fmt(days[hover].clicks)}</span>
        </div>
      )}
    </div>
  );
}

function niceMax(v: number) {
  const p = Math.pow(10, Math.floor(Math.log10(v)));
  for (const m of [1, 1.5, 2, 2.5, 3, 4, 5, 6, 8, 10]) if (m * p >= v) return m * p;
  return 10 * p;
}

export default function StatsPage({ initialId, query }: { dicts: Dicts | null; initialId: number | null; query: string }) {
  const [list, setList] = useState<CampaignListItem[]>([]);
  const [id, setId] = useState<number | null>(initialId);
  const [st, setSt] = useState<CampaignStats | null>(null);
  const [metric, setMetric] = useState<Metric>("impressions");
  const [error, setError] = useState<string | null>(null);
  const [table, setTable] = useState(false);

  useEffect(() => {
    api.campaigns().then((xs) => {
      setList(xs);
      if (!id && xs.length) setId((xs.find((c) => c.published) ?? xs[0]).id); // по умолчанию — запущенная
    }).catch((e: Error) => setError(e.message));
  }, []);
  useEffect(() => { if (id) { setSt(null); api.stats(id).then(setSt).catch((e: Error) => setError(e.message)); } }, [id]);

  const q = query.trim().toLowerCase();
  const shown = useMemo(() => list.filter((c) => !q || c.name.toLowerCase().includes(q)), [list, q]);
  const cur = list.find((c) => c.id === id);
  const fact = st?.mode === "fact";

  return (
    <div className="page stats-page">
      <aside className="panel stats-list">
        <div className="panel-head"><h3>Кампании</h3><span className="muted small">{shown.length}</span></div>
        <div className="stats-items">
          {shown.map((c) => (
            <button key={c.id} className={`stats-item ${c.id === id ? "on" : ""}`} onClick={() => setId(c.id)}>
              <b>{c.name}</b>
              <span className="row"><StateBadge state={c.state} published={c.published} /></span>
            </button>
          ))}
        </div>
      </aside>

      <div className="stats-main">
        {error && <div className="toast err">{error}</div>}
        {cur && (
          <div className="page-head">
            <div>
              <div className="eyebrow">{fact ? "Факт" : "Прогноз"}{st ? ` · ${fmtDate(st.from)} — ${fmtDate(st.to)} · ${st.days} ${plural(st.days, "день", "дня", "дней")}` : ""}</div>
              <h1>{cur.name}</h1>
              {st && <p className="muted">{st.note}</p>}
            </div>
          </div>
        )}
        {!st && !error && <div className="muted">Считаем статистику…</div>}
        {st && (
          <>
            <div className="stat-tiles">
              <Tile label="Аудитория" value={fmt(st.audienceSize)} hint="подходят под таргетинг" />
              <Tile label={fact ? "Охват" : "Ожидаемый охват"} value={fmt(st.reach)} hint={`${pct(st.reach / Math.max(st.audienceSize, 1))} аудитории`} />
              <Tile label="Показы" value={fmt(st.impressions)} hint={`частота ${st.frequency.toLocaleString("ru-RU")} на клиента`} />
              <Tile label="Клики" value={fmt(st.clicks)} hint={`CTR ${st.ctr.toLocaleString("ru-RU")}%`} />
              <Tile label="Целевые действия" value={fmt(st.conversions)} hint={`${pct(st.conversions / Math.max(st.clicks, 1))} от кликов`} />
            </div>

            <section className="panel pad stat-card">
              <div className="panel-row">
                <h3>{fact ? "Динамика по дням" : "Ожидаемая динамика"}{st.daily.length < st.days ? ` · ${fact ? "последние" : "первые"} ${st.daily.length} ${plural(st.daily.length, "день", "дня", "дней")}` : ""}</h3>
                <div className="row">
                  <div className="segmented small">
                    {(Object.keys(METRIC) as Metric[]).map((m) => <button key={m} className={metric === m ? "on" : ""} onClick={() => setMetric(m)}>{METRIC[m]}</button>)}
                  </div>
                  <button className="pill" onClick={() => setTable(!table)}>{table ? "График" : "Таблица"}</button>
                </div>
              </div>
              {table ? (
                <div className="stats-table-wrap">
                  <table className="table">
                    <thead><tr><th>День</th><th>Показы</th><th>Охват</th><th>Клики</th></tr></thead>
                    <tbody>{st.daily.map((d) => <tr key={d.date}><td>{dayLabel(d.date)}</td><td>{d.impressions.toLocaleString("ru-RU")}</td><td>{d.reach.toLocaleString("ru-RU")}</td><td>{d.clicks.toLocaleString("ru-RU")}</td></tr>)}</tbody>
                  </table>
                </div>
              ) : <Trend days={st.daily} metric={metric} />}
            </section>

            <div className="stat-grid">
              <Bars title="Возраст" items={st.age} unit="клиентов" />
              <Bars title="Пол" items={st.gender} unit="клиентов" />
              <Bars title="Города" items={st.cities} unit="клиентов" />
              <Bars title="Платформы" items={st.platforms} unit="показов" />
              <Bars title="Места размещения" items={st.places} unit="показов" />
            </div>
          </>
        )}
      </div>
    </div>
  );
}
