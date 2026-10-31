import { useEffect, useState } from "react";
import { api } from "../api/client";
import type { Campaign } from "../types";

// Список сохранённых кампаний с редактированием основных полей и сменой статуса.
export default function CampaignList() {
  const [items, setItems] = useState<Campaign[]>([]);
  const [edit, setEdit] = useState<Campaign | null>(null);
  const [msg, setMsg] = useState<string | null>(null);

  const load = () => api.campaigns().then(setItems).catch((e) => setMsg(e.message));
  useEffect(() => { load(); }, []);

  async function save() {
    if (!edit) return;
    try {
      const r = await api.updateCampaign(edit);
      setMsg(r.problems.length ? "Сохранено, но не хватает: " + r.problems.map((p) => p.field).join(", ") : "Сохранено");
      setEdit(null);
      load();
    } catch (e) { setMsg((e as Error).message); }
  }

  async function status(id: string, s: string) {
    try { await api.setStatus(id, s); load(); } catch (e) { setMsg((e as Error).message); }
  }

  return (
    <main className="list">
      {msg && <div className="hint">{msg}</div>}
      <table>
        <thead>
          <tr><th>Название</th><th>Статус</th><th>Места</th><th>Бюджет, ₽</th><th>Даты</th><th>Показы / клики</th><th /></tr>
        </thead>
        <tbody>
          {items.map((c) => (
            <tr key={c.id}>
              <td>{c.name}</td>
              <td><span className={`status ${c.status}`}>{c.status}</span></td>
              <td>{c.placement_ids?.join(", ")}</td>
              <td>{c.budget_rub?.toLocaleString("ru-RU")}</td>
              <td>{c.start_date} — {c.end_date}</td>
              <td>{c.stats ? `${c.stats.impressions ?? 0} / ${c.stats.clicks ?? 0}` : "—"}</td>
              <td className="row">
                <button className="ghost" onClick={() => setEdit({ ...c })}>Изменить</button>
                {c.status === "ready" && <button onClick={() => status(c.id!, "moderation")}>На модерацию</button>}
                {c.status === "active" && <button className="ghost" onClick={() => status(c.id!, "paused")}>Пауза</button>}
                {c.status === "paused" && <button onClick={() => status(c.id!, "active")}>Возобновить</button>}
              </td>
            </tr>
          ))}
        </tbody>
      </table>

      {edit && (
        <div className="card editor">
          <h2>Редактирование: {edit.name}</h2>
          {(["name", "offer", "budget_rub", "start_date", "end_date", "show_hours", "landing_url"] as const).map((k) => (
            <label key={k}>
              {k}
              <input value={String(edit[k] ?? "")}
                onChange={(e) => setEdit({ ...edit, [k]: k === "budget_rub" ? Number(e.target.value) : e.target.value })} />
            </label>
          ))}
          <div className="row">
            <button onClick={save}>Сохранить</button>
            <button className="ghost" onClick={() => setEdit(null)}>Отмена</button>
          </div>
        </div>
      )}
    </main>
  );
}
