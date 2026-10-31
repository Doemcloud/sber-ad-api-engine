import { useEffect, useMemo, useRef, useState } from "react";
import type { ChatItem, Dicts, HistoryItem, PendingAction } from "../types";
import { fmtReach } from "../ru";
import { IconBot, IconHistory, IconPlus, IconSend, IconTrash } from "./Icons";
import PlanCard from "./PlanCard";
import { Img } from "./Previews";
import { humanize, person } from "../ru";
import { plural } from "../checklist";

const IMAGE_FOR: Record<string, string> = { STORY: "сторис", SMART_BANNER: "смарт-баннера", PROMO: "промо-экрана" };

interface Props {
  items: ChatItem[];
  busy: boolean;
  plan: PendingAction | null;
  dicts: Dicts | null;
  onSend: (text: string) => void;
  onDecide: (approved: boolean) => void;
  onReset: () => void;
  // История диалогов
  sid: string;
  history: HistoryItem[] | null;
  historyOpen: boolean;
  onToggleHistory: () => void;
  onOpenSession: (id: string) => void;
  onDeleteSession: (id: string) => void;
  awaitingFix?: boolean; // план отменён — ассистент ждёт, что исправить
  showExamples?: boolean;
  suggestions?: string[]; // быстрые ответы под последней репликой ассистента
  draft?: { text: string; n: number } | null; // подставить текст в поле ввода (не отправляя)
}

interface Hint { label: string; kind: string; extra?: string }

// Подсказки при наборе: сегменты, места размещения, теги и тематики, совпадающие с последним словом.
function findHints(text: string, dicts: Dicts | null): { word: string; hints: Hint[] } {
  const m = /([\p{L}\d-]{3,})$/u.exec(text);
  const word = m?.[1] ?? "";
  if (!dicts || !word) return { word: "", hints: [] };
  const w = word.toLowerCase();
  const hit = (s: string) => s.toLowerCase().split(/[\s,.()«»–-]+/).some((t) => t.startsWith(w));
  const out: Hint[] = [];
  for (const s of dicts.segments) {
    const name = s.name.replace("Исключение. ", "");
    if (s.state === "ACTIVE" && hit(name)) out.push({ label: name, kind: s.code.startsWith("EXC_") ? "исключить" : "сегмент", extra: fmtReach(s.count) });
  }
  for (const p of dicts.places) if (p.state === "ACTIVE" && hit(p.description)) out.push({ label: p.description, kind: "место" });
  for (const t of dicts.tags) if (hit(t.name)) out.push({ label: t.name, kind: "тег" });
  for (const t of dicts.topics) if (hit(t.label)) out.push({ label: t.label, kind: "тематика" });
  return { word, hints: out.slice(0, 5) };
}

const EXAMPLES = [
  "Кампания по вкладу для клиентов 26–45 в Москве и СПб, промо на главном, ставка 16%, с 5 ноября до конца года",
  "Почему «Ипотека: ставка 4,9%» на доработке?",
  "Можно ли запустить «Сомелье: подбор вина»?",
];

// «сегодня, 18:40» / «вчера, 09:15» / «28 окт., 12:00» — в часовом поясе пользователя.
function whenLabel(iso: string) {
  const d = new Date(iso);
  if (isNaN(d.getTime())) return "";
  const time = d.toLocaleTimeString("ru-RU", { hour: "2-digit", minute: "2-digit" });
  const day = (x: Date) => new Date(x.getFullYear(), x.getMonth(), x.getDate()).getTime();
  const diff = Math.round((day(new Date()) - day(d)) / 86400000);
  if (diff === 0) return `сегодня, ${time}`;
  if (diff === 1) return `вчера, ${time}`;
  return `${d.toLocaleDateString("ru-RU", { day: "numeric", month: "short" })}, ${time}`;
}

export default function Chat(props: Props) {
  const { items, busy, plan, dicts, onSend, onDecide, onReset, sid, history, historyOpen, onToggleHistory, onOpenSession, onDeleteSession, awaitingFix, showExamples = true, suggestions = [], draft } = props;
  const [text, setText] = useState("");
  const end = useRef<HTMLDivElement>(null);
  const input = useRef<HTMLTextAreaElement>(null);
  useEffect(() => { if (awaitingFix && !busy) input.current?.focus(); }, [awaitingFix, busy]);
  useEffect(() => { if (draft) { setText(draft.text); input.current?.focus(); } }, [draft?.n]);
  useEffect(() => { end.current?.scrollIntoView({ behavior: "smooth" }); }, [items, plan, busy]);

  const { word, hints } = useMemo(() => findHints(text, dicts), [text, dicts]);
  const [hintsOff, setHintsOff] = useState("");
  const showHints = hints.length > 0 && hintsOff !== word && !busy;
  function accept(h: Hint) {
    setText(text.slice(0, text.length - word.length) + `«${h.label}» `);
    input.current?.focus();
  }

  function submit(t: string) {
    const v = t.trim();
    if (!v || busy) return;
    onSend(v);
    setText("");
  }

  return (
    <section className="panel chat">
      <div className="panel-head">
        <h3><IconBot size={17} /> Ассистент</h3>
        <div className="row">
          <button className={`pill ${historyOpen ? "on" : ""}`} onClick={onToggleHistory} aria-pressed={historyOpen}>
            <IconHistory size={15} /> История{history?.length ? ` · ${history.length}` : ""}
          </button>
          <button className="pill" onClick={onReset}><IconPlus size={15} /> Новый диалог</button>
        </div>
      </div>

      {historyOpen ? (
        <div className="history">
          <div className="history-head">
            <span className="muted small">Диалоги сохраняются автоматически — к любому можно вернуться и продолжить.</span>
          </div>
          {history === null && <div className="history-empty muted">Загружаем историю…</div>}
          {history?.length === 0 && <div className="history-empty muted">Пока нет сохранённых диалогов. Начните первый — он появится здесь.</div>}
          {history?.map((h) => (
            <div key={h.id} className={`history-item ${h.id === sid ? "current" : ""}`} role="button" tabIndex={0}
              onClick={() => onOpenSession(h.id)} onKeyDown={(e) => { if (e.key === "Enter") onOpenSession(h.id); }}>
              <div className="h-main">
                <div className="h-title">{h.title}</div>
                <div className="h-meta">
                  <span>{whenLabel(h.updated_at)}</span>
                  <span>· {h.messages} {plural(h.messages, "сообщение", "сообщения", "сообщений")}</span>
                  <span>· {person(h.user)}</span>
                  {h.campaign_name && <span>· «{h.campaign_name}»</span>}
                  {h.pending && <span className="h-tag warn">ждёт подтверждения</span>}
                  {h.id === sid && <span className="h-tag">открыт</span>}
                </div>
              </div>
              <button className="h-del" title="Удалить диалог" aria-label="Удалить диалог"
                onClick={(e) => { e.stopPropagation(); onDeleteSession(h.id); }}><IconTrash size={16} /></button>
            </div>
          ))}
        </div>
      ) : (
        <div className="messages">
          {items.map((m, i) => {
            if (m.kind === "result") {
              if (m.rejected) return <div key={i} className="result"><div className="rejected">✗ План отменён: {humanize(m.rejected, dicts)}</div></div>;
              return (
                <div key={i} className="result">
                  {(m.results ?? []).map((r) => (
                    <div key={r.step} className={r.ok ? "ok" : "fail"}>
                      {r.ok ? "✓" : "✗"} {humanize(r.summary, dicts)}
                      {r.errors?.map((e, j) => <div key={j} className="hint">{humanize(e.message, dicts)}{e.hint ? ` — ${humanize(e.hint, dicts)}` : ""}</div>)}
                    </div>
                  ))}
                </div>
              );
            }
            if (m.kind === "image") {
              const target = IMAGE_FOR[m.format ?? ""] ?? "креатива";
              return (
                <figure key={i} className={`gen-image gen-${(m.format ?? "").toLowerCase()}`}>
                  <a href={m.url} target="_blank" rel="noopener noreferrer" title="Открыть в полном размере"><Img src={m.url} className="gen-image-pic" /></a>
                  <figcaption>
                    <b>✦ Изображение для {target}</b>
                    {m.prompt && <span>{m.prompt}</span>}
                    <button className="quick-btn" disabled={busy} onClick={() => onSend(`Нарисуй другой вариант изображения для ${target}`)}>Другой вариант</button>
                  </figcaption>
                </figure>
              );
            }
            return <div key={i} className={`msg ${m.kind}`}>{m.kind === "assistant" ? humanize(m.text, dicts) : m.text}</div>;
          })}
          {plan && <PlanCard plan={plan} dicts={dicts} busy={busy} onDecide={onDecide} />}
          {busy && <div className="msg assistant typing">Ассистент думает…</div>}
          {!busy && !plan && suggestions.length > 0 && items.length > 1 && (
            <div className="quick" role="group" aria-label="Быстрые ответы">
              {suggestions.map((q) => <button key={q} className="quick-btn" onClick={() => submit(q)}>{q}</button>)}
            </div>
          )}
          {items.length <= 1 && showExamples && (
            <div className="examples">
              {EXAMPLES.map((e) => <button key={e} className="example" onClick={() => submit(e)}>{e}</button>)}
            </div>
          )}
          <div ref={end} />
        </div>
      )}

      {showHints && (
        <div className="typeahead" role="listbox" aria-label="Подсказки из справочников">
          <span className="muted small">Подставить:</span>
          {hints.map((h, i) => (
            <button key={h.kind + h.label} role="option" aria-selected={i === 0} className="hint-chip" onClick={() => accept(h)} title={i === 0 ? "Tab — подставить" : undefined}>
              <b>{h.label}</b><span>{h.kind}{h.extra ? ` · ${h.extra}` : ""}</span>
            </button>
          ))}
        </div>
      )}
      <form onSubmit={(e) => { e.preventDefault(); submit(text); }}>
        <textarea ref={input} rows={3} value={text} onChange={(e) => setText(e.target.value)}
          className={awaitingFix ? "await" : ""}
          placeholder={awaitingFix ? "Что поправить в плане? Например: «даты с 10 ноября», «без Санкт-Петербурга», «короче заголовок»" : "Опишите задачу: продукт, аудитория, место размещения, сроки…"}
          onKeyDown={(e) => {
            if (e.key === "Tab" && showHints) { e.preventDefault(); accept(hints[0]); return; }
            if (e.key === "Escape" && showHints) { setHintsOff(word); return; }
            if (e.key === "Enter" && !e.shiftKey) { e.preventDefault(); submit(text); }
          }} />
        <button type="submit" className="send" disabled={busy || !text.trim()} aria-label="Отправить"><IconSend size={18} /></button>
      </form>
    </section>
  );
}
