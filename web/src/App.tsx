import { useState } from "react";
import { agent } from "./api/client";
import type { AgentState, ChatMessage } from "./types";
import Chat from "./components/Chat";
import CampaignCard from "./components/CampaignCard";
import Preview from "./components/Preview";
import CampaignList from "./components/CampaignList";

type Tab = "builder" | "campaigns";

export default function App() {
  const [tab, setTab] = useState<Tab>("builder");
  const [state, setState] = useState<AgentState | null>(null);
  const [messages, setMessages] = useState<ChatMessage[]>([
    { role: "assistant", text: "Опишите кампанию своими словами: кого рекламируем, что предлагаем, бюджет и сроки." },
  ]);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  async function run(fn: () => Promise<AgentState>, userText?: string) {
    if (userText) setMessages((m) => [...m, { role: "user", text: userText }]);
    setBusy(true);
    setError(null);
    try {
      const s = await fn();
      setState(s);
      if (s.reply) setMessages((m) => [...m, { role: "assistant", text: s.reply }]);
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setBusy(false);
    }
  }

  const send = (text: string) => run(() => agent.chat(state?.session_id ?? null, text), text);
  const confirm = (actionId: string, ok: boolean) =>
    state && run(() => agent.confirm(state.session_id, actionId, ok));

  function reset() {
    setState(null);
    setMessages([{ role: "assistant", text: "Новая кампания. Что запускаем?" }]);
  }

  return (
    <div className="app">
      <header>
        <div className="logo">AI-конструктор кампаний</div>
        <nav>
          <button className={tab === "builder" ? "active" : ""} onClick={() => setTab("builder")}>Новая кампания</button>
          <button className={tab === "campaigns" ? "active" : ""} onClick={() => setTab("campaigns")}>Мои кампании</button>
        </nav>
        {tab === "builder" && <button className="ghost" onClick={reset}>Начать заново</button>}
      </header>

      {error && <div className="error">Ошибка: {error}</div>}

      {tab === "builder" ? (
        <main className="builder">
          <Chat messages={messages} busy={busy} onSend={send}
            pending={state?.pending_actions ?? []} onConfirm={confirm} />
          <section className="side">
            <CampaignCard draft={state?.draft ?? {}} missing={state?.missing ?? []} />
            <Preview creatives={state?.draft.creatives ?? []} />
          </section>
        </main>
      ) : (
        <CampaignList />
      )}
    </div>
  );
}
