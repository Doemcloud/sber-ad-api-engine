import { useEffect, useRef, useState } from "react";
import type { ChatItem, Dicts, HistoryItem, PendingAction } from "../types";
import { IconBot, IconHistory, IconPlus, IconSend, IconTrash } from "./Icons";
import PlanCard from "./PlanCard";
import { humanize, person } from "../ru";
import { plural } from "../checklist";

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
  const { items, busy, plan, dicts, onSend, onDecide, onReset, sid, history, historyOpen, onToggleHistory, onOpenSession, onDeleteSession, awaitingFix } = props;
  const [text, setText] = useState("");
  const end = useRef<HTMLDivElement>(null);
  const input = useRef<HTMLTextAreaElement>(null);
  useEffect(() => { if (awaitingFix && !busy) input.current?.focus(); }, [awaitingFix, busy]);
  useEffect(() => { end.current?.scrollIntoView({ behavior: "smooth" }); }, [items, plan, busy]);

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
            return <div key={i} className={`msg ${m.kind}`}>{m.kind === "assistant" ? humanize(m.text, dicts) : m.text}</div>;
          })}
          {plan && <PlanCard plan={plan} dicts={dicts} busy={busy} onDecide={onDecide} />}
          {busy && <div className="msg assistant typing">Ассистент думает…</div>}
          {items.length <= 1 && (
            <div className="examples">
              {EXAMPLES.map((e) => <button key={e} className="example" onClick={() => submit(e)}>{e}</button>)}
            </div>
          )}
          <div ref={end} />
        </div>
      )}

      <form onSubmit={(e) => { e.preventDefault(); submit(text); }}>
        <textarea ref={input} rows={3} value={text} onChange={(e) => setText(e.target.value)}
          className={awaitingFix ? "await" : ""}
          placeholder={awaitingFix ? "Что поправить в плане? Например: «даты с 10 ноября», «без Санкт-Петербурга», «короче заголовок»" : "Опишите задачу: продукт, аудитория, место размещения, сроки…"}
          onKeyDown={(e) => { if (e.key === "Enter" && !e.shiftKey) { e.preventDefault(); submit(text); } }} />
        <button type="submit" className="send" disabled={busy || !text.trim()} aria-label="Отправить"><IconSend size={18} /></button>
      </form>
    </section>
  );
}
