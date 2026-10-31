// Чек-лист готовности кампании к модерации: собирается из данных кампании,
// результата проверки API (ошибки и замечания) и справочников.
// Ошибки блокируют отправку, замечания — нет.
import { CHANNEL_RU, FORMAT_RU, STATE_RU, fmtReach, humanize, placeName, topicLabel } from "./ru";
import type { ApiErrorItem, CampaignDetails, Dicts, Validation } from "./types";

export type Status = "ok" | "error" | "warn" | "info";

export interface CheckItem {
  id: string;
  status: Status;
  title: string;
  detail: string;
  action?: { label: string; prompt: string };
}

export interface CheckSection { title: string; items: CheckItem[] }

const HEADER = new Set(["NAME_REQUIRED", "NAME_TOO_LONG", "NAME_DUPLICATE", "MARKETING_NAME_TOO_LONG", "START_DATE_REQUIRED",
  "START_TIME_REQUIRED", "DATE_FORMAT_INVALID", "TIME_FORMAT_INVALID", "END_TIME_WITHOUT_END_DATE", "DATE_RANGE_INVALID",
  "TOPIC_REQUIRED", "TOPIC_INVALID", "KEYWORDS_TOO_LONG", "AUDIENCE_TYPE_REQUIRED", "AUDIENCE_TYPE_INVALID", "WEIGHT_INVALID", "INITIAL_CTR_INVALID"]);
const AUDIENCE = new Set(["SEGMENTS_REQUIRED", "SEGMENT_NOT_FOUND", "SEGMENT_NOT_ACTIVE", "SEGMENT_DUPLICATE", "SEGMENTS_FORBIDDEN_FOR_ALL_USERS"]);

/** Статусы, из которых кампанию можно отправить на модерацию. */
export const EDITABLE_FOR_SUBMIT = ["DRAFT", "NEEDS_WORK", "ACTIVE_EDITING"];

export const fmtCount = fmtReach;

export const plural = (n: number, one: string, few: string, many: string) => {
  const m10 = n % 10, m100 = n % 100;
  if (m10 === 1 && m100 !== 11) return one;
  if (m10 >= 2 && m10 <= 4 && (m100 < 10 || m100 >= 20)) return few;
  return many;
};

export const fmtPeriod = (c: CampaignDetails) =>
  `${fmtDate(c.startDate)} ${c.startTime} — ${c.endDate ? `${fmtDate(c.endDate)} ${c.endTime ?? ""}` : "без даты окончания"}`;

export function fmtDate(iso: string) {
  const [y, m, d] = iso.split("-").map(Number);
  if (!y) return iso;
  return `${d} ${["января", "февраля", "марта", "апреля", "мая", "июня", "июля", "августа", "сентября", "октября", "ноября", "декабря"][m - 1]} ${y}`;
}

export function buildChecklist(c: CampaignDetails, v: Validation | undefined, d: Dicts | null): CheckSection[] {
  const errors = v?.errors ?? [];
  const warns = v?.warningDetails ?? [];
  const used = new Set<ApiErrorItem>();
  const take = (pred: (e: ApiErrorItem) => boolean) => errors.filter((e) => { const m = pred(e); if (m) used.add(e); return m; });
  const warn = (code: string) => warns.find((w) => w.code === code);
  const msgs = (errs: ApiErrorItem[]) => errs.map((e) => humanize(e.message, d)).join("; ");
  const ask = (text: string) => `Кампания «${c.name}»: ${text}`;
  const item = (id: string, errs: ApiErrorItem[], ok: Omit<CheckItem, "id" | "status">, fix: { label: string; prompt: string }, errTitle: string): CheckItem =>
    errs.length ? { id, status: "error", title: errTitle, detail: msgs(errs), action: fix } : { id, status: "ok", ...ok };

  const tagNames = c.tags.map((t) => d?.tags.find((x) => x.id === t)?.name ?? `тег ${t}`);
  const seg = (code: string) => d?.segments.find((s) => s.code === code);
  const segName = (code: string) => (seg(code)?.name ?? code).replace("Исключение. ", "");
  const place = (id: number) => d?.places.find((p) => p.id === id);
  const btype = (id: number) => d?.bannerTypes.find((b) => b.id === id);
  const placesList = (codes?: string) => (codes ?? "").split(",").filter(Boolean).map((x) => `«${placeName(x, d)}»`).join(", ");

  // --- основные параметры
  const header: CheckItem[] = [
    item("header", take((e) => HEADER.has(e.code)), {
      title: "Название, период и тематика заданы",
      detail: `${fmtPeriod(c)} (UTC) · ${topicLabel(c.topic, d)}`,
      action: { label: "Изменить", prompt: ask("хочу изменить название, период или тематику") },
    }, { label: "Исправить", prompt: ask("исправь ошибки в основных параметрах кампании") }, "Ошибки в названии, периоде или тематике"),
  ];
  const tagsWarn = warn("TAGS_MISSING");
  header.push(tagsWarn
    ? { id: "tags", status: "warn", title: "У кампании нет тегов", detail: "Необязательно — отправке не мешает, но без тегов кампанию сложнее найти в отчётах.", action: { label: "Добавить", prompt: ask("предложи подходящий тег и добавь его") } }
    : { id: "tags", status: "ok", title: "Теги добавлены", detail: tagNames.join(", "), action: { label: "Изменить", prompt: ask("хочу поменять теги") } });

  // --- аудитория
  const reach = c.segments.included.reduce((s, x) => s + (seg(x)?.count ?? 0), 0);
  const audienceDetail = c.audienceType === "ALL_USERS"
    ? "Все клиенты приложения, без таргетинга"
    : `${c.segments.included.length} ${plural(c.segments.included.length, "сегмент", "сегмента", "сегментов")} таргетинга, охват до ${fmtReach(reach)} клиентов` +
      (c.segments.excluded.length ? ` · исключены: ${c.segments.excluded.map(segName).join(", ")}` : "");
  const audience: CheckItem[] = [
    item("audience", take((e) => AUDIENCE.has(e.code)), {
      title: "Аудитория настроена", detail: audienceDetail,
      action: { label: "Изменить", prompt: ask("хочу изменить аудиторию") },
    }, { label: "Подобрать сегменты", prompt: ask("подбери сегменты аудитории и объясни выбор") }, "Аудитория не настроена"),
  ];
  if (c.audienceType === "SEGMENTED" && !c.segments.excluded.includes("EXC_UNSUBSCRIBED")) {
    audience.push({ id: "unsub", status: "info", title: "Не исключены клиенты, отказавшиеся от рекламы", detail: "Рекомендуем исключить сегмент «Отписались от рекламы» — 15 млн клиентов.", action: { label: "Исключить", prompt: ask("исключи сегмент «Отписались от рекламы»") } });
  }

  // --- места размещения
  const places: CheckItem[] = [
    item("places", take((e) => e.code === "PLACES_REQUIRED" || (e.code === "ENTITY_NOT_FOUND" && e.field === "places")), {
      title: "Места размещения выбраны", detail: c.places.map((p) => place(p)?.description ?? `место ${p}`).join(" · "),
      action: { label: "Изменить", prompt: ask("хочу изменить места размещения") },
    }, { label: "Выбрать", prompt: ask("подбери места размещения") }, "Места размещения не выбраны"),
  ];
  const inactive = warn("PLACE_INACTIVE");
  places.push(inactive
    ? { id: "inactive", status: "warn", title: "Среди мест есть отключённые", detail: `${placesList(inactive.field)} — показов там не будет. Отправке не мешает.`, action: { label: "Убрать", prompt: ask(`убери отключённые места размещения: ${placesList(inactive.field)}`) } }
    : { id: "inactive", status: "ok", title: "Все места размещения работают", detail: "Отключённых мест нет" });

  // --- креативы
  const bannerErr = take((e) => (e.field ?? "").startsWith("banners["));
  const contentErr = take((e) => (e.field ?? "").startsWith("contents["));
  const creativeErr = take((e) => (e.field ?? "").startsWith("creatives["));
  const formats = [...new Set(c.banners.map((b) => FORMAT_RU[btype(b.bannerTypeId)?.code ?? ""] ?? "баннер"))];
  const platforms = [...new Set(c.creatives.map((x) => CHANNEL_RU[x.channelCode] ?? x.channelCode))];
  const creatives: CheckItem[] = [
    item("banners", bannerErr, {
      title: "Баннеры соответствуют требованиям формата",
      detail: `${c.banners.length} ${plural(c.banners.length, "баннер", "баннера", "баннеров")}: ${formats.join(", ").toLowerCase()} · длина текстов и кнопки в норме`,
      action: { label: "Смотреть", prompt: ask("покажи баннеры кампании") },
    }, { label: "Исправить", prompt: ask("исправь ошибки в баннере и объясни, что поменял") }, "Баннер не соответствует требованиям формата"),
    item("contents", contentErr, {
      title: "Промо-экраны собраны корректно",
      detail: c.contents.length ? `${c.contents.length} ${plural(c.contents.length, "экран", "экрана", "экранов")} — тексты, картинки и кнопки на месте` : "Промо-экранов нет — баннер может работать и без него",
    }, { label: "Исправить экран", prompt: ask("исправь ошибки в промо-экране") }, "Промо-экран собран с ошибками"),
    item("creatives", creativeErr, {
      title: "Креативы подходят для платформ",
      detail: c.creatives.length ? `${c.creatives.length} ${plural(c.creatives.length, "креатив", "креатива", "креативов")}: ${platforms.join(", ")}` : "Креативов пока нет",
    }, { label: "Исправить", prompt: ask("исправь ошибки в креативах") }, "Креативы не подходят для платформ"),
  ];
  if (!c.banners.length && creatives[0].status === "ok") {
    creatives[0] = { id: "banners", status: "info", title: "Баннеров пока нет", detail: "Отправке не мешает, но клиенты не увидят рекламу.", action: { label: "Создать", prompt: ask("создай баннер, промо-экран и креативы для всех мест размещения") } };
  }
  const noCreative = warn("PLACE_NO_CREATIVE");
  creatives.push(noCreative
    ? { id: "coverage", status: "warn", title: "Не для всех мест есть креативы", detail: `Без креатива: ${placesList(noCreative.field)}. Там клиенты рекламу не увидят — отправке не мешает.`, action: { label: "Создать", prompt: ask(`создай баннер, промо-экран и креативы для мест: ${placesList(noCreative.field)}`) } }
    : { id: "coverage", status: "ok", title: "Креативы есть для всех мест размещения", detail: "Формат баннера совпадает с форматом каждого места" });

  const rest = errors.filter((e) => !used.has(e));
  if (rest.length) creatives.push({ id: "rest", status: "error", title: "Другие ошибки проверки", detail: msgs(rest), action: { label: "Разобрать", prompt: ask("разбери ошибки проверки и предложи исправления") } });

  // --- статус кампании
  const status: CheckItem[] = [];
  if (EDITABLE_FOR_SUBMIT.includes(c.state)) {
    status.push({ id: "state", status: "ok", title: "Кампанию можно отправить на модерацию", detail: `Текущий статус — «${STATE_RU[c.state]}»` });
  } else {
    status.push({ id: "state", status: "info", title: "Отправка на модерацию сейчас не требуется", detail: `Текущий статус — «${STATE_RU[c.state] ?? c.state}». На модерацию отправляют черновики, кампании на доработке и запущенные кампании с правками.` });
  }
  if (c.published) status.push({ id: "live", status: "info", title: "Показы идут", detail: "Кампания уже в эфире. Правки увидят клиенты только после повторного запуска." });

  return [
    { title: "Основные параметры", items: header },
    { title: "Аудитория", items: audience },
    { title: "Места размещения", items: places },
    { title: "Креативы", items: creatives },
    { title: "Статус", items: status },
  ];
}

export function counts(sections: CheckSection[]) {
  const all = sections.flatMap((s) => s.items);
  return { blockers: all.filter((i) => i.status === "error"), warnings: all.filter((i) => i.status === "warn") };
}
