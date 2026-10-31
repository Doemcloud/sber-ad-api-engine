import { useEffect, useMemo, useState } from "react";
import { agent, api, loadAuth, saveAuth, setOnAuthExpired, type Auth } from "./api";
import { buildChecklist, counts, plural } from "./checklist";
import type { AgentState, ChatItem, Dicts, HistoryItem, TranscriptItem } from "./types";
import Chat from "./components/Chat";
import CampaignView, { StateBadge } from "./components/CampaignView";
import CampaignList from "./components/CampaignList";
import DictsPage from "./components/DictsPage";
import ReviewPage from "./components/ReviewPage";
import { IconShield } from "./components/Icons";
import { Sidebar, Topbar, type Page } from "./components/Shell";
import LoginPage from "./components/LoginPage";
import StatsPage from "./components/StatsPage";

const newSid = () => Math.random().toString(36).slice(2, 14);

// Текущий диалог запоминается в браузере: после перезагрузки страницы он открывается снова.
let SID_KEY = "sber-ad.assistant.sid";
const storedSid = () => { try { return localStorage.getItem(SID_KEY); } catch { return null; } };
const rememberSid = (v: string) => { try { localStorage.setItem(SID_KEY, v); } catch { /* приватный режим — просто не запоминаем */ } };
const GREETING: ChatItem = { kind: "assistant", text: "Расскажите о кампании своими словами: что продвигаем, для кого, где показать и в какие даты. Я подберу аудиторию и места размещения, подготовлю креативы, проверю всё и покажу, как реклама будет выглядеть, — сохраню только после вашего подтверждения." };

const toItems = (t: TranscriptItem[] | undefined): ChatItem[] =>
  [GREETING, ...(t ?? []).map(({ kind, text, results, rejected }) => ({ kind, text, results, rejected }))];

// Без входа — страница входа; после входа — кабинет от имени вошедшего (роль берётся из токена).
export default function App() {
  const [auth, setAuth] = useState<Auth | null>(loadAuth);
  useEffect(() => { setOnAuthExpired(() => setAuth(null)); }, []);
  if (!auth) return <LoginPage onLogin={setAuth} />;
  return <Cabinet key={auth.user.login} auth={auth} onLogout={() => { saveAuth(null); setAuth(null); }} />;
}

function Cabinet({ auth, onLogout }: { auth: Auth; onLogout: () => void }) {
  SID_KEY = `sber-ad.assistant.sid.${auth.user.login}`; // у каждого пользователя — свой текущий диалог
  const role = auth.user.role;
  const [page, setPage] = useState<Page>(role === "campaignModerator" ? "campaigns" : "assistant");
  const [query, setQuery] = useState("");
  const [sid, setSid] = useState(() => storedSid() ?? newSid());
  const [state, setState] = useState<AgentState | null>(null);
  const [items, setItems] = useState<ChatItem[]>([GREETING]);
  const [dicts, setDicts] = useState<Dicts | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [reviewId, setReviewId] = useState<number | null>(null);
  const [history, setHistory] = useState<HistoryItem[] | null>(null);
  const [historyOpen, setHistoryOpen] = useState(false);

  const who = { user: auth.user.user, role };

  useEffect(() => { api.dicts().then(setDicts).catch((e: Error) => setError(`Не удалось загрузить данные рекламного кабинета: ${e.message}`)); }, []);
  useEffect(() => { rememberSid(sid); }, [sid]);

  // После перезагрузки страницы — вернуть последний диалог со всей лентой.
  useEffect(() => {
    const saved = storedSid();
    if (!saved) return;
    agent.session(saved).then((s) => {
      setState(s);
      setItems(toItems(s.transcript));
      if (s.campaign_id) setReviewId(s.campaign_id);
    }).catch(() => undefined); // диалога уже нет (удалён) — начинаем с чистого листа
  }, []);

  const loadHistory = () => agent.sessions().then(setHistory).catch(() => setHistory([]));

  async function run(fn: () => Promise<AgentState>, userText?: string) {
    if (userText) setItems((m) => [...m, { kind: "user", text: userText }]);
    setBusy(true);
    setError(null);
    try {
      const s = await fn();
      setState(s);
      if (s.campaign_id) setReviewId(s.campaign_id);
      if (s.transcript) setItems(toItems(s.transcript)); // лента с сервера — та же, что попадёт в историю
      else setItems((m) => {
        const next = [...m];
        if (!userText && s.last_result?.length) next.push({ kind: "result", results: s.last_result });
        if (s.reply) next.push({ kind: "assistant", text: s.reply });
        return next;
      });
      if (historyOpen) loadHistory();
      api.dicts().then(setDicts).catch(() => undefined); // могли появиться новые теги и места
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setBusy(false);
    }
  }

  const send = (text: string) => run(() => agent.chat(sid, text, who.user, role), text);
  const decide = (approved: boolean) => state?.pending_action && run(() => agent.confirm(sid, state.pending_action!.id, approved));

  function reset() {
    setSid(newSid());
    setState(null);
    setItems([GREETING]);
    setHistoryOpen(false);
  }

  function toggleHistory() {
    if (!historyOpen) { setHistory(null); loadHistory(); }
    setHistoryOpen(!historyOpen);
  }

  async function openSession(id: string) {
    setError(null);
    try {
      const s = await agent.session(id);
      setSid(id);
      setState(s);
      setItems(toItems(s.transcript));
      setReviewId(s.campaign_id ?? null);
      setHistoryOpen(false);
    } catch (e) {
      setError(`Не удалось открыть диалог: ${(e as Error).message}`);
    }
  }

  async function deleteSession(id: string) {
    try {
      await agent.deleteSession(id);
      if (id === sid) { setSid(newSid()); setState(null); setItems([GREETING]); }
      loadHistory();
    } catch (e) {
      setError(`Не удалось удалить диалог: ${(e as Error).message}`);
    }
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
        <Topbar page={page} name={auth.user.name} title={auth.user.title} query={query} onLogout={onLogout}
          onQuery={(q) => { setQuery(q); if (q && page === "assistant") setPage("campaigns"); }} />
        {error && <div className="toast err">{error}</div>}

        {page === "assistant" && (
          <div className="page assistant">
            <Chat items={items} busy={busy} plan={state?.pending_action ?? null} dicts={dicts} onSend={send} onDecide={decide} onReset={reset}
              sid={sid} history={history} historyOpen={historyOpen} onToggleHistory={toggleHistory} onOpenSession={openSession} onDeleteSession={deleteSession}
              awaitingFix={!!state?.awaiting_fix} />
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
        {page === "stats" && <StatsPage dicts={dicts} initialId={reviewId} query={query} />}
        {page === "dicts" && <DictsPage dicts={dicts} query={query} />}
      </div>
    </div>
  );
}
