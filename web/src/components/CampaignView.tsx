import { useEffect, useState } from "react";
import { api } from "../api";
import { fmtPeriod } from "../checklist";
import { AUDIT_ACTION_RU, CHANNEL_RU, ENTITY_RU, FIELD_RU, FORMAT_RU, STATE_RU, fmtDateTime, fmtReach, humanize, person, topicLabel } from "../ru";
import type { ApiErrorItem, AuditEntry, CampaignDetails, Dicts, Validation } from "../types";
import { BannerPreview, Phone, PromoPreview } from "./Previews";

// Служебные поля шапки, которые в кабинете не показываются (очерёдность показа решает система банка).
const HIDDEN_FIELDS = new Set(["weight", "initialCtr"]);

/** Подписи статусов (оставлено для совместимости импорта). */
export const STATE_LABEL = STATE_RU;

export function StateBadge({ state, published }: { state: string; published?: boolean }) {
  return (
    <span className="badges">
      <span className={`badge st-${state}`}>{STATE_RU[state] ?? state}</span>
      {published && <span className="badge live">показы идут</span>}
    </span>
  );
}

interface Props {
  campaign: CampaignDetails;
  dicts: Dicts | null;
  validation?: Validation;
  refreshKey?: unknown;
  onOpenInChat?: () => void;
}


export default function CampaignView({ campaign: c, dicts, validation, refreshKey, onOpenInChat }: Props) {
  const [audit, setAudit] = useState<AuditEntry[]>([]);
  const [val, setVal] = useState<Validation | undefined>(validation);

  useEffect(() => {
    api.audit(c.id).then(setAudit).catch(() => setAudit([]));
    if (validation) setVal(validation);
    else api.warnings(c.id).then(setVal).catch(() => undefined);
  }, [c.id, refreshKey, validation]);

  const place = (id: number) => dicts?.places.find((p) => p.id === id);
  const seg = (code: string) => dicts?.segments.find((s) => s.code === code);
  const format = (id: number) => dicts?.bannerTypes.find((b) => b.id === id)?.code ?? "";
  const tags = c.tags.map((t) => dicts?.tags.find((x) => x.id === t)?.name ?? `тег ${t}`);
  const lastDecline = [...audit].reverse().find((a) => a.action === "DECLINE");
  const warnList: ApiErrorItem[] = val?.warningDetails?.length ? val.warningDetails : (val?.warnings ?? []).map((w) => ({ code: "", message: w }));

  return (
    <div className="campaign">
      <div className="card">
        <div className="card-head">
          <div>
            <h2>{c.name}</h2>
            {c.marketingName && <div className="muted">Рекламное название: {c.marketingName}</div>}
          </div>
          <StateBadge state={c.state} published={c.published} />
        </div>
        {c.state === "NEEDS_WORK" && lastDecline?.comment && (
          <div className="notice warn"><b>Комментарий модератора ({person(lastDecline.actor)}):</b> {lastDecline.comment}</div>
        )}
        <dl className="fields">
          <dt>Период</dt><dd>{fmtPeriod(c)} (UTC)</dd>
          <dt>Тематика</dt><dd>{topicLabel(c.topic, dicts)}</dd>
          <dt>Теги</dt><dd>{tags.length ? tags.join(", ") : <span className="muted">нет</span>}</dd>
          {c.keywords && <><dt>Ключевые слова</dt><dd>{c.keywords.split(";").join(", ")}</dd></>}
          <dt>Аудитория</dt>
          <dd>
            {c.audienceType === "ALL_USERS" ? "Все клиенты" : (
              <div className="segs">
                {c.segments.included.map((code) => <span key={code} className="chip in">{seg(code)?.name ?? code} · {fmtReach(seg(code)?.count ?? 0)}</span>)}
                {c.segments.excluded.map((code) => <span key={code} className="chip out">без: {(seg(code)?.name ?? code).replace("Исключение. ", "").toLowerCase()}</span>)}
                {!c.segments.included.length && <span className="muted">сегменты не выбраны</span>}
              </div>
            )}
          </dd>
          <dt>Размещение</dt>
          <dd>
            {c.places.map((id) => {
              const p = place(id);
              return <span key={id} className={`chip ${p?.state === "INACTIVE" ? "off" : ""}`}>{p?.description ?? `место ${id}`} <small>{FORMAT_RU[p?.defaultBanner ?? ""]?.toLowerCase()}</small></span>;
            })}
            {!c.places.length && <span className="muted">не выбрано</span>}
          </dd>
          <dt>Менеджер</dt><dd>{person(c.author)}{c.lastEditAuthor !== c.author && `, последние правки — ${person(c.lastEditAuthor)}`}</dd>
        </dl>
      </div>

      {val && (val.errors.length > 0 || warnList.length > 0) && (
        <div className="card">
          <h3>Проверка</h3>
          {val.errors.map((e, i) => <div key={i} className="notice err">{humanize(e.message, dicts)}{e.hint && <div className="hint">{humanize(e.hint, dicts)}</div>}</div>)}
          {warnList.map((w, i) => <div key={i} className="notice warn">{w.message}{w.hint && <div className="hint">{humanize(w.hint, dicts)}</div>}</div>)}
        </div>
      )}
      {val && val.errors.length === 0 && warnList.length === 0 && <div className="notice ok">Ошибок и замечаний нет — кампанию можно отправлять на модерацию.</div>}

      <div className="card">
        <h3>Как увидит клиент</h3>
        {c.banners.length === 0 && <div className="muted">Баннеров пока нет.</div>}
        <div className="previews">
          {c.banners.map((b) => {
            const f = format(b.bannerTypeId);
            const crs = c.creatives.filter((x) => x.bannerId === b.id);
            const content = c.contents.find((x) => crs.some((cr) => cr.contentId === x.id));
            return (
              <div key={b.id} className="creative-group">
                <Phone label={`${FORMAT_RU[f] ?? "Баннер"} «${b.name}»`}><BannerPreview type={f} content={b.content} /></Phone>
                {content && <Phone label={`Промо-экран «${content.name}»`}><PromoPreview content={content.content} /></Phone>}
                <div className="channels">
                  {crs.length ? crs.map((cr) => <span key={cr.id} className="chip">{CHANNEL_RU[cr.channelCode] ?? cr.channelCode}</span>) : <span className="muted">не размещён</span>}
                </div>
              </div>
            );
          })}
        </div>
      </div>

      <div className="card">
        <h3>История изменений</h3>
        <ol className="audit">
          {[...audit].reverse().map((a) => (
            <li key={a.id}>
              <span className="muted">{fmtDateTime(a.at)}</span> <b>{person(a.actor)}</b> — {ENTITY_RU[a.entity] ?? a.entity}: {AUDIT_ACTION_RU[a.action] ?? a.action}
              {a.comment && <div className="comment">«{a.comment}»</div>}
              {a.changes && Object.keys(a.changes).some((k) => !HIDDEN_FIELDS.has(k)) && <div className="muted small">изменено: {Object.keys(a.changes).filter((k) => !HIDDEN_FIELDS.has(k)).map((k) => FIELD_RU[k] ?? k).join(", ")}</div>}
            </li>
          ))}
        </ol>
      </div>
      {onOpenInChat && <button onClick={onOpenInChat}>Продолжить с ассистентом</button>}
    </div>
  );
}
