import { useEffect, useRef, useState } from "react";
import type { ChatItem, Dicts, PendingAction } from "../types";
import { IconBot, IconSend } from "./Icons";
import PlanCard from "./PlanCard";
import { humanize } from "../ru";

interface Props {
  items: ChatItem[];
  busy: boolean;
  plan: PendingAction | null;
  dicts: Dicts | null;
  onSend: (text: string) => void;
  onDecide: (approved: boolean) => void;
  onReset: () => void;
}

const EXAMPLES = [
  "Кампания по вкладу для клиентов 26–45 в Москве и СПб, промо на главном, ставка 16%, с 5 ноября до конца года",
  "Почему «Ипотека: ставка 4,9%» на доработке?",
  "Можно ли запустить «Сомелье: подбор вина»?",
];

export default function Chat({ items, busy, plan, dicts, onSend, onDecide, onReset }: Props) {
  const [text, setText] = useState("");
  const end = useRef<HTMLDivElement>(null);
  useEffect(() => { end.current?.scrollIntoView({ behavior: "smooth" }); }, [items, plan, busy]);

  function submit(t: string) {
    const v = t.trim();
    if (!v || busy) return;
    onSend(v);
    setText("");
  }

  return (
    <section className="panel chat">
      <div className="panel-head"><h3><IconBot size={17} /> Ассистент</h3><button className="pill" onClick={onReset}>Новый диалог</button></div>
      <div className="messages">
        {items.map((m, i) => {
          if (m.kind === "result") {
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
      <form onSubmit={(e) => { e.preventDefault(); submit(text); }}>
        <textarea rows={3} value={text} onChange={(e) => setText(e.target.value)} placeholder="Опишите задачу: продукт, аудитория, место размещения, сроки…"
          onKeyDown={(e) => { if (e.key === "Enter" && !e.shiftKey) { e.preventDefault(); submit(text); } }} />
        <button type="submit" className="send" disabled={busy || !text.trim()} aria-label="Отправить"><IconSend size={18} /></button>
      </form>
    </section>
  );
}
