import { useEffect, useMemo, useState } from "react";
import { agent, api } from "./api";
import { buildChecklist, counts, plural } from "./checklist";
import type { AgentState, ChatItem, Dicts, Role } from "./types";
import Chat from "./components/Chat";
import CampaignView, { StateBadge } from "./components/CampaignView";
import CampaignList from "./components/CampaignList";
import DictsPage from "./components/DictsPage";
import ReviewPage from "./components/ReviewPage";
import { IconShield } from "./components/Icons";
import { Sidebar, Topbar, USERS, type Page } from "./components/Shell";

const newSid = () => Math.random().toString(36).slice(2, 14);
const GREETING: ChatItem = { kind: "assistant", text: "Расскажите о кампании своими словами: что продвигаем, для кого, где показать и в какие даты. Я подберу аудиторию и места размещения, подготовлю креативы, проверю всё и покажу, как реклама будет выглядеть, — сохраню только после вашего подтверждения." };

export default function App() {
  const [page, setPage] = useState<Page>("assistant");
  const [role, setRole] = useState<Role>("campaignManager");
  const [query, setQuery] = useState("");
  const [sid, setSid] = useState(newSid);
  const [state, setState] = useState<AgentState | null>(null);
  const [items, setItems] = useState<ChatItem[]>([GREETING]);
  const [dicts, setDicts] = useState<Dicts | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [reviewId, setReviewId] = useState<number | null>(null);

  const who = { user: USERS[role].user, role };

  useEffect(() => { api.dicts().then(setDicts).catch((e: Error) => setError(`Не удалось загрузить данные рекламного кабинета: ${e.message}`)); }, []);

  async function run(fn: () => Promise<AgentState>, userText?: string) {
    if (userText) setItems((m) => [...m, { kind: "user", text: userText }]);
    setBusy(true);
    setError(null);
    try {
      const s = await fn();
      setState(s);
      if (s.campaign_id) setReviewId(s.campaign_id);
      setItems((m) => {
        const next = [...m];
        if (!userText && s.last_result?.length) next.push({ kind: "result", results: s.last_result });
        if (s.reply) next.push({ kind: "assistant", text: s.reply });
        return next;
      });
      api.dicts().then(setDicts).catch(() => undefined); // могли появиться новые теги и места
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setBusy(false);
    }
  }

  const send = (text: string) => run(() => agent.chat(sid, text, who.user, role), text);
  const decide = (approved: boolean) => state?.pending_action && run(() => agent.confirm(sid, state.pending_action!.id, approved));

  function switchRole(r: Role) {
    setRole(r);
    if (state) run(() => agent.setRole(sid, USERS[r].user, r));
  }

  function reset() {
    setSid(newSid());
    setState(null);
    setItems([GREETING]);
  }

  function openReview(id: number) {
    setReviewId(id);
    setPage("review");
  }

  // Кнопка в чек-листе → ассистент получает задачу уже в контексте кампании.
  async function ask(prompt: string) {
    setPage("assistant");
    if (reviewId && state?.campaign_id !== reviewId) {
      try { setState(await agent.openCampaign(sid, reviewId)); } catch { /* агент недоступен — ошибку покажет chat */ }
    }
    send(prompt);
  }

  const summary = useMemo(() => {
    if (!state?.campaign) return null;
    return counts(buildChecklist(state.campaign, state.validation, dicts));
  }, [state, dicts]);

  return (
    <div className="shell">
      <Sidebar page={page} onNavigate={(p) => (p === "review" && !reviewId ? setPage("campaigns") : setPage(p))} />
      <div className="workspace">
        <Topbar page={page} role={role} query={query} onQuery={(q) => { setQuery(q); if (q && page === "assistant") setPage("campaigns"); }} onRole={switchRole} />
        {error && <div className="toast err">{error}</div>}

        {page === "assistant" && (
          <div className="page assistant">
            <Chat items={items} busy={busy} plan={state?.pending_action ?? null} dicts={dicts} onSend={send} onDecide={decide} onReset={reset} />
            <div className="col side-col">
              {state?.campaign ? (
                <>
                  <section className="panel pad summary">
                    <div className="eyebrow">Текущая кампания</div>
                    <h3>{state.campaign.name}</h3>
                    <StateBadge state={state.campaign.state} published={state.campaign.published} />
                    {summary && (
                      <div className="counters small-counters">
                        <span className={`counter err ${summary.blockers.length ? "" : "zero"}`}><b>{summary.blockers.length}</b> {plural(summary.blockers.length, "ошибка", "ошибки", "ошибок")}</span>
                        <span className={`counter warn ${summary.warnings.length ? "" : "zero"}`}><b>{summary.warnings.length}</b> {plural(summary.warnings.length, "замечание", "замечания", "замечаний")}</span>
                      </div>
                    )}
                    <button className="cta-light" onClick={() => openReview(state.campaign!.id)}><IconShield size={16} /> Проверить готовность к модерации</button>
                  </section>
                  <CampaignView campaign={state.campaign} dicts={dicts} validation={state.validation} refreshKey={state.journal?.length} />
                </>
              ) : (
                <section className="panel pad empty">
                  <h3>Здесь появится ваша кампания</h3>
                  <p className="muted">Параметры, аудитория и охват, места размещения, макеты баннера и промо-экрана, проверка и история изменений.</p>
                </section>
              )}
            </div>
          </div>
        )}
        {page === "campaigns" && <CampaignList dicts={dicts} query={query} onOpen={openReview} />}
        {page === "review" && reviewId && <ReviewPage campaignId={reviewId} dicts={dicts} who={who} onAsk={ask} onBack={() => setPage("campaigns")} />}
        {page === "dicts" && <DictsPage dicts={dicts} query={query} />}
      </div>
    </div>
  );
}
