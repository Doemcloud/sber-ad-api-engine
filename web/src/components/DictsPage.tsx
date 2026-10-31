import { CHANNEL_RU, FORMAT_RU, SEGMENT_TYPE_RU, fmtReach } from "../ru";
import type { Dicts } from "../types";

// Справочники для маркетолога: сегменты аудитории, места размещения, форматы.
export default function DictsPage({ dicts, query }: { dicts: Dicts | null; query: string }) {
  if (!dicts) return <div className="page muted">Загружаем справочники…</div>;
  const q = query.trim().toLowerCase();
  const segs = dicts.segments.filter((s) => !q || `${s.name} ${SEGMENT_TYPE_RU[s.type] ?? ""}`.toLowerCase().includes(q));
  const places = dicts.places.filter((p) => !q || p.description.toLowerCase().includes(q));
  return (
    <div className="page">
      <div className="page-head"><div><div className="eyebrow">Только просмотр</div><h1>Аудитории и размещение</h1>
        <p className="muted">Сегменты рассчитываются в системе аудиторий банка — новые здесь не создаются. Места размещения и теги ассистент может предложить добавить.</p></div></div>
      <div className="review-grid">
        <section className="panel">
          <div className="panel-head"><h3>Сегменты аудитории</h3><span className="muted small">{segs.length} из {dicts.segments.length}</span></div>
          <table className="table">
            <thead><tr><th>Сегмент</th><th>Группа</th><th>Охват</th></tr></thead>
            <tbody>{segs.map((s) => (
              <tr key={s.code} className={s.state !== "ACTIVE" ? "dim" : ""}><td>{s.name}</td><td className="muted">{SEGMENT_TYPE_RU[s.type] ?? s.type}</td>
                <td>{s.state === "ACTIVE" ? `${fmtReach(s.count)} клиентов` : <span className="counter warn">ещё рассчитывается</span>}</td></tr>))}</tbody>
          </table>
        </section>
        <div className="col side-col">
          <section className="panel">
            <div className="panel-head"><h3>Места размещения</h3></div>
            <table className="table">
              <thead><tr><th>Место</th><th>Формат</th></tr></thead>
              <tbody>{places.map((p) => (
                <tr key={p.id} className={p.state !== "ACTIVE" ? "dim" : ""}><td><b>{p.description}</b>{p.state !== "ACTIVE" && <div className="muted small">отключено</div>}</td>
                  <td>{FORMAT_RU[p.defaultBanner ?? ""] ?? "любой"}</td></tr>))}</tbody>
            </table>
          </section>
          <section className="panel">
            <div className="panel-head"><h3>Форматы баннеров</h3></div>
            <table className="table">
              <thead><tr><th>Формат</th><th>Длина текстов</th><th>Платформы</th></tr></thead>
              <tbody>{dicts.bannerTypes.map((b) => (
                <tr key={b.id}><td><b>{FORMAT_RU[b.code] ?? b.description}</b></td><td className="muted">заголовок до {b.titleMaxLength}, текст до {b.textMaxLength} символов</td>
                  <td>{b.channels.map((c) => CHANNEL_RU[c] ?? c).join(", ")}</td></tr>))}</tbody>
            </table>
          </section>
        </div>
      </div>
    </div>
  );
}
