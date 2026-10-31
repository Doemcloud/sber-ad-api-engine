"""Подсказки и рекомендации в диалоге с ассистентом.

* Варианты ответа: модель, задавая вопрос, дописывает служебную последнюю строку
  «Варианты: … | … | …» — агент её вырезает из текста и отдаёт интерфейсу кнопками.
  Лишних обращений к модели нет.
* Следующие шаги: если вариантов нет, кнопки строятся по состоянию диалога и кампании
  (план ждёт подтверждения, кампания на доработке, готова к отправке и т. д.).
* Рекомендации: что улучшить в текущей кампании и почему — из замечаний проверки,
  справочников и состава креативов. Каждая рекомендация — готовая просьба ассистенту.
Всё детерминированно и не требует модели."""
from __future__ import annotations

import re

_CHOICES = re.compile(r"^\s*варианты(?:\s+ответа)?\s*:\s*(.+?)\s*$", re.IGNORECASE)
MAX_CHIPS = 4
MAX_RECS = 4
EDITABLE = {"DRAFT", "NEEDS_WORK", "APPROVED", "ACTIVE", "ACTIVE_EDITING"}
# доли показов по платформам (те же, что в модели статистики)
PLATFORM = {"iOS": ("iOS", 38), "ANDROID": ("Android", 52), "WEB": ("веб-версию", 10)}


def extract_choices(text: str) -> tuple[str, list[str]]:
    """Вырезает строку «Варианты: a | b | c» из ответа модели → (текст без неё, варианты)."""
    if not text:
        return text, []
    lines = text.rstrip().split("\n")
    for i in range(len(lines) - 1, max(len(lines) - 4, -1), -1):  # ищем в последних строках
        m = _CHOICES.match(lines[i].replace("*", "").replace("_", " "))
        if m:
            raw = re.split(r"\s*[|;]\s*", m.group(1))
            opts = []
            for o in raw:
                o = o.strip().rstrip(".").strip()
                for a, b in (("«", "»"), ('"', '"'), ("'", "'"), ("`", "`")):  # только парные кавычки вокруг всего варианта
                    if len(o) > 1 and o.startswith(a) and o.endswith(b) and o.count(a) == 1:
                        o = o[1:-1].strip()
                if o and len(o) <= 60 and o.lower() not in (x.lower() for x in opts):
                    opts.append(o)
            clean = "\n".join(lines[:i] + lines[i + 1:]).rstrip()
            return clean, opts[:MAX_CHIPS]
    return text, []


def _seg_name(code: str, dicts: dict) -> str:
    s = next((x for x in dicts.get("segments", []) if x["code"] == code), None)
    return (s["name"] if s else code).replace("Исключение. ", "")


def recommendations(c: dict | None, v: dict | None, dicts: dict, role: str) -> list[dict]:
    """Рекомендации по кампании: [{id, title, why, prompt}] — по убыванию пользы."""
    if not c or role != "campaignManager":
        return []
    name, state, out = c.get("name", ""), c.get("state"), []
    add = lambda id_, title, why, prompt: out.append({"id": id_, "title": title, "why": why, "prompt": prompt})

    if state == "STOPPED":
        add("resume", "Возобновить показы", "Остановленную кампанию можно запустить снова с разрешения модератора.",
            f"Запроси возобновление кампании «{name}»")
        return out
    if state not in EDITABLE:
        return out

    codes = {w.get("code") for w in (v or {}).get("warningDetails", [])}
    errors = (v or {}).get("errors", [])
    if errors:
        add("errors", "Исправить ошибки перед модерацией", errors[0].get("message", "Есть ошибки проверки."),
            f"Кампания «{name}»: исправь ошибки проверки")
    if "PLACE_NO_CREATIVE" in codes:
        add("creatives", "Сделать креативы для всех мест размещения", "Там, где нет креатива, клиенты рекламу не увидят.",
            f"Кампания «{name}»: создай креативы для всех мест размещения")
    if "PLACE_INACTIVE" in codes:
        add("inactive", "Убрать отключённое место размещения", "В отключённых местах показов нет — место только путает отчёты.",
            f"Кампания «{name}»: убери отключённые места размещения")

    segs = c.get("segments") or {}
    if c.get("audienceType") == "SEGMENTED":
        if "EXC_UNSUBSCRIBED" not in (segs.get("excluded") or []):
            unsub = next((x["count"] for x in dicts.get("segments", []) if x["code"] == "EXC_UNSUBSCRIBED"), 0)
            add("unsub", "Исключить отписавшихся от рекламы",
                f"{unsub / 1e6:.0f} млн клиентов просили не показывать им рекламу — меньше жалоб и бесполезных показов.",
                f"Кампания «{name}»: исключи сегмент «Отписались от рекламы»")
        reach = sum(x["count"] for x in dicts.get("segments", []) if x["code"] in (segs.get("included") or []))
        if 0 < reach < 1_000_000:
            add("narrow", "Расширить аудиторию", f"Сейчас охват около {reach // 1000} тыс. клиентов — кампании может не хватить показов.",
                f"Кампания «{name}»: предложи, какими сегментами расширить аудиторию")

    btypes = {b["id"]: b for b in dicts.get("banner_types", [])}
    creatives = c.get("creatives") or []
    for b in c.get("banners") or []:
        have = {x["channelCode"] for x in creatives if x.get("bannerId") == b["id"]}
        allowed = (btypes.get(b.get("bannerTypeId")) or {}).get("channels") or []
        missing = [ch for ch in allowed if ch not in have and ch in PLATFORM]
        if have and missing:
            ch = max(missing, key=lambda x: PLATFORM[x][1])
            label, share = PLATFORM[ch]
            add(f"platform-{b['id']}-{ch}", f"Добавить {label}",
                f"Баннер «{b.get('name', '')}» не показывается на этой платформе — это примерно {share}% показов.",
                f"Кампания «{name}»: размести баннер «{b.get('name', '')}» ещё и на платформе {label}")
            break
    if (c.get("banners") or []) and not (c.get("contents") or []):
        add("promo", "Добавить промо-экран", "По нажатию на баннер клиент увидит подробности и кнопку действия — так больше целевых действий.",
            f"Кампания «{name}»: добавь промо-экран с кнопкой действия")
    if "TAGS_MISSING" in codes:
        add("tags", "Добавить теги", "По тегам кампанию быстрее найти в списке и отчётах.", f"Кампания «{name}»: предложи теги")
    if not c.get("endDate"):
        add("enddate", "Указать дату окончания", "Без даты окончания реклама показывается бессрочно — легко забыть её выключить.",
            f"Кампания «{name}»: предложи дату окончания показов")
    return out[:MAX_RECS]


def next_steps(pending: bool, awaiting_fix: bool, c: dict | None, v: dict | None, role: str) -> list[str]:
    """Кнопки быстрых ответов, когда модель сама вариантов не предложила."""
    if pending or role != "campaignManager":
        return []
    if awaiting_fix:
        return ["Поменяй даты", "Поменяй аудиторию", "Сократи заголовок", "Другое место размещения"]
    if not c:
        return []
    state, errors = c.get("state"), (v or {}).get("errors", [])
    steps: list[str] = []
    if state == "NEEDS_WORK":
        steps.append("Исправь замечания модератора")
    if state in ("DRAFT", "NEEDS_WORK", "ACTIVE_EDITING"):
        steps.append("Исправь ошибки" if errors else "Отправь на модерацию")
    elif state == "APPROVED":
        steps.append("Запусти кампанию")
    elif state == "ON_MODERATION":
        steps.append("Что будет дальше?")
    elif state == "STOPPED":
        steps.append("Возобнови показы")
    elif state == "ACTIVE":
        steps.append("Поменяй текст баннера")
    steps.append("Покажи, что можно улучшить")  # заменяется на главную рекомендацию; без рекомендаций — убирается
    return steps[:MAX_CHIPS]
