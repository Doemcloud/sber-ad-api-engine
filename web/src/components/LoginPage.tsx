import { useState } from "react";
import { login, type Auth } from "../api";

// Страница входа в рекламный кабинет. Две демо-учётки: менеджер (client) и модератор (moder).
const DEMO = [
  { login: "client", password: "client", label: "Менеджер кампаний", hint: "заводит кампании с ассистентом" },
  { login: "moder", password: "moder", label: "Модератор", hint: "одобряет или возвращает на доработку" },
];

export default function LoginPage({ onLogin }: { onLogin: (a: Auth) => void }) {
  const [name, setName] = useState("");
  const [password, setPassword] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  async function submit(l = name, p = password) {
    if (!l.trim() || !p) { setError("Введите логин и пароль"); return; }
    setBusy(true); setError(null);
    try { onLogin(await login(l, p)); }
    catch (e) {
      const m = (e as Error).message;
      setError(/fetch|network/i.test(m) ? "Сервер недоступен — проверьте, что API запущен" : m);
    } finally { setBusy(false); }
  }

  return (
    <div className="login-screen">
      <form className="login-card" onSubmit={(e) => { e.preventDefault(); submit(); }}>
        <div className="login-brand"><div className="brand">С</div><div><b>Рекламный кабинет</b><span>СберБанк Онлайн</span></div></div>
        <h1>Вход</h1>
        <p className="muted">Войдите, чтобы заводить рекламные кампании с ассистентом или проверять их на модерации.</p>
        <label className="field"><span>Логин</span>
          <input value={name} onChange={(e) => setName(e.target.value)} autoFocus autoComplete="username" placeholder="client или moder" />
        </label>
        <label className="field"><span>Пароль</span>
          <input type="password" value={password} onChange={(e) => setPassword(e.target.value)} autoComplete="current-password" placeholder="••••••" />
        </label>
        {error && <div className="login-error">{error}</div>}
        <button type="submit" className="login-btn" disabled={busy}>{busy ? "Входим…" : "Войти"}</button>
        <div className="demo">
          <div className="muted small">Демо-доступ</div>
          {DEMO.map((d) => (
            <button key={d.login} type="button" className="demo-acc" disabled={busy}
              onClick={() => { setName(d.login); setPassword(d.password); submit(d.login, d.password); }}>
              <b>{d.label}</b><span>{d.login} / {d.password} · {d.hint}</span>
            </button>
          ))}
        </div>
      </form>
    </div>
  );
}
