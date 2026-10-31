"""Инструменты агента: по одному на каждый вызов API (task.md §6.2) + две
локальные проверки JSON. У каждого — JSON-схема параметров. Пишущие
инструменты (kind="write") не вызывают API сразу: они ставят шаг в план,
который выполняется только после подтверждения человека."""
from __future__ import annotations

S = {"type": "string"}
INT = {"type": "integer"}
CID = {"type": "integer", "description": "id кампании или ссылка вида \"$camp\" на кампанию, создаваемую в этом же плане"}
REF = {"type": "string", "description": "имя ссылки на результат шага (например camp, banner1, content1, tag1), чтобы использовать его id в следующих шагах как \"$имя\""}

STYLE = {"type": "object", "properties": {
    "fontSize": {"type": "integer", "minimum": 10, "maximum": 40},
    "fontWeight": {"type": "string", "enum": ["thin", "light", "regular", "medium", "semi-bold", "bold"]},
    "textColor": {"type": "string", "description": "#RRGGBBAA"}}}
LINK = {"type": "object", "description": "deep-link/URL по платформам; обязателен при externalLink/openSmartLink, запрещён при closeCampaign/doneCampaign",
        "properties": {"iOS": S, "android": S, "web": S}}
ACTION = {"type": "string", "enum": ["default", "externalLink", "openSmartLink", "closeCampaign", "doneCampaign"]}

BANNER_CONTENT = {
    "type": "object",
    "description": "JSON-контент баннера (task.md §2.6). Лимиты: STORY title≤100, text≤500; SMART_BANNER title≤250, text≤1000.",
    "properties": {
        "title": S, "text": S, "titleStyle": STYLE, "textStyle": STYLE,
        "background": {"type": "object", "properties": {"color": {"type": "string", "description": "#RRGGBBAA"}}},
        "image": {"type": "object", "properties": {"url": {"type": "string", "description": "https://..."}}},
        "buttonName": S, "actionType": ACTION, "link": LINK,
        "voiceOver": {"type": "string", "description": "озвучка для accessibility, ≤200"},
    },
    "required": ["actionType"],
}

PROMO_CONTENT = {
    "type": "object",
    "description": ('PROMO-экран (task.md §2.7): {"role":"promo","component":{"role":"linearContainer","axis":"v",'
                    '"style":{"backgroundColor":"#FFFFFFFF"},"components":[1..6 компонентов]}}. Компоненты: '
                    '{"role":"text","format":"none"|"html","text":"...","textStyle":{...}}, '
                    '{"role":"image","url":"https://...","aspectRatio":2.0}, '
                    '{"role":"button","text":"...","actionType":"...","link":{...}}'),
    "properties": {"role": {"type": "string", "enum": ["promo"]}, "component": {"type": "object"}},
    "required": ["role", "component"],
}

CAMPAIGN = {
    "type": "object",
    "description": "Шапка кампании (task.md §2.2). Значения enum и id — только из справочников.",
    "properties": {
        "name": {"type": "string", "description": "≤100, уникальное"},
        "marketingName": S,
        "startDate": {"type": "string", "description": "YYYY-MM-DD"},
        "startTime": {"type": "string", "description": "HH:mm, UTC"},
        "endDate": {"type": "string", "description": "YYYY-MM-DD; пусто = бессрочно"},
        "endTime": {"type": "string", "description": "HH:mm"},
        "topic": {"type": "string", "description": "value из get_topics"},
        "tags": {"type": "array", "items": INT, "description": "id тегов из get_tags или \"$ref\" нового тега"},
        "keywords": {"type": "string", "description": "через ;"},
        "audienceType": {"type": "string", "enum": ["ALL_USERS", "SEGMENTED"]},
        "weight": {"type": "number", "description": "по умолчанию 0; выше — больше шансов на показ"},
        "initialCtr": {"type": "number", "description": "по умолчанию 15"},
        "places": {"type": "array", "items": INT, "description": "id мест показа из get_places или \"$ref\" нового места"},
    },
}


def obj(props: dict, required: list[str] | None = None) -> dict:
    return {"type": "object", "properties": props, "required": required or []}


# name: (kind, method, path, role, description, parameters)
TOOLS: dict[str, tuple] = {
    # --- справочники (только чтение) ---
    "get_topics": ("read", "GET", "/topics", None, "Справочник тематик (фиксированный enum из 11 значений).", obj({})),
    "get_tags": ("read", "GET", "/tags", None, "Справочник тегов.", obj({})),
    "get_channels": ("read", "GET", "/channels", None, "Каналы: iOS, ANDROID, WEB (регистр важен).", obj({})),
    "get_banner_types": ("read", "GET", "/banner-types", None, "Типы баннеров с лимитами title/text и допустимыми каналами.", obj({})),
    "get_segment_types": ("read", "GET", "/segment-types", None, "Типы сегментов.", obj({})),
    "get_segments": ("read", "GET", "/segments", None, "Сегменты: код, название, тип, состояние, число клиентов. Выбирать можно только ACTIVE.", obj({})),
    "get_places": ("read", "GET", "/places", None, "Места показа: код, описание, defaultBanner (какой тип баннера генерировать), состояние.", obj({})),
    # --- кампании (чтение) ---
    "list_campaigns": ("read", "GET", "/campaigns", None, "Список кампаний: id, name, state, published, topic, даты.", obj({})),
    "get_campaign": ("read", "GET", "/campaigns/{campaign_id}", None, "Кампания целиком: шапка, места, сегменты, баннеры, контент, креативы.", obj({"campaign_id": INT}, ["campaign_id"])),
    "get_warnings": ("read", "GET", "/campaigns/{campaign_id}/warnings", None, "Прогон валидации: errors (блокируют модерацию) и warnings.", obj({"campaign_id": INT}, ["campaign_id"])),
    "get_audit": ("read", "GET", "/campaigns/{campaign_id}/audit", None, "Журнал аудита: кто, что, когда; комментарий модератора при decline.", obj({"campaign_id": INT}, ["campaign_id"])),
    # --- локальные проверки ---
    "validate_banner": ("local", None, None, None, "Проверить JSON баннера по схеме и лимитам типа до отправки.", obj({"bannerTypeId": INT, "content": BANNER_CONTENT}, ["bannerTypeId", "content"])),
    "validate_content": ("local", None, None, None, "Проверить JSON PROMO-контента по схеме до отправки.", obj({"content": PROMO_CONTENT}, ["content"])),
    # --- справочники модуля кампаний (запись) ---
    "create_place": ("write", "POST", "/places", "campaignManager", "Создать место показа (только если подходящего нет). После создания добавьте его в places кампании через \"$ref\".", obj({"code": S, "description": S, "ref": REF}, ["code", "description"])),
    "create_tag": ("write", "POST", "/tags", "campaignManager", "Создать тег (только если подходящего нет).", obj({"name": S, "ref": REF}, ["name"])),
    # --- кампания ---
    "create_campaign": ("write", "POST", "/campaigns", "campaignManager", "Создать кампанию (state=DRAFT).", obj({"campaign": CAMPAIGN, "ref": REF}, ["campaign"])),
    "update_campaign": ("write", "PUT", "/campaigns/{campaign_id}", "campaignManager", "Изменить шапку/места. Передайте только меняемые поля — агент сам сделает GET → слияние → PUT.", obj({"campaign_id": CID, "campaign": CAMPAIGN}, ["campaign_id", "campaign"])),
    "delete_campaign": ("write", "DELETE", "/campaigns/{campaign_id}", "campaignManager", "Удалить кампанию (только DRAFT/NEEDS_WORK без активного показа).", obj({"campaign_id": INT}, ["campaign_id"])),
    "set_segments": ("write", "PUT", "/campaigns/{campaign_id}/segments", "campaignManager", "Задать сегменты включения (OR) и исключения. Только для SEGMENTED.", obj({"campaign_id": CID, "included": {"type": "array", "items": S}, "excluded": {"type": "array", "items": S}}, ["campaign_id", "included", "excluded"])),
    # --- баннеры ---
    "create_banner": ("write", "POST", "/campaigns/{campaign_id}/banners", "campaignManager", "Создать баннер. bannerTypeId: 1 — STORY, 2 — SMART_BANNER (бери defaultBanner места).", obj({"campaign_id": CID, "name": S, "bannerTypeId": INT, "content": BANNER_CONTENT, "ref": REF}, ["campaign_id", "name", "bannerTypeId", "content"])),
    "update_banner": ("write", "PUT", "/campaigns/{campaign_id}/banners/{banner_id}", "campaignManager", "Изменить баннер (переданные поля заменяют текущие).", obj({"campaign_id": CID, "banner_id": INT, "name": S, "bannerTypeId": INT, "content": BANNER_CONTENT}, ["campaign_id", "banner_id"])),
    "delete_banner": ("write", "DELETE", "/campaigns/{campaign_id}/banners/{banner_id}", "campaignManager", "Удалить баннер (и его креативы).", obj({"campaign_id": CID, "banner_id": INT}, ["campaign_id", "banner_id"])),
    # --- контент ---
    "create_content": ("write", "POST", "/campaigns/{campaign_id}/contents", "campaignManager", "Создать PROMO-экран, который открывается по нажатию на баннер.", obj({"campaign_id": CID, "name": S, "content": PROMO_CONTENT, "ref": REF}, ["campaign_id", "name", "content"])),
    "update_content": ("write", "PUT", "/campaigns/{campaign_id}/contents/{content_id}", "campaignManager", "Изменить PROMO-экран.", obj({"campaign_id": CID, "content_id": INT, "name": S, "content": PROMO_CONTENT}, ["campaign_id", "content_id"])),
    "delete_content": ("write", "DELETE", "/campaigns/{campaign_id}/contents/{content_id}", "campaignManager", "Удалить PROMO-экран.", obj({"campaign_id": CID, "content_id": INT}, ["campaign_id", "content_id"])),
    # --- креативы ---
    "create_creative": ("write", "POST", "/campaigns/{campaign_id}/creatives", "campaignManager", "Связать баннер (+ PROMO) с каналом. STORY — только iOS/ANDROID; SMART_BANNER — iOS/ANDROID/WEB. Одна пара баннер+канал — один креатив.", obj({"campaign_id": CID, "name": S, "bannerId": INT, "contentId": INT, "channelCode": {"type": "string", "enum": ["iOS", "ANDROID", "WEB"]}, "ref": REF}, ["campaign_id", "name", "bannerId", "channelCode"])),
    "update_creative": ("write", "PUT", "/campaigns/{campaign_id}/creatives/{creative_id}", "campaignManager", "Изменить креатив.", obj({"campaign_id": CID, "creative_id": INT, "name": S, "bannerId": INT, "contentId": INT, "channelCode": S}, ["campaign_id", "creative_id"])),
    "delete_creative": ("write", "DELETE", "/campaigns/{campaign_id}/creatives/{creative_id}", "campaignManager", "Удалить креатив.", obj({"campaign_id": CID, "creative_id": INT}, ["campaign_id", "creative_id"])),
    # --- жизненный цикл ---
    "to_moderation": ("write", "POST", "/campaigns/{campaign_id}/to-moderation", "campaignManager", "Отправить на модерацию (из DRAFT, NEEDS_WORK, ACTIVE_EDITING; без ошибок валидации).", obj({"campaign_id": CID}, ["campaign_id"])),
    "approve": ("write", "POST", "/campaigns/{campaign_id}/approve", "campaignModerator", "Одобрить (роль модератора, только ON_MODERATION).", obj({"campaign_id": INT}, ["campaign_id"])),
    "decline": ("write", "POST", "/campaigns/{campaign_id}/decline", "campaignModerator", "Отклонить с обязательным комментарием (роль модератора).", obj({"campaign_id": INT, "comment": S}, ["campaign_id", "comment"])),
    "activate": ("write", "POST", "/campaigns/{campaign_id}/activate", "campaignManager", "Активировать одобренную кампанию: выгрузка в Content Broker, published=true.", obj({"campaign_id": INT}, ["campaign_id"])),
    "stop": ("write", "POST", "/campaigns/{campaign_id}/stop", "campaignManager", "Остановить показ (published=true → STOPPED). Возобновить нельзя.", obj({"campaign_id": INT}, ["campaign_id"])),
}


def schemas() -> list[dict]:
    """Описание инструментов в нейтральном виде: name, description, parameters."""
    out = []
    for name, (kind, method, path, role, desc, params) in TOOLS.items():
        d = desc
        if kind == "write":
            d += " Требует подтверждения менеджера: шаг добавится в план."
        out.append({"name": name, "description": d, "parameters": params,
                    "x-kind": kind, "x-http": f"{method} {path}" if method else None, "x-role": role})
    return out
