import type { Campaign } from "../types";

const FIELDS: [keyof Campaign, string][] = [
  ["name", "Название"],
  ["advertiser_id", "Рекламодатель"],
  ["goal", "Цель"],
  ["object", "Объект рекламы"],
  ["offer", "Оффер"],
  ["target_client", "Конечный клиент"],
  ["segment_ids", "Сегменты"],
  ["placement_ids", "Места показа"],
  ["budget_rub", "Бюджет, ₽"],
  ["start_date", "Начало"],
  ["end_date", "Окончание"],
  ["show_hours", "Часы показа"],
  ["frequency_cap_per_day", "Показов в день на клиента"],
  ["landing_url", "Ссылка"],
];

const SOURCE_LABEL: Record<string, string> = { request: "из запроса", ai: "ИИ", asked: "уточнено", system: "система" };

function show(v: unknown): string {
  if (v === undefined || v === null || v === "") return "—";
  if (Array.isArray(v)) return v.join(", ");
  return String(v);
}

export default function CampaignCard({ draft, missing }: { draft: Campaign; missing: string[] }) {
  const sources = draft.field_sources ?? {};
  return (
    <div className="card">
      <div className="card-head">
        <h2>Карточка кампании</h2>
        {draft.status && <span className={`status ${draft.status}`}>{draft.status}</span>}
      </div>
      <dl>
        {FIELDS.map(([key, label]) => {
          const k = String(key);
          const isMissing = missing.includes(k);
          const src = sources[k];
          return (
            <div key={k} className={`field ${isMissing ? "missing" : ""} ${src === "ai" ? "ai" : ""}`}>
              <dt>{label}</dt>
              <dd>
                {show(draft[key])}
                {src && <span className="src">{SOURCE_LABEL[src] ?? src}</span>}
              </dd>
            </div>
          );
        })}
      </dl>
      {missing.length > 0 && <p className="hint">Не хватает: {missing.join(", ")}</p>}
      {draft.id && <p className="hint">Сохранено в БД: {draft.id}</p>}
    </div>
  );
}
