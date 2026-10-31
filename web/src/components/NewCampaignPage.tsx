import { useEffect, useMemo, useState } from "react";
import { api } from "../api";
import { topicLabel } from "../ru";
import type { Dicts } from "../types";

// Мастер «Новая кампания»: 1) инструкции из справочников, 2) оформление и описание.
// «Сохранить» собирает бриф и передаёт его ассистенту — дальше кампания собирается в диалоге
// с подтверждением каждого шага (как при обычном брифе).

interface Template { id: string; name: string; title: string; subtitle: string; bg: string; text: string; source: "base" | "past" | "favorite" }

const BASE: Template[] = [
  { id: "green", name: "Зелёный акцент", title: "Премиальная карта", subtitle: "Выгодные условия для вас", bg: "#008A45FF", text: "#FFFFFFFF", source: "base" },
  { id: "light", name: "Светлый минимализм", title: "Специальное предложение", subtitle: "Узнайте больше", bg: "#E9F6EDFF", text: "#1C2520FF", source: "base" },
  { id: "dark", name: "Контрастный", title: "Выгодное предложение", subtitle: "Только для клиентов", bg: "#1C2520FF", text: "#FFFFFFFF", source: "base" },
];
const FAV_KEY = "sber-ad.favorite-templates";
const HEX = /^#[0-9A-Fa-f]{8}$/;
// Избранное читается из браузера — принимаем только корректные записи с цветами #RRGGBBAA.
const loadFavs = (): Template[] => {
  try {
    const xs = JSON.parse(localStorage.getItem(FAV_KEY) ?? "[]");
    return Array.isArray(xs) ? xs.filter((t) => t && typeof t.name === "string" && HEX.test(t.bg) && HEX.test(t.text)).slice(0, 6) : [];
  } catch { return []; }
};
const css = (c: string, fallback = "#21A038") => (HEX.test(c) ? `#${c.slice(1, 7)}` : fallback);

const CONDITIONS = [
  "Укажите основную тему кампании",
  "Опишите ключевое предложение",
  "Не используйте недостоверные обещания («лучший», «№1», «одобрим всем»)",
  "Соблюдайте понятный деловой тон",
  "Укажите действие для пользователя",
];

export default function NewCampaignPage({ dicts, onSubmit, onCancel }: { dicts: Dicts | null; onSubmit: (brief: string) => void; onCancel: () => void }) {
  const [step, setStep] = useState<1 | 2>(1);
  const [platform, setPlatform] = useState("");
  const [audience, setAudience] = useState("");
  const [interest, setInterest] = useState("");
  const [city, setCity] = useState("");
  const [topic, setTopic] = useState("");
  const [error, setError] = useState("");
  const [past, setPast] = useState<Template[]>([]);
  const [favs, setFavs] = useState<Template[]>(loadFavs);
  const [onlyFavs, setOnlyFavs] = useState(false);
  const [tpl, setTpl] = useState<Template>(BASE[0]);
  const [desc, setDesc] = useState("");
  const [saveFav, setSaveFav] = useState(false);

  // шаблоны прошлых кампаний — по баннерам последних кампаний (цвет фона и заголовок)
  useEffect(() => {
    api.campaigns().then(async (xs) => {
      const recent = [...xs].sort((a, b) => b.id - a.id).slice(0, 6);
      const dets = await Promise.all(recent.map((c) => api.campaign(c.id).catch(() => null)));
      const out: Template[] = [];
      for (const d of dets) {
        const b = d?.banners.find((x) => /^#[0-9A-Fa-f]{8}$/.test(String(x.content?.background?.color ?? "")));
        if (d && b && out.length < 3) {
          out.push({ id: `past-${b.id}`, name: d.name, title: b.content.title ?? d.name, subtitle: "Из прошлой кампании",
            bg: String(b.content.background?.color), text: HEX.test(String(b.content.titleStyle?.textColor)) ? String(b.content.titleStyle?.textColor) : "#FFFFFFFF", source: "past" });
        }
      }
      setPast(out);
    }).catch(() => undefined);
  }, []);

  const interests = useMemo(() => (dicts?.segments ?? []).filter((s) => s.code.startsWith("INTRS_") && s.state === "ACTIVE"), [dicts]);
  const cities = useMemo(() => (dicts?.segments ?? []).filter((s) => (s.code.startsWith("CITY_") || s.code.startsWith("REGION_")) && s.state === "ACTIVE"), [dicts]);
  const segmented = audience === "segmented";

  function next() {
    if (!platform || !audience || !topic) { setError("Заполните все поля перед переходом далее."); return; }
    if (segmented && !interest && !city) { setError("Для таргетинга выберите интересы или город."); return; }
    setError("");
    setStep(2);
  }

  function save() {
    const d = desc.trim();
    if (!d) { setError("Добавьте описание темы рекламной кампании."); return; }
    if (saveFav) {
      const fav: Template = { ...tpl, id: `fav-${Date.now()}`, name: `Мой шаблон: ${tpl.name}`, subtitle: "Сохранённый вариант", source: "favorite" };
      const next = [fav, ...favs.filter((f) => !(f.bg === tpl.bg && f.text === tpl.text))].slice(0, 6);
      setFavs(next);
      try { localStorage.setItem(FAV_KEY, JSON.stringify(next)); } catch { /* без хранилища — без избранного */ }
    }
    const seg = (code: string) => dicts?.segments.find((s) => s.code === code)?.name;
    const platforms = platform === "all" ? "iOS, Android и веб-версия (где позволяет формат)" : { ios: "iOS", android: "Android", web: "веб-версия" }[platform];
    const aud = !segmented ? "все клиенты приложения"
      : `таргетинг по сегментам: ${[interest && `интересы «${seg(interest)}»`, city && `город «${seg(city)}»`].filter(Boolean).join(", ")}`;
    onSubmit([
      "Новая кампания из мастера.",
      `Тематика: «${topicLabel(topic, dicts)}». Платформы: ${platforms}. Аудитория: ${aud}.`,
      `Оформление баннера: шаблон «${tpl.name}» — фон ${tpl.bg}, цвет текста ${tpl.text}.`,
      `Описание: ${d}`,
      "Подбери места размещения, даты и креативы, нарисуй изображения для баннера и промо-экрана в этом оформлении; если чего-то не хватает — спроси.",
    ].join("\n"));
  }

  const templates = onlyFavs ? favs : [...BASE, ...past, ...favs];

  return (
    <div className="page new-campaign">
      {step === 1 ? (
        <section>
          <div className="page-heading"><h1>Новая кампания</h1><p>Заполните инструкции для подготовки рекламной кампании</p></div>
          <div className="card instructions-container">
            <div className="card-header"><div><h2>Инструкции</h2><p>Выберите параметры будущей рекламной кампании</p></div><span className="step-badge">Шаг 1 из 2</span></div>
            <div className="instruction-list">
              <label className="instruction-field"><span>Платформа</span>
                <select value={platform} onChange={(e) => setPlatform(e.target.value)}>
                  <option value="">Выберите платформу</option>
                  <option value="ios">iOS</option><option value="android">Android</option><option value="web">Веб-версия</option><option value="all">Все платформы</option>
                </select>
              </label>
              <label className="instruction-field"><span>Аудитория</span>
                <select value={audience} onChange={(e) => setAudience(e.target.value)}>
                  <option value="">Выберите аудиторию</option>
                  <option value="all-users">Все клиенты</option>
                  <option value="segmented">Таргетинг по сегментам</option>
                </select>
              </label>
              {segmented && (
                <>
                  <label className="instruction-field"><span>Интересы и поведение</span>
                    <select value={interest} onChange={(e) => setInterest(e.target.value)}>
                      <option value="">Без уточнения</option>
                      {interests.map((s) => <option key={s.code} value={s.code}>{s.name}</option>)}
                    </select>
                  </label>
                  <label className="instruction-field"><span>Город</span>
                    <select value={city} onChange={(e) => setCity(e.target.value)}>
                      <option value="">Без уточнения</option>
                      {cities.map((s) => <option key={s.code} value={s.code}>{s.name}</option>)}
                    </select>
                  </label>
                </>
              )}
              <label className="instruction-field"><span>Тематика</span>
                <select value={topic} onChange={(e) => setTopic(e.target.value)}>
                  <option value="">Выберите тематику</option>
                  {(dicts?.topics ?? []).map((t) => <option key={t.value} value={t.value}>{topicLabel(t.value, dicts)}</option>)}
                </select>
              </label>
            </div>
            <div className="form-error" role="alert">{error}</div>
            <div className="form-actions">
              <button className="secondary-button" onClick={onCancel}>Назад</button>
              <button className="primary-button" onClick={next}>Далее</button>
            </div>
          </div>
        </section>
      ) : (
        <section>
          <div className="page-heading"><h1>Стили</h1><p>Оформите рекламный баннер для кампании</p></div>
          <div className="styles-layout">
            <div className="styles-main">
              <section className="card">
                <div className="card-header">
                  <div><h2>Шаблоны оформления</h2><p>Шаблоны прошлых кампаний и базовые варианты</p></div>
                  <button className="secondary-button" onClick={() => setOnlyFavs(!onlyFavs)} aria-pressed={onlyFavs}>{onlyFavs ? "× Все шаблоны" : `★ Избранное${favs.length ? ` · ${favs.length}` : ""}`}</button>
                </div>
                <div className="template-grid">
                  {templates.length === 0 && <div className="statistics-empty">В избранном пока пусто — отметьте «Сохранить оформление в избранное».</div>}
                  {templates.map((t) => (
                    <button key={t.id} className={`template-card ${tpl.id === t.id ? "selected" : ""}`} onClick={() => setTpl(t)} aria-pressed={tpl.id === t.id}>
                      <span className="template-preview" style={{ background: css(t.bg), color: css(t.text) }}>
                        <b>{t.title}</b><small>{t.subtitle}</small>
                      </span>
                      <span className="template-name">{t.source === "past" ? `Из кампании «${t.name}»` : t.name}</span>
                    </button>
                  ))}
                </div>
              </section>
              <section className="card">
                <div className="card-header"><div><h2>Описание рекламной кампании</h2><p>Опишите тему, чтобы ассистент подготовил графику и тексты кампании</p></div></div>
                <textarea className="campaign-description" value={desc} onChange={(e) => setDesc(e.target.value)} maxLength={2000}
                  placeholder="Например: расскажите о преимуществах премиальной карты и сделайте акцент на кэшбэке…" />
                <label className="favorite-checkbox"><input type="checkbox" checked={saveFav} onChange={(e) => setSaveFav(e.target.checked)} /> Сохранить оформление в избранное</label>
              </section>
            </div>
            <aside className="card conditions-card">
              <h2>Обязательные условия</h2>
              <ul className="conditions-list">{CONDITIONS.map((c) => <li key={c}>{c}</li>)}</ul>
            </aside>
          </div>
          <div className="form-error" role="alert">{error}</div>
          <div className="form-actions">
            <button className="secondary-button" onClick={() => { setError(""); setStep(1); }}>Назад</button>
            <button className="primary-button" onClick={save}>Сохранить и собрать с ассистентом</button>
          </div>
        </section>
      )}
    </div>
  );
}
