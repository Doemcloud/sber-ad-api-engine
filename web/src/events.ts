// Лента событий (GET /audit): человеческие формулировки для «Главной», уведомлений и истории.
import type { Role } from "./types";

export interface FeedEntry {
  id: number; campaignId: number; campaignName: string; entity: string; entityId: number;
  action: string; at: string; actor: string; comment: string | null;
}
export type Tone = "success" | "warning" | "info" | "neutral";
export interface EventView { text: string; tone: Tone; status: string }

export function describe(e: FeedEntry): EventView {
  const n = e.campaignName ? `«${e.campaignName}»` : "Кампания";
  const subject = e.entity === "BANNER" ? "баннер" : e.entity === "CONTENT" ? "промо-экран" : e.entity === "CREATIVE" ? "размещение на платформе" : "";
  switch (e.action) {
    case "DECLINE": return { text: `Кампания ${n} не прошла модерацию — нажмите для редактирования`, tone: "warning", status: "Нужны правки" };
    case "APPROVE": return { text: `Кампания ${n} одобрена модератором — можно запускать`, tone: "success", status: "Одобрена" };
    case "ACTIVATE": return { text: `Кампания ${n} запущена — реклама в приложении`, tone: "success", status: "Запущена" };
    case "STOP": return { text: `Показы кампании ${n} остановлены`, tone: "neutral", status: "Остановлена" };
    case "TO_MODERATION": return { text: `Кампания ${n} отправлена на модерацию`, tone: "info", status: "На модерации" };
    case "RESUME_REQUEST": return { text: `Запрошено возобновление показов ${n}`, tone: "info", status: "На модерации" };
    case "CREATE": return { text: subject ? `В кампании ${n} создан ${subject}` : `Создана кампания ${n}`, tone: "neutral", status: "Создание" };
    case "DELETE": return { text: subject ? `В кампании ${n} удалён ${subject}` : `Удалена кампания ${n}`, tone: "neutral", status: "Удаление" };
    default: return { text: subject ? `В кампании ${n} изменён ${subject}` : `Изменена кампания ${n}`, tone: "neutral", status: "Изменение" };
  }
}

// Что важно знать роли: менеджеру — решения модератора и запуски, модератору — новые заявки.
export function isNotification(e: FeedEntry, role: Role): boolean {
  return role === "campaignManager"
    ? ["DECLINE", "APPROVE", "ACTIVATE"].includes(e.action)
    : ["TO_MODERATION", "RESUME_REQUEST"].includes(e.action);
}

// «Сегодня, 12:40» / «Вчера, 17:25» / «26 октября, 10:15». Время аудита — UTC.
export function when(iso: string): string {
  const d = new Date(/[zZ]|[+-]\d\d:?\d\d$/.test(iso) ? iso : `${iso}Z`);
  if (isNaN(d.getTime())) return iso;
  const time = d.toLocaleTimeString("ru-RU", { hour: "2-digit", minute: "2-digit" });
  const day = (x: Date) => new Date(x.getFullYear(), x.getMonth(), x.getDate()).getTime();
  const diff = Math.round((day(new Date()) - day(d)) / 86400000);
  if (diff === 0) return `Сегодня, ${time}`;
  if (diff === 1) return `Вчера, ${time}`;
  return `${d.toLocaleDateString("ru-RU", { day: "numeric", month: "long" })}, ${time}`;
}
