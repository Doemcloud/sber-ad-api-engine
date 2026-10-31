import { fmtDate } from "../checklist";
import { AUDIENCE_RU, fmtReach, humanize, topicLabel } from "../ru";
import type { BannerContent, Dicts, PendingAction, PlanStep, PromoContent } from "../types";
import { BannerPreview, Phone, PromoPreview } from "./Previews";

const PRIORITY: Record<number, string> = { 0: "обычный", 10: "повышенный", 25: "высокий", 50: "максимальный" };

function StepPreview({ step, dicts }: { step: PlanStep; dicts: Dicts | null }) {
  const p = step.preview;
  if (p.kind === "banner") {
    const data = p.data as { content?: BannerContent };
    return <Phone><BannerPreview type={p.bannerType as string} content={data.content} /></Phone>;
  }
  if (p.kind === "content") {
    return <Phone><PromoPreview content={(p.data as { content?: PromoContent }).content} /></Phone>;
  }
  if (p.kind === "campaign") {
    const c = p.data as Record<string, unknown>;
    const places = ((c.places as unknown[]) ?? []).map((id) => dicts?.places.find((x) => x.id === id)?.description ?? "новое место");
    const tags = ((c.tags as unknown[]) ?? []).map((id) => dicts?.tags.find((x) => x.id === id)?.name ?? "новый тег");
    const weight = Number(c.weight ?? 0);
    return (
      <dl className="fields small">
        <dt>Период</dt><dd>{fmtDate(String(c.startDate))} {String(c.startTime)} — {c.endDate ? `${fmtDate(String(c.endDate))} ${c.endTime ?? ""}` : "без даты окончания"}</dd>
        <dt>Тематика</dt><dd>{topicLabel(String(c.topic), dicts)}</dd>
        <dt>Аудитория</dt><dd>{AUDIENCE_RU[String(c.audienceType)] ?? String(c.audienceType)}</dd>
        <dt>Размещение</dt><dd>{places.join(", ") || "—"}</dd>
        <dt>Теги</dt><dd>{tags.join(", ") || "—"}</dd>
        <dt>Приоритет</dt><dd>{PRIORITY[weight] ?? weight}, прогнозный CTR {String(c.initialCtr ?? 15)}%</dd>
      </dl>
    );
  }
  if (p.kind === "segments") {
    const d = p.data as { included: { code: string; name?: string; count?: number }[]; excluded: { code: string; name?: string }[] };
    return (
      <div className="segs">
        {d.included.map((s) => <span key={s.code} className="chip in">{s.name ?? s.code}{s.count ? ` · ${fmtReach(s.count)}` : ""}</span>)}
        {d.excluded.map((s) => <span key={s.code} className="chip out">без: {(s.name ?? s.code).replace("Исключение. ", "").toLowerCase()}</span>)}
      </div>
    );
  }
  return null;
}

interface Props {
  plan: PendingAction;
  dicts: Dicts | null;
  busy: boolean;
  onDecide: (approved: boolean) => void;
}

export default function PlanCard({ plan, dicts, busy, onDecide }: Props) {
  return (
    <div className="plan">
      <div className="plan-title">Что сделает ассистент — подтвердите</div>
      <ol>
        {plan.steps.map((s) => (
          <li key={s.n}>
            <div>{humanize(s.summary, dicts)}</div>
            <StepPreview step={s} dicts={dicts} />
          </li>
        ))}
      </ol>
      <div className="row">
        <button disabled={busy} onClick={() => onDecide(true)}>Подтвердить</button>
        <button disabled={busy} className="ghost" onClick={() => onDecide(false)}>Отменить</button>
      </div>
    </div>
  );
}
