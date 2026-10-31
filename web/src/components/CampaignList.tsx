import { useEffect, useState } from "react";
import { api } from "../api";
import type { CampaignListItem, Dicts } from "../types";
import { StateBadge } from "./CampaignView";
import { fmtDate, plural } from "../checklist";
import { STATE_RU, topicLabel } from "../ru";
import { IconShield } from "./Icons";

interface Props { dicts: Dicts | null; query: string; onOpen: (id: number) => void }

export default function CampaignList({ dicts, query, onOpen }: Props) {
  const [items, setItems] = useState<CampaignListItem[]>([]);
  const [error, setError] = useState<string | null>(null);
  const [topic, setTopic] = useState("");

  useEffect(() => { api.campaigns().then(setItems).catch((e: Error) => setError(e.message)); }, []);

  const q = query.trim().toLowerCase();
  // Поиск по названию, тематике (по-русски) и статусу; несколько слов — все должны совпасть.
  const shown = items.filter((c) => {
    if (topic && c.topic !== topic) return false;
    if (!q) return true;
    const hay = `${c.name} ${topicLabel(c.topic, dicts)} ${STATE_RU[c.state] ?? ""} ${c.published ? "показы идут" : ""}`.toLowerCase();
    return q.split(/\s+/).every((w) => hay.includes(w));
  });

  return (
    <div className="page">
      <div className="page-head">
        <div>
          <div className="eyebrow">{items.length} {plural(items.length, "кампания", "кампании", "кампаний")}</div>
          <h1>Кампании</h1>
          <p className="muted">Откройте кампанию, чтобы проверить готовность к модерации, посмотреть креативы и историю изменений.</p>
        </div>
        <label className="filter">
          <span>Тематика</span>
          <select value={topic} onChange={(e) => setTopic(e.target.value)}>
            <option value="">Все тематики</option>
            {(dicts?.topics ?? []).filter((t) => items.some((c) => c.topic === t.value)).map((t) => <option key={t.value} value={t.value}>{topicLabel(t.value, dicts)}</option>)}
          </select>
        </label>
      </div>
      {error && <div className="toast err">{error}</div>}
      <section className="panel">
        <table className="table">
          <thead><tr><th>Кампания</th><th>Статус</th><th>Тематика</th><th>Период показа</th><th /></tr></thead>
          <tbody>
            {shown.map((c) => (
              <tr key={c.id} onClick={() => onOpen(c.id)}>
                <td><b>{c.name}</b></td>
                <td><StateBadge state={c.state} published={c.published} /></td>
                <td>{topicLabel(c.topic, dicts)}</td>
                <td className="muted">{fmtDate(c.startDate)} — {c.endDate ? fmtDate(c.endDate) : "без даты окончания"}</td>
                <td><span className="pill ok"><IconShield size={13} /> Готовность</span></td>
              </tr>
            ))}
            {!shown.length && <tr><td colSpan={5} className="muted">Ничего не найдено</td></tr>}
          </tbody>
        </table>
      </section>
    </div>
  );
}
