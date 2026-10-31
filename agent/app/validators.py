"""Локальная валидация JSON баннера и PROMO-контента ДО отправки в API
(task.md §2.6–2.7, §6.2). Правила зеркалят Go-бэкенд; коды — из каталога
validation_rules.json, чтобы агент и бэкенд говорили на одном языке."""
from __future__ import annotations

import re
from datetime import datetime
from typing import Any

ACTION_TYPES = ["default", "externalLink", "openSmartLink", "closeCampaign", "doneCampaign"]
FONT_WEIGHTS = ["thin", "light", "regular", "medium", "semi-bold", "bold"]
BANNER_KEYS = {"title", "text", "titleStyle", "textStyle", "background", "image", "buttonName", "actionType", "link", "voiceOver"}
LINK_KEYS = {"iOS", "android", "web"}
LINK_REQUIRED = {"externalLink", "openSmartLink"}
LINK_FORBIDDEN = {"closeCampaign", "doneCampaign"}
COLOR = re.compile(r"^#[0-9A-Fa-f]{8}$")
TIME = re.compile(r"^([01]\d|2[0-3]):[0-5]\d$")


def err(code: str, field: str, message: str) -> dict:
    return {"code": code, "field": field, "message": message}


# Адреса собственного хранилища изображений API ({PUBLIC_URL}/media/): их ссылки принимаются
# и без https (локальный запуск). Заполняет агент по ответу GET /health.
TRUSTED_MEDIA: set[str] = set()


def _https(v: Any) -> bool:
    if isinstance(v, str) and any(v.startswith(p) and len(v) > len(p) for p in TRUSTED_MEDIA):
        return True
    return isinstance(v, str) and v.startswith("https://") and len(v) > len("https://")


def _color(v: Any) -> bool:
    return isinstance(v, str) and bool(COLOR.match(v))


def validate_action(m: dict, path: str) -> list[dict]:
    out: list[dict] = []
    if "actionType" not in m:
        return [err("BANNER_ACTION_TYPE_REQUIRED", f"{path}.actionType", "Не задано действие (actionType)")]
    at = m["actionType"]
    if at not in ACTION_TYPES:
        return [err("ACTION_TYPE_INVALID", f"{path}.actionType", f"actionType={at!r}; допустимо: {', '.join(ACTION_TYPES)}")]
    link = m.get("link")
    non_empty = False
    if "link" in m:
        if not isinstance(link, dict):
            out.append(err("LINK_INVALID", f"{path}.link", "link должен быть объектом {iOS, android, web}"))
        else:
            for k, v in link.items():
                if k not in LINK_KEYS:
                    out.append(err("LINK_INVALID", f"{path}.link.{k}", f"неизвестный ключ {k}; допустимо iOS, android, web"))
                if isinstance(v, str) and v:
                    non_empty = True
    if at in LINK_REQUIRED and not non_empty:
        out.append(err("LINK_REQUIRED", f"{path}.link", f"для actionType={at} нужна ссылка хотя бы для одной платформы"))
    if at in LINK_FORBIDDEN and "link" in m:
        out.append(err("LINK_FORBIDDEN", f"{path}.link", f"для actionType={at} ссылка запрещена — уберите link"))
    return out


def _style(v: Any, path: str) -> list[dict]:
    if not isinstance(v, dict):
        return [err("STYLE_INVALID", path, "стиль должен быть объектом")]
    out = []
    if "fontSize" in v and not (isinstance(v["fontSize"], (int, float)) and 10 <= v["fontSize"] <= 40):
        out.append(err("STYLE_INVALID", f"{path}.fontSize", f"fontSize={v['fontSize']}, допустимо 10..40"))
    if "fontWeight" in v and v["fontWeight"] not in FONT_WEIGHTS:
        out.append(err("STYLE_INVALID", f"{path}.fontWeight", f"fontWeight={v['fontWeight']!r}; допустимо: {', '.join(FONT_WEIGHTS)}"))
    if "textColor" in v and not _color(v["textColor"]):
        out.append(err("COLOR_INVALID", f"{path}.textColor", f"{v['textColor']!r} — нужен формат #RRGGBBAA"))
    return out


def validate_banner(name: str, banner_type: dict | None, content: Any) -> list[dict]:
    """banner_type — запись справочника banner-types (с лимитами) или None, если тип неизвестен."""
    out: list[dict] = []
    if not (name or "").strip():
        out.append(err("BANNER_NAME_REQUIRED", "name", "Название баннера обязательно"))
    if banner_type is None:
        out.append(err("ENTITY_NOT_FOUND", "bannerTypeId", "Такого типа баннера нет в справочнике (1 — STORY, 2 — SMART_BANNER)"))
    if not isinstance(content, dict):
        return out + [err("BANNER_CONTENT_INVALID", "content", "content должен быть объектом")]
    for k in content:
        if k not in BANNER_KEYS:
            out.append(err("BANNER_CONTENT_INVALID", f"content.{k}", f"неизвестное поле {k}"))
    bt = banner_type or {}
    for key, limit_key, code in (("title", "titleMaxLength", "BANNER_TITLE_TOO_LONG"), ("text", "textMaxLength", "BANNER_TEXT_TOO_LONG")):
        if key in content:
            v = content[key]
            if not isinstance(v, str):
                out.append(err("BANNER_CONTENT_INVALID", f"content.{key}", f"{key} должен быть строкой"))
            elif bt.get(limit_key) and len(v) > bt[limit_key]:
                out.append(err(code, f"content.{key}", f"{len(v)} символов, лимит для {bt.get('code')} — {bt[limit_key]}"))
    for k in ("titleStyle", "textStyle"):
        if k in content:
            out += _style(content[k], f"content.{k}")
    if "background" in content:
        bg = content["background"]
        if not isinstance(bg, dict):
            out.append(err("BANNER_CONTENT_INVALID", "content.background", "background должен быть объектом {color}"))
        elif "color" in bg and not _color(bg["color"]):
            out.append(err("COLOR_INVALID", "content.background.color", f"{bg['color']!r} — нужен формат #RRGGBBAA"))
    if "image" in content:
        img = content["image"]
        if not isinstance(img, dict) or not _https(img.get("url")):
            out.append(err("IMAGE_URL_INVALID", "content.image.url", "image должен быть {url: \"https://...\"}"))
    if "buttonName" in content and not isinstance(content["buttonName"], str):
        out.append(err("BANNER_CONTENT_INVALID", "content.buttonName", "buttonName должен быть строкой"))
    if "voiceOver" in content and (not isinstance(content["voiceOver"], str) or len(content["voiceOver"]) > 200):
        out.append(err("VOICE_OVER_TOO_LONG", "content.voiceOver", "voiceOver — строка до 200 символов"))
    out += validate_action(content, "content")
    return out


def validate_content(name: str, content_type: str, content: Any) -> list[dict]:
    out: list[dict] = []
    if not (name or "").strip():
        out.append(err("CONTENT_NAME_REQUIRED", "name", "Название контента обязательно"))
    if content_type != "PROMO":
        out.append(err("CONTENT_TYPE_INVALID", "contentType", "В MVP только PROMO"))
    if not isinstance(content, dict) or content.get("role") != "promo":
        return out + [err("CONTENT_SCHEMA_INVALID", "content.role", 'корень: {"role": "promo", "component": {...linearContainer}}')]
    lc = content.get("component")
    if not isinstance(lc, dict) or lc.get("role") != "linearContainer":
        return out + [err("CONTENT_SCHEMA_INVALID", "content.component", "component должен быть linearContainer")]
    if lc.get("axis") != "v":
        out.append(err("CONTENT_AXIS_INVALID", "content.component.axis", 'axis должен быть "v"'))
    st = lc.get("style")
    if st is not None and (not isinstance(st, dict) or ("backgroundColor" in st and not _color(st["backgroundColor"]))):
        out.append(err("COLOR_INVALID", "content.component.style", "style = {backgroundColor: #RRGGBBAA}"))
    comps = lc.get("components")
    if not isinstance(comps, list) or not 1 <= len(comps) <= 6:
        out.append(err("CONTENT_COMPONENTS_COUNT", "content.component.components", f"нужно 1–6 компонентов, сейчас {len(comps) if isinstance(comps, list) else 0}"))
        comps = comps if isinstance(comps, list) else []
    for i, c in enumerate(comps):
        p = f"content.component.components[{i}]"
        if not isinstance(c, dict):
            out.append(err("CONTENT_SCHEMA_INVALID", p, "компонент должен быть объектом"))
            continue
        role = c.get("role")
        if role == "text":
            if c.get("format") not in ("none", "html"):
                out.append(err("CONTENT_TEXT_FORMAT_REQUIRED", f"{p}.format", 'у text обязателен format: "none" или "html"'))
            if not isinstance(c.get("text"), str):
                out.append(err("CONTENT_SCHEMA_INVALID", f"{p}.text", "у text нужен строковый text"))
        elif role == "image":
            if not _https(c.get("url")):
                out.append(err("CONTENT_IMAGE_URL_REQUIRED", f"{p}.url", "у image обязателен url https://..."))
            if "aspectRatio" in c and not isinstance(c["aspectRatio"], (int, float)):
                out.append(err("CONTENT_SCHEMA_INVALID", f"{p}.aspectRatio", "aspectRatio — число"))
        elif role == "button":
            if not isinstance(c.get("text"), str):
                out.append(err("CONTENT_SCHEMA_INVALID", f"{p}.text", "у кнопки нужен text"))
            out += validate_action(c, p)
        else:
            out.append(err("CONTENT_ROLE_INVALID", f"{p}.role", f"role={role!r}; допустимо text, image, button"))
    return out


def validate_header(c: dict, dicts: dict, refs_ok=lambda v: False) -> list[dict]:
    """Проверка шапки до POST/PUT: enum и id только из словарей, даты и время."""
    out: list[dict] = []
    name = (c.get("name") or "").strip()
    if not name:
        out.append(err("NAME_REQUIRED", "name", "Название кампании обязательно"))
    elif len(name) > 100:
        out.append(err("NAME_TOO_LONG", "name", f"{len(name)} символов, лимит 100"))
    if c.get("marketingName") and len(c["marketingName"]) > 100:
        out.append(err("MARKETING_NAME_TOO_LONG", "marketingName", "лимит 100 символов"))
    start = None
    try:
        start = datetime.strptime(f"{c.get('startDate')} {c.get('startTime')}", "%Y-%m-%d %H:%M")
    except (TypeError, ValueError):
        if not c.get("startDate"):
            out.append(err("START_DATE_REQUIRED", "startDate", "Нужна дата начала YYYY-MM-DD"))
        if not c.get("startTime") or not TIME.match(str(c.get("startTime"))):
            out.append(err("TIME_FORMAT_INVALID", "startTime", "Нужно время начала HH:mm"))
        if c.get("startDate"):
            out.append(err("DATE_FORMAT_INVALID", "startDate", "Дата в формате YYYY-MM-DD"))
    if c.get("endTime") and not c.get("endDate"):
        out.append(err("END_TIME_WITHOUT_END_DATE", "endTime", "Время окончания без даты окончания"))
    if c.get("endDate"):
        try:
            end = datetime.strptime(f"{c['endDate']} {c.get('endTime') or '23:59'}", "%Y-%m-%d %H:%M")
            if start and end <= start:
                out.append(err("DATE_RANGE_INVALID", "endDate", "Окончание должно быть позже начала"))
        except ValueError:
            out.append(err("DATE_FORMAT_INVALID", "endDate", "Дата/время окончания: YYYY-MM-DD и HH:mm"))
    topics = {t["value"] for t in dicts.get("topics", [])}
    if not c.get("topic"):
        out.append(err("TOPIC_REQUIRED", "topic", "Нужна тематика из справочника topics"))
    elif c["topic"] not in topics:
        out.append(err("TOPIC_INVALID", "topic", f"{c['topic']!r} нет в справочнике; допустимо: {', '.join(sorted(topics))}"))
    if c.get("audienceType") not in ("ALL_USERS", "SEGMENTED"):
        out.append(err("AUDIENCE_TYPE_INVALID", "audienceType", "ALL_USERS или SEGMENTED"))
    tag_ids = {t["id"] for t in dicts.get("tags", [])}
    for t in c.get("tags") or []:
        if t not in tag_ids and not refs_ok(t):
            out.append(err("ENTITY_NOT_FOUND", "tags", f"тега {t} нет в справочнике — выберите существующий или предложите create_tag"))
    place_ids = {p["id"] for p in dicts.get("places", [])}
    for p in c.get("places") or []:
        if p not in place_ids and not refs_ok(p):
            out.append(err("ENTITY_NOT_FOUND", "places", f"места {p} нет в справочнике"))
    for k, lo, hi in (("weight", 0, None), ("initialCtr", 0, 100)):
        v = c.get(k)
        if v is not None and (not isinstance(v, (int, float)) or v < lo or (hi is not None and v > hi)):
            out.append(err("WEIGHT_INVALID" if k == "weight" else "INITIAL_CTR_INVALID", k, f"{k}={v!r} вне допустимого диапазона"))
    return out


def validate_segments(audience: str | None, included: list, excluded: list, dicts: dict) -> list[dict]:
    if audience == "ALL_USERS" and (included or excluded):
        return [err("SEGMENTS_FORBIDDEN_FOR_ALL_USERS", "segments", "для ALL_USERS сегменты не задаются — смените тип аудитории на SEGMENTED")]
    seg = {s["code"]: s for s in dicts.get("segments", [])}
    out = []
    for field, codes in (("included", included), ("excluded", excluded)):
        for code in codes:
            s = seg.get(code)
            if s is None:
                out.append(err("SEGMENT_NOT_FOUND", f"segments.{field}", f"сегмента {code} нет в справочнике"))
            elif s["state"] != "ACTIVE":
                out.append(err("SEGMENT_NOT_ACTIVE", f"segments.{field}", f"{code} в состоянии {s['state']}, клиентов {s['count']} — выбрать нельзя"))
    for code in set(included) & set(excluded):
        out.append(err("SEGMENT_DUPLICATE", "segments", f"{code} одновременно во включении и исключении"))
    return out
