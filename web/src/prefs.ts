// Настройки интерфейса (Настройки → Оформление): хранятся в браузере, применяются к <html>.
export type Theme = "light" | "dark" | "system";
export interface Prefs { theme: Theme; compact: boolean; reduceMotion: boolean; examples: boolean }

const KEY = "sber-ad.prefs";
const DEFAULTS: Prefs = { theme: "light", compact: false, reduceMotion: false, examples: true };

export function loadPrefs(): Prefs {
  try { return { ...DEFAULTS, ...(JSON.parse(localStorage.getItem(KEY) ?? "{}") as Partial<Prefs>) }; } catch { return DEFAULTS; }
}

const systemDark = () => typeof matchMedia === "function" && matchMedia("(prefers-color-scheme: dark)").matches;

export function applyPrefs(p: Prefs) {
  const root = document.documentElement;
  root.dataset.theme = p.theme === "system" ? (systemDark() ? "dark" : "light") : p.theme;
  root.dataset.density = p.compact ? "compact" : "normal";
  root.dataset.motion = p.reduceMotion ? "reduced" : "full";
}

export function savePrefs(p: Prefs) {
  try { localStorage.setItem(KEY, JSON.stringify(p)); } catch { /* без хранилища — до перезагрузки */ }
  applyPrefs(p);
}

// Тема «как в системе» следит за сменой темы ОС на лету.
if (typeof matchMedia === "function") {
  matchMedia("(prefers-color-scheme: dark)").addEventListener?.("change", () => { const p = loadPrefs(); if (p.theme === "system") applyPrefs(p); });
}
applyPrefs(loadPrefs()); // сразу при загрузке, ещё до входа — без вспышки светлой темы
