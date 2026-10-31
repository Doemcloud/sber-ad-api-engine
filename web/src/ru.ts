// Словарь интерфейса: технические коды API → язык маркетолога.
// humanize() переводит коды в текстах, которые приходят от API и ассистента.
import type { Dicts } from "./types";

export const STATE_RU: Record<string, string> = {
  DRAFT: "Черновик",
  ON_MODERATION: "На модерации",
  NEEDS_WORK: "На доработке",
  APPROVED: "Одобрена",
  ACTIVE: "Запущена",
  ACTIVE_EDITING: "Запущена, есть правки",
  STOPPED: "Остановлена",
  ARCHIVED: "В архиве",
};

export const AUDIENCE_RU: Record<string, string> = { ALL_USERS: "Все клиенты", SEGMENTED: "Таргетинг по сегментам" };

export const FORMAT_RU: Record<string, string> = { STORY: "Сторис", SMART_BANNER: "Смарт-баннер", PROMO: "Промо-экран" };

export const CHANNEL_RU: Record<string, string> = { iOS: "iOS", ANDROID: "Android", WEB: "Веб-версия" };

export const SEGMENT_TYPE_RU: Record<string, string> = {
  GEO_CITY: "Город", GEO_REGION: "Регион", AGE: "Возраст", GENDER: "Пол", INTEREST: "Интересы",
  PRODUCT: "Продукты банка", CHANNEL: "Канал обслуживания", BASIC: "Исключения",
};

export const TOPIC_RU: Record<string, string> = { LIFESTYLE: "Лайфстайл" };

export const ACTION_TYPE_RU: Record<string, string> = {
  default: "без перехода", externalLink: "переход по ссылке", openSmartLink: "переход в раздел приложения",
  closeCampaign: "закрыть рекламу", doneCampaign: "завершить показ",
};

export const ENTITY_RU: Record<string, string> = {
  CAMPAIGN: "кампания", BANNER: "баннер", CONTENT: "промо-экран", CREATIVE: "креатив", SEGMENTS: "аудитория", PLACE: "место размещения", TAG: "тег",
};

export const AUDIT_ACTION_RU: Record<string, string> = {
  CREATE: "создание", UPDATE: "изменение", DELETE: "удаление", TO_MODERATION: "отправлена на модерацию",
  DECLINE: "возвращена на доработку", APPROVE: "одобрена", ACTIVATE: "запущена", STOP: "показы остановлены",
  RESUME_REQUEST: "запрошено возобновление показов",
};

export const FIELD_RU: Record<string, string> = {
  name: "название", marketingName: "рекламное название", startDate: "дата старта", startTime: "время старта",
  endDate: "дата окончания", endTime: "время окончания", topic: "тематика", tags: "теги", keywords: "ключевые слова",
  audienceType: "тип аудитории", weight: "приоритет показа", initialCtr: "прогнозный CTR", places: "места размещения",
  included: "таргетинг", excluded: "исключения", content: "содержание", bannerTypeId: "формат", channelCode: "платформа",
  bannerId: "баннер", contentId: "промо-экран",
};

export const topicLabel = (value: string, d: Dicts | null) =>
  TOPIC_RU[value] ?? d?.topics.find((t) => t.value === value)?.label ?? value;

export const placeName = (code: string, d: Dicts | null) => d?.places.find((p) => p.code === code)?.description ?? code;

export const fmtReach = (n: number) =>
  n >= 1_000_000 ? `${(n / 1_000_000).toLocaleString("ru-RU", { maximumFractionDigits: 1 })} млн` : n.toLocaleString("ru-RU");

const escape = (s: string) => s.replace(/[.*+?^${}()|[\]\\]/g, "\\$&");

/** Заменяет технические коды на русские названия. Справочники нужны для сегментов и мест. */
export function humanize(text: string | null | undefined, d: Dicts | null): string {
  if (!text) return "";
  let t = text;
  const pairs: [string, string][] = [];
  for (const s of d?.segments ?? []) pairs.push([s.code, `«${s.name.replace("Исключение. ", "")}»`]);
  for (const p of d?.places ?? []) pairs.push([p.code, `«${p.description}»`]);
  for (const [k, v] of Object.entries(STATE_RU)) pairs.push([k, `«${v}»`]);
  for (const [k, v] of Object.entries(AUDIENCE_RU)) pairs.push([k, `«${v}»`]);
  for (const [k, v] of Object.entries(FORMAT_RU)) pairs.push([k, v.toLowerCase()]);
  pairs.push(["ANDROID", "Android"], ["WEB", "веб-версия"], ["published=true", "показ идёт"], ["published=false", "показ не идёт"]);
  for (const [k, v] of Object.entries(ACTION_TYPE_RU)) pairs.push([`actionType=${k}`, `действие «${v}»`]);
  pairs.push(["actionType", "действие кнопки"], ["Content Broker", "систему доставки рекламы"], ["JSON", "макет"]);
  // длинные коды первыми, чтобы SMART_BANNER не съел BANNER и т. п.
  pairs.sort((a, b) => b[0].length - a[0].length);
  for (const [code, ru] of pairs) {
    t = t.replace(new RegExp(`(?<![\\w«])${escape(code)}(?![\\w»])`, "g"), ru);
  }
  return t.replace(/«(«[^»]+»)»/g, "$1");
}

export const PERSON_RU: Record<string, string> = { "ivanov.p": "Павел Иванов", "petrova.m": "Мария Петрова" };
export const person = (login: string) => PERSON_RU[login] ?? login;

export function fmtDateTime(iso: string) {
  const d = new Date(iso.endsWith("Z") ? iso : `${iso}Z`);
  if (isNaN(d.getTime())) return iso;
  return d.toLocaleString("ru-RU", { day: "numeric", month: "short", hour: "2-digit", minute: "2-digit", timeZone: "UTC" });
}
