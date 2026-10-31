import { useEffect, useRef, useState } from "react";
import type { ChatMessage, PendingAction } from "../types";

interface Props {
  messages: ChatMessage[];
  busy: boolean;
  pending: PendingAction[];
  onSend: (text: string) => void;
  onConfirm: (actionId: string, ok: boolean) => void;
}

export default function Chat({ messages, busy, pending, onSend, onConfirm }: Props) {
  const [text, setText] = useState("");
  const end = useRef<HTMLDivElement>(null);
  useEffect(() => end.current?.scrollIntoView({ behavior: "smooth" }), [messages, pending]);

  function submit(e: { preventDefault(): void }) {
    e.preventDefault();
    const t = text.trim();
    if (!t || busy) return;
    onSend(t);
    setText("");
  }

  return (
    <section className="chat">
      <div className="messages">
        {messages.map((m, i) => (
          <div key={i} className={`msg ${m.role}`}>{m.text}</div>
        ))}
        {pending.map((a) => (
          <div key={a.id} className="action">
            <div className="action-title">{a.title}</div>
            {Object.keys(a.payload).length > 0 && (
              <pre>{JSON.stringify(a.payload, null, 2)}</pre>
            )}
            <div className="row">
              <button disabled={busy} onClick={() => onConfirm(a.id, true)}>Подтвердить</button>
              <button disabled={busy} className="ghost" onClick={() => onConfirm(a.id, false)}>Отклонить</button>
            </div>
          </div>
        ))}
        {busy && <div className="msg assistant typing">Думаю…</div>}
        <div ref={end} />
      </div>
      <form onSubmit={submit}>
        <textarea value={text} onChange={(e) => setText(e.target.value)} rows={3}
          placeholder="Например: кофейня «Зерно» на Ленина, 12, скидка 20% на кофе с собой до 12:00, бюджет 30 000 ₽"
          onKeyDown={(e) => { if (e.key === "Enter" && !e.shiftKey) submit(e); }} />
        <button type="submit" disabled={busy || !text.trim()}>Отправить</button>
      </form>
    </section>
  );
}
