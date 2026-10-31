import { useEffect, useState } from "react";
import { api } from "../api";
import { fmtDate, plural } from "../checklist";
import { topicLabel } from "../ru";
import type { CampaignListItem, Dicts } from "../types";
import { StateBadge } from "./CampaignView";
import { IconShield } from "./Icons";

// Кабинет модератора: очередь кампаний, ждущих решения, и недавно рассмотренные.
export default function ModerationPage({ dicts, query, onOpen }: { dicts: Dicts | null; query: string; onOpen: (id: number) => void }) {
  const [items, setItems] = useState<CampaignListItem[] | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [resumes, setResumes] = useState<Set<number>>(new Set());
  useEffect(() => {
    api.campaigns().then(async (xs) => {
      setItems(xs);
      // какие из ждущих — запросы на возобновление остановленных кампаний
      const onMod = xs.filter((c) => c.state === "ON_MODERATION");
      const logs = await Promise.all(onMod.map((c) => api.audit(c.id).catch(() => [])));
      const ids = onMod.filter((_, i) => [...logs[i]].reverse().find((a) => a.action === "RESUME_REQUEST" || a.action === "TO_MODERATION")?.action === "RESUME_REQUEST").map((c) => c.id);
      setResumes(new Set(ids));
    }).catch((e: Error) => setError(e.message));
  }, []);

  const q = query.trim().toLowerCase();
  const match = (c: CampaignListItem) => !q || `${c.name} ${topicLabel(c.topic, dicts)}`.toLowerCase().includes(q);
  const queue = (items ?? []).filter((c) => c.state === "ON_MODERATION" && match(c));
  const done = (items ?? []).filter((c) => ["APPROVED", "NEEDS_WORK"].includes(c.state) && match(c));

  const table = (rows: CampaignListItem[], cta: string) => (
    <table className="table">
      <thead><tr><th>Кампания</th><th>Статус</th><th>Тематика</th><th>Период показа</th><th /></tr></thead>
      <tbody>
        {rows.map((c) => (
          <tr key={c.id} onClick={() => onOpen(c.id)}>
            <td><b>{c.name}</b>{resumes.has(c.id) && <div className="muted small">запрос на возобновление показов</div>}</td>
            <td><StateBadge state={c.state} published={c.published} /></td>
            <td>{topicLabel(c.topic, dicts)}</td>
            <td className="muted">{fmtDate(c.startDate)} — {c.endDate ? fmtDate(c.endDate) : "без даты окончания"}</td>
            <td><span className="pill ok"><IconShield size={13} /> {cta}</span></td>
          </tr>
        ))}
        {!rows.length && <tr><td colSpan={5} className="muted">{items ? "Пусто" : "Загружаем…"}</td></tr>}
      </tbody>
    </table>
  );

  return (
    <div className="page">
      <div className="page-head">
        <div>
          <div className="eyebrow">{queue.length} {plural(queue.length, "кампания ждёт", "кампании ждут", "кампаний ждут")} решения</div>
          <h1>Очередь модерации</h1>
          <p className="muted">Откройте кампанию, проверьте креативы, аудиторию и размещение — затем одобрите или верните менеджеру с комментарием.</p>
        </div>
      </div>
      {error && <div className="toast err">{error}</div>}
      <section className="panel">{table(queue, "Проверить")}</section>
      <h3 className="block-title">Недавно рассмотренные</h3>
      <section className="panel">{table(done, "Открыть")}</section>
    </div>
  );
}
