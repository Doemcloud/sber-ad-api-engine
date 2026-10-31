import { useState } from "react";
import { agent, type AuthUser } from "../api";
import { loadPrefs, savePrefs, type Prefs, type Theme } from "../prefs";

const THEMES: { value: Theme; label: string }[] = [
  { value: "light", label: "Светлая" }, { value: "dark", label: "Тёмная" }, { value: "system", label: "Как в системе" },
];

function Switch({ on, onChange, label }: { on: boolean; onChange: (v: boolean) => void; label: string }) {
  return <button className={`switch ${on ? "on" : ""}`} role="switch" aria-checked={on} aria-label={label} onClick={() => onChange(!on)} />;
}

export default function SettingsPage({ user, onLogout, onHistoryCleared }: { user: AuthUser; onLogout: () => void; onHistoryCleared: () => void }) {
  const [p, setP] = useState<Prefs>(loadPrefs);
  const [msg, setMsg] = useState<string | null>(null);
  const manager = user.role === "campaignManager";
  const set = (patch: Partial<Prefs>) => { const next = { ...p, ...patch }; setP(next); savePrefs(next); };

  async function clearHistory() {
    if (!confirmClear) { setConfirmClear(true); return; }
    setConfirmClear(false);
    try {
      const list = await agent.sessions();
      await Promise.all(list.map((h) => agent.deleteSession(h.id)));
      onHistoryCleared();
      setMsg(list.length ? `Удалено диалогов: ${list.length}` : "История и так пуста");
    } catch (e) { setMsg(`Не удалось очистить историю: ${(e as Error).message}`); }
  }
  const [confirmClear, setConfirmClear] = useState(false);

  return (
    <div className="page">
      <div className="page-head"><div><div className="eyebrow">Только для вас</div><h1>Настройки</h1>
        <p className="muted">Оформление сохраняется в этом браузере и применяется сразу.</p></div></div>
      <div className="settings">
        <section className="panel pad">
          <h3>Оформление</h3>
          <div className="theme-pick">
            {THEMES.map((t) => (
              <button key={t.value} className={`theme-opt ${p.theme === t.value ? "on" : ""}`} onClick={() => set({ theme: t.value })} aria-pressed={p.theme === t.value}>
                <span className={`theme-swatch ${t.value}`} />{t.label}
              </button>
            ))}
          </div>
          <div className="set-row" style={{ marginTop: 10 }}>
            <div className="t"><b>Компактный режим</b><span>Мельче шрифт — больше помещается на экране</span></div>
            <Switch on={p.compact} onChange={(v) => set({ compact: v })} label="Компактный режим" />
          </div>
          <div className="set-row">
            <div className="t"><b>Меньше анимации</b><span>Без плавных переходов и раскрытия меню</span></div>
            <Switch on={p.reduceMotion} onChange={(v) => set({ reduceMotion: v })} label="Меньше анимации" />
          </div>
        </section>

        {manager && (
          <section className="panel pad">
            <h3>Ассистент</h3>
            <div className="set-row">
              <div className="t"><b>Примеры запросов</b><span>Подсказки в начале нового диалога</span></div>
              <Switch on={p.examples} onChange={(v) => set({ examples: v })} label="Примеры запросов" />
            </div>
            <div className="set-row">
              <div className="t"><b>История диалогов</b><span>{confirmClear ? "Удалить все ваши диалоги без возможности восстановить?" : "Все ваши диалоги с ассистентом"}</span></div>
              <button className="danger-link" onClick={clearHistory}>{confirmClear ? "Да, удалить" : "Очистить"}</button>
            </div>
            {msg && <div className="muted small">{msg}</div>}
          </section>
        )}

        <section className="panel pad">
          <h3>Профиль</h3>
          <div className="set-row"><div className="t"><b>{user.name}</b><span>{user.title}</span></div></div>
          <div className="set-row"><div className="t"><b>Логин</b><span>{user.login}</span></div></div>
          <div className="set-row">
            <div className="t"><b>Права</b><span>{manager ? "Создаёт и редактирует кампании, отправляет на модерацию, запускает и останавливает показы" : "Одобряет кампании или возвращает их на доработку с комментарием"}</span></div>
          </div>
          <div className="set-row"><div className="t"><b>Выход</b><span>Завершить сеанс в этом браузере</span></div><button className="danger-link" onClick={onLogout}>Выйти</button></div>
        </section>
      </div>
    </div>
  );
}
