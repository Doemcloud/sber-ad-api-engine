import { useEffect, useMemo, useState } from "react";
import { actions, api, type Who } from "../api";
import { buildChecklist, counts, EDITABLE_FOR_SUBMIT, fmtPeriod, plural, type CheckItem, type Status } from "../checklist";
import { AUDIT_ACTION_RU, CHANNEL_RU, ENTITY_RU, FORMAT_RU, STATE_RU, fmtDateTime, fmtReach, person } from "../ru";
import type { AuditEntry, CampaignDetails, Dicts, Validation } from "../types";
import { IconAlertCircle, IconAlertTriangle, IconArrowLeft, IconCheck, IconClock, IconGlobe, IconInfo, IconRocket, IconUsers } from "./Icons";
import { BannerPreview, Phone, PromoPreview } from "./Previews";

interface Props {
  campaignId: number;
  dicts: Dicts | null;
  who: Who;
  onAsk: (prompt: string) => void;
  onBack: () => void;
}

const ICON: Record<Status, JSX.Element> = {
  ok: <IconCheck size={14} />, error: <IconAlertCircle size={15} />, warn: <IconAlertTriangle size={14} />, info: <IconInfo size={15} />,
};

// Готовые причины возврата на доработку — модератор отмечает их и дописывает своё.
const DECLINE_REASONS = [
  "Креативы настроены не для всех мест размещения",
  "Добавьте теги кампании",
  "Текст баннера нужно поправить",
  "Проверьте даты показа",
  "Аудитория не соответствует продукту",
  "Нужна ссылка для перехода",
];
const EDITABLE = ["DRAFT", "NEEDS_WORK", "APPROVED", "ACTIVE", "ACTIVE_EDITING"];

function Row({ it, onAsk }: { it: CheckItem; onAsk: (p: string) => void }) {
  return (
    <div className={`check ${it.status}`}>
      <span className="check-icon">{ICON[it.status]}</span>
      <div className="check-body">
        <div className="check-title">{it.title}</div>
        <div className="check-detail">{it.detail}</div>
      </div>
      {it.action && <button className={`pill ${it.status === "error" || it.status === "warn" ? it.status : ""}`} onClick={() => onAsk(it.action!.prompt)}>{it.action.label}</button>}
    </div>
  );
}

export default function ReviewPage({ campaignId, dicts, who, onAsk, onBack }: Props) {
  const [c, setC] = useState<CampaignDetails | null>(null);
  const [v, setV] = useState<Validation | undefined>();
  const [audit, setAudit] = useState<AuditEntry[]>([]);
  const [checked, setChecked] = useState(new Date());
  const [ack, setAck] = useState(false);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [comment, setComment] = useState("");

  async function load() {
    try {
      const [det, val, log] = await Promise.all([api.campaign(campaignId), api.warnings(campaignId), api.audit(campaignId)]);
      setC(det); setV(val); setAudit(log); setChecked(new Date());
    } catch (e) { setError((e as Error).message); }
  }
  useEffect(() => { setAck(false); setError(null); load(); }, [campaignId]);

  const sections = useMemo(() => (c ? buildChecklist(c, v, dicts) : []), [c, v, dicts]);
  const { blockers, warnings } = counts(sections);

  async function act(fn: () => Promise<unknown>) {
    setBusy(true); setError(null);
    try { await fn(); await load(); } catch (e) { setError((e as Error).message); } finally { setBusy(false); }
  }

  if (!c) return <div className="page"><div className="muted">{error ?? "Загружаем кампанию…"}</div></div>;

  const lastDecline = [...audit].reverse().find((a) => a.action === "DECLINE");
  const editable = EDITABLE.includes(c.state) && who.role === "campaignManager";
  const canSubmit = EDITABLE_FOR_SUBMIT.includes(c.state) && blockers.length === 0 && (warnings.length === 0 || ack);
  const included = c.segments.included.map((code) => dicts?.segments.find((s) => s.code === code));
  const reach = included.reduce((s, x) => s + (x?.count ?? 0), 0);
  const format = (id: number) => dicts?.bannerTypes.find((b) => b.id === id)?.code;

  return (
    <div className="page review">
      <button className="back" onClick={onBack}><IconArrowLeft size={15} /> Все кампании</button>
      <div className="page-head">
        <div>
          <div className="eyebrow"><span className={`dot-state st-${c.state}`} /> {STATE_RU[c.state]}{c.published && " · показы идут"}</div>
          <h1>{EDITABLE_FOR_SUBMIT.includes(c.state) ? "Готова к модерации?" : c.name}</h1>
          <p className="muted">{EDITABLE_FOR_SUBMIT.includes(c.state)
            ? `«${c.name}» — всё, что нужно проверить, прежде чем кампания попадёт к модератору.`
            : "Проверка кампании и действия, доступные в текущем статусе."}</p>
        </div>
        <div className="counters">
          <span className={`counter err ${blockers.length ? "" : "zero"}`}><b>{blockers.length}</b> {plural(blockers.length, "ошибка", "ошибки", "ошибок")}</span>
          <span className={`counter warn ${warnings.length ? "" : "zero"}`}><b>{warnings.length}</b> {plural(warnings.length, "замечание", "замечания", "замечаний")}</span>
        </div>
      </div>

      {error && <div className="toast err">{error}</div>}

      <div className="review-grid">
        <div className="col">
          <section className="panel">
            <div className="panel-head"><h3>Чек-лист готовности</h3><span className="muted small">Проверено в {checked.toLocaleTimeString("ru-RU", { hour: "2-digit", minute: "2-digit" })}</span></div>
            {c.state === "NEEDS_WORK" && lastDecline?.comment && (
              <div className="moderator-note"><IconAlertTriangle size={15} /><div><b>Комментарий модератора ({person(lastDecline.actor)}):</b> «{lastDecline.comment}»</div>
                <button className="pill warn" onClick={() => onAsk(`Кампания «${c.name}»: исправь замечания модератора — «${lastDecline.comment}»`)}>Исправить</button></div>
            )}
            {sections.map((s) => (
              <div key={s.title}>
                <div className="section-title">{s.title}</div>
                {s.items.map((it) => <Row key={it.id} it={it} onAsk={onAsk} />)}
              </div>
            ))}
          </section>

          <section className="panel">
            <div className="panel-head"><h3>Как увидит клиент</h3><span className="muted small">{c.creatives.length} {plural(c.creatives.length, "креатив", "креатива", "креативов")}</span></div>
            {c.banners.length === 0 && <div className="empty-row">Креативов пока нет — <button className="link" onClick={() => onAsk(`Кампания «${c.name}»: создай баннер, промо-экран и креативы для всех мест размещения`)}>создать с ассистентом</button></div>}
            <div className="previews-row">
              {c.banners.map((b) => {
                const crs = c.creatives.filter((x) => x.bannerId === b.id);
                const content = c.contents.find((x) => crs.some((cr) => cr.contentId === x.id));
                const f = format(b.bannerTypeId) ?? "";
                return (
                  <div key={b.id} className="preview-pair">
                    <Phone label={`${FORMAT_RU[f] ?? "Баннер"} · ${crs.map((x) => CHANNEL_RU[x.channelCode] ?? x.channelCode).join(", ") || "не размещён"}`}><BannerPreview type={f} content={b.content} /></Phone>
                    {content && <Phone label="Промо-экран по нажатию"><PromoPreview content={content.content} /></Phone>}
                  </div>
                );
              })}
            </div>
          </section>

          <section className="panel">
            <div className="panel-head"><h3>История изменений</h3><span className="muted small">кто и что менял</span></div>
            <ol className="timeline">
              {[...audit].reverse().slice(0, 12).map((a) => (
                <li key={a.id}>
                  <span className="muted small">{fmtDateTime(a.at)}</span>
                  <span><b>{person(a.actor)}</b> · {ENTITY_RU[a.entity] ?? a.entity}: {AUDIT_ACTION_RU[a.action] ?? a.action}</span>
                  {a.comment && <em>«{a.comment}»</em>}
                </li>
              ))}
            </ol>
          </section>
        </div>

        <div className="col side-col">
          <section className="panel pad">
            <h3>Кто увидит рекламу</h3>
            <button className={`option ${c.audienceType === "ALL_USERS" ? "selected" : ""}`} disabled={!editable || busy || c.audienceType === "ALL_USERS"}
              onClick={() => dicts && act(() => actions.updateHeader(c, { audienceType: "ALL_USERS" }, dicts, who))}>
              <IconGlobe size={18} />
              <span><b>Все клиенты</b><small>Без таргетинга — максимальный охват места размещения</small></span>
              <i className="radio" />
            </button>
            <button className={`option ${c.audienceType === "SEGMENTED" ? "selected" : ""}`} disabled={!editable || busy || c.audienceType === "SEGMENTED"}
              onClick={() => dicts && act(() => actions.updateHeader(c, { audienceType: "SEGMENTED" }, dicts, who))}>
              <IconUsers size={18} />
              <span><b>Таргетинг по сегментам</b><small>{c.segments.included.length ? `Охват до ${fmtReach(reach)} клиентов` : "Нужен хотя бы один сегмент"}</small></span>
              <i className="radio" />
            </button>
            {c.audienceType === "SEGMENTED" && (
              <div className="seg-list">
                {c.segments.included.map((code, i) => <span key={code} className="chip in">{included[i]?.name ?? code} · {fmtReach(included[i]?.count ?? 0)}</span>)}
                {c.segments.excluded.map((code) => <span key={code} className="chip out">без: {dicts?.segments.find((s) => s.code === code)?.name.replace("Исключение. ", "").toLowerCase() ?? code}</span>)}
                <button className="link" onClick={() => onAsk(`Кампания «${c.name}»: хочу изменить сегменты`)}>изменить с ассистентом</button>
              </div>
            )}
            {c.audienceType === "SEGMENTED" && c.segments.included.length > 1 && (
              <p className="muted small note">Клиент попадает в аудиторию, если входит хотя бы в один сегмент.</p>
            )}
          </section>

          <div className="hint-box standalone"><IconClock size={16} /><span>Период показа: {fmtPeriod(c)} (UTC). Ограничений частоты показов нет — не увидят рекламу только исключённые сегменты.</span></div>

          <SubmitCard c={c} who={who} blockers={blockers.length} warnings={warnings.map((w) => w.title)} ack={ack} setAck={setAck}
            canSubmit={canSubmit} busy={busy} comment={comment} setComment={setComment}
            onAction={(a) => act(() => a === "decline" ? actions.decline(c.id, comment, who) : actions.transition(c.id, a, who))} />
        </div>
      </div>
    </div>
  );
}

interface SubmitProps {
  c: CampaignDetails; who: Who; blockers: number; warnings: string[]; ack: boolean; setAck: (v: boolean) => void;
  canSubmit: boolean; busy: boolean; comment: string; setComment: (v: string) => void;
  onAction: (a: "to-moderation" | "approve" | "decline" | "activate" | "stop") => void;
}

// Тёмная карточка действия: что можно сделать с кампанией прямо сейчас и почему.
function SubmitCard({ c, who, blockers, warnings, ack, setAck, canSubmit, busy, comment, setComment, onAction }: SubmitProps) {
  const manager = who.role === "campaignManager";
  const [declining, setDeclining] = useState(false);
  const toggleReason = (r: string) => {
    const parts = comment.split(/;\s*/).map((x) => x.trim()).filter(Boolean);
    setComment((parts.includes(r) ? parts.filter((x) => x !== r) : [...parts, r]).join("; "));
  };
  let head: { tone: string; title: string; text: string };
  let body: JSX.Element | null = null;
  let foot = "";

  if (EDITABLE_FOR_SUBMIT.includes(c.state)) {
    head = blockers
      ? { tone: "err", title: "Отправка на модерацию недоступна", text: `${blockers} ${plural(blockers, "ошибка мешает", "ошибки мешают", "ошибок мешают")} передать кампанию модератору.` }
      : { tone: "ok", title: "Можно отправлять на модерацию", text: "Ошибок нет. Модератор получит кампанию в текущем виде." };
    body = (
      <>
        {warnings.length > 0 && blockers === 0 && (
          <label className="ack"><input type="checkbox" checked={ack} onChange={(e) => setAck(e.target.checked)} />
            <span>Я видел замечания и отправляю кампанию с ними: {warnings.join("; ").toLowerCase()}.</span></label>
        )}
        <button className="cta" disabled={!canSubmit || !manager || busy} onClick={() => onAction("to-moderation")}><IconRocket size={17} /> Отправить на модерацию</button>
      </>
    );
    foot = !manager ? "Отправляет менеджер кампании — смените роль." : blockers ? `Исправьте ${blockers} ${plural(blockers, "ошибку", "ошибки", "ошибок")} — кнопка станет доступна автоматически.` : warnings.length && !ack ? "Отметьте, что видели замечания." : "Действие сохранится в истории изменений от вашего имени.";
  } else if (c.state === "ON_MODERATION") {
    head = { tone: "info", title: "На модерации", text: "Кампания ждёт решения модератора. Вносить правки сейчас нельзя." };
    body = who.role !== "campaignModerator" ? null : !declining ? (
      <div className="row">
        <button className="cta" disabled={busy} onClick={() => onAction("approve")}><IconCheck size={17} /> Одобрить</button>
        <button className="cta ghost" disabled={busy} onClick={() => setDeclining(true)}>На доработку</button>
      </div>
    ) : (
      <div className="decline-form">
        <div className="decline-label">Что исправить менеджеру? Отметьте причины или напишите своими словами.</div>
        <div className="reasons">
          {DECLINE_REASONS.map((r) => (
            <button key={r} className={`reason ${comment.includes(r) ? "on" : ""}`} onClick={() => toggleReason(r)} disabled={busy}>{r}</button>
          ))}
        </div>
        <textarea className="dark-input" rows={3} autoFocus placeholder="Комментарий увидит менеджер и ассистент — он поможет всё исправить"
          value={comment} onChange={(e) => setComment(e.target.value)} />
        <div className="row">
          <button className="cta warn" disabled={busy || !comment.trim()} onClick={() => onAction("decline")}>Вернуть на доработку</button>
          <button className="cta ghost" disabled={busy} onClick={() => setDeclining(false)}>Отмена</button>
        </div>
      </div>
    );
    foot = who.role !== "campaignModerator" ? "Решение принимает модератор."
      : declining ? (comment.trim() ? "Кампания вернётся менеджеру со статусом «На доработке», комментарий сохранится в истории." : "Без комментария вернуть нельзя — менеджер должен понимать, что исправить.")
      : `Правило двух рук: одобрять собственные правки нельзя (последние правки — ${person(c.lastEditAuthor)}).`;
  } else if (c.state === "APPROVED") {
    head = { tone: "ok", title: "Одобрена модератором", text: "После запуска кампания попадёт в приложение и её увидят клиенты." };
    body = <button className="cta" disabled={!manager || busy} onClick={() => onAction("activate")}><IconRocket size={17} /> Запустить кампанию</button>;
    foot = "Любая правка сейчас снимет одобрение — кампанию придётся снова отправить на модерацию.";
  } else if (c.published) {
    head = { tone: "ok", title: "Показы идут", text: c.state === "ACTIVE_EDITING" ? "Есть правки, которые клиенты ещё не видят, — отправьте их на модерацию." : "Кампания показывается клиентам." };
    body = (
      <>
        <label className="ack"><input type="checkbox" checked={ack} onChange={(e) => setAck(e.target.checked)} /><span>Понимаю: остановленную кампанию нельзя запустить снова.</span></label>
        <button className="cta danger" disabled={!manager || !ack || busy} onClick={() => onAction("stop")}>Остановить показы</button>
      </>
    );
    foot = "После остановки кампания останется в списке и истории, но перестанет показываться.";
  } else {
    head = { tone: "info", title: STATE_RU[c.state] ?? c.state, text: "Кампания остановлена: её нельзя изменить или запустить снова." };
  }

  const Icon = head.tone === "err" ? IconAlertTriangle : head.tone === "ok" ? IconCheck : IconInfo;
  return (
    <section className={`submit-card ${head.tone}`}>
      <div className="submit-title"><Icon size={18} /> {head.title}</div>
      <p>{head.text}</p>
      {body}
      {foot && <div className="submit-foot">{foot}</div>}
    </section>
  );
}
