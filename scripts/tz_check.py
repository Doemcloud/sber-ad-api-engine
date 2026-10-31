"""Сверка API с ТЗ (task.md §2–§5, mock-data.md §9) на живом сервере: 116 проверок.
Запуск на чистых данных (API с AUTH_REQUIRED=0, заголовки X-User/X-Role — как в ТЗ §3):
    python scripts/tz_check.py http://localhost:8080
"""
import json
import sys
from pathlib import Path
import urllib.error
import urllib.request

BASE = sys.argv[1]
MGR = {"X-User": "ivanov.p", "X-Role": "campaignManager"}
MOD = {"X-User": "petrova.m", "X-Role": "campaignModerator"}
fails, oks = [], 0


def req(method, path, body=None, h=MGR):
    data = json.dumps(body).encode() if body is not None else None
    r = urllib.request.Request(BASE + path, data=data, method=method, headers={"Content-Type": "application/json", **h})
    try:
        with urllib.request.urlopen(r) as resp:
            raw = resp.read()
            return resp.status, (json.loads(raw) if raw else None), dict(resp.headers)
    except urllib.error.HTTPError as e:
        raw = e.read()
        try:
            return e.code, json.loads(raw), dict(e.headers)
        except Exception:
            return e.code, raw.decode(errors="replace"), dict(e.headers)


def check(name, cond, info=""):
    global oks
    if cond:
        oks += 1
    else:
        fails.append(f"{name}: {info}")


def codes(b):
    return {e.get("code") for e in (b or {}).get("errors", [])} if isinstance(b, dict) else set()


def expect_err(name, method, path, body, code, status=400, h=MGR):
    s, b, _ = req(method, path, body, h)
    check(name, s == status and code in codes(b), f"ждали {status} {code}, получили {s} {b}")


# ---------- §2.9 справочники
for path, n in [("/topics", 11), ("/tags", 6), ("/channels", 3), ("/banner-types", 2), ("/segment-types", 8), ("/segments", 40), ("/places", 8)]:
    s, b, _ = req("GET", path)
    check(f"справочник {path}", s == 200 and isinstance(b, list) and len(b) == n, f"{s} len={len(b) if isinstance(b, list) else b}")
s, places, _ = req("GET", "/places")
check("2 неактивных места", sum(p.get("state") == "INACTIVE" for p in places) == 2)
s, ch, _ = req("GET", "/channels")
check("коды каналов", sorted(c.get("code") for c in ch) == sorted(["iOS", "ANDROID", "WEB"]), ch)
s, bt, _ = req("GET", "/banner-types")
st = next(x for x in bt if x["code"] == "STORY")
check("STORY лимиты/каналы", st.get("titleMaxLength") == 100 and st.get("textMaxLength") == 500 and sorted(st.get("channels", st.get("channelCodes", []))) == ["ANDROID", "iOS"], st)

# ---------- §3 список и карточка
s, lst, hdr = req("GET", "/campaigns")
check("GET /campaigns 14", s == 200 and len(lst) == 14, len(lst))
allowed = {"id", "name", "state", "published", "topic", "startDate", "startTime", "endDate", "endTime"}
check("CampaignListItemDto лёгкий", all(set(x) <= allowed for x in lst), set().union(*map(set, lst)) - allowed)
check("эхо X-User/X-Role", hdr.get("X-User") == "ivanov.p" and hdr.get("X-Role") == "campaignManager", hdr)
s, d, _ = req("GET", "/campaigns/101")
check("101 topic string", isinstance(d.get("topic"), str), d.get("topic"))
check("101 tags/places [id]", all(isinstance(v, int) for v in d.get("tags", []) + d.get("places", [])), (d.get("tags"), d.get("places")))
check("101 вложенные коллекции", all(k in d for k in ("banners", "contents", "creatives", "segments")) and set(d["segments"]) >= {"included", "excluded"}, list(d))
check("101 weight/initialCtr", "weight" in d and "initialCtr" in d, list(d))
expect_err("404 кампания", "GET", "/campaigns/99999", None, "ENTITY_NOT_FOUND", 404)

# ---------- §2.2 создание: тела с {value,label} (campaign_create_payloads.json)
payloads = json.load(open(Path(__file__).resolve().parent.parent / "data" / "mock" / "campaign_create_payloads.json", encoding="utf-8"))
items = payloads if isinstance(payloads, list) else payloads.get("payloads") or list(payloads.values())
p0 = None
for it in items:
    body = it.get("body") or it.get("payload") or it
    if isinstance(body, dict) and "name" in body:
        p0 = json.loads(json.dumps(body))
        break
check("есть образец тела создания", p0 is not None, str(payloads)[:200])
p0["name"] = "ТЗ-проверка: создание по образцу"
s, c, _ = req("POST", "/campaigns", p0)
check("POST тело {value,label} (образец заказчика)", s in (200, 201) and c.get("state") == "DRAFT" and c.get("published") is False, f"{s} {c}")
cid = c.get("id") if isinstance(c, dict) else None
if cid:
    s, d, _ = req("GET", f"/campaigns/{cid}")
    check("GET после {value,label}: сырые значения", isinstance(d.get("topic"), str) and all(isinstance(x, int) for x in d.get("places", [])), d)
    check("author проставлен по X-User", d.get("author") == "ivanov.p", d.get("author"))

base = {"name": "ТЗ-проверка минимальная", "startDate": "2026-11-10", "startTime": "10:00", "topic": "SALES", "audienceType": "ALL_USERS", "places": [2]}
s, c2, _ = req("POST", "/campaigns", base)
check("POST минимальное (сырые значения)", s in (200, 201), f"{s} {c2}")
m = c2.get("id")
s, d, _ = req("GET", f"/campaigns/{m}")
check("дефолты weight=0 initialCtr=15", d.get("weight") == 0 and d.get("initialCtr") == 15, (d.get("weight"), d.get("initialCtr")))

# валидации шапки (§4)
def hdr_err(name, patch, code, status=400):
    expect_err(name, "POST", "/campaigns", {**base, "name": f"ТЗ {name}", **patch}, code, status)
hdr_err("пустое имя", {"name": ""}, "NAME_REQUIRED")
hdr_err("имя >100", {"name": "я" * 101}, "NAME_TOO_LONG")
expect_err("дубликат имени", "POST", "/campaigns", {**base}, "NAME_DUPLICATE")
hdr_err("marketingName >100", {"marketingName": "я" * 101}, "MARKETING_NAME_TOO_LONG")
hdr_err("end <= start", {"endDate": "2026-11-10", "endTime": "09:00"}, "DATE_RANGE_INVALID")
hdr_err("startTime формат", {"startTime": "9:00"}, "TIME_FORMAT_INVALID")
hdr_err("endTime формат", {"endDate": "2026-12-10", "endTime": "25:00"}, "TIME_FORMAT_INVALID")
hdr_err("topic неверный", {"topic": "NOPE"}, "TOPIC_INVALID")
hdr_err("topic обязателен", {"topic": None}, "TOPIC_REQUIRED")
hdr_err("keywords >512", {"keywords": "a" * 513}, "KEYWORDS_TOO_LONG")
hdr_err("audienceType обязателен", {"audienceType": None}, "AUDIENCE_TYPE_REQUIRED")
hdr_err("place 404", {"places": [999]}, "ENTITY_NOT_FOUND", 404)
hdr_err("tag 404", {"tags": [999]}, "ENTITY_NOT_FOUND", 404)
hdr_err("weight < 0", {"weight": -1}, "WEIGHT_INVALID")
s, b, _ = req("PUT", f"/campaigns/{m}", {**base})
check("NAME_DUPLICATE не срабатывает на своё имя", s == 200, f"{s} {b}")
# PUT — полная замена
req("PUT", f"/campaigns/{m}", {**base, "marketingName": "Временно"})
req("PUT", f"/campaigns/{m}", {**base})
s, d, _ = req("GET", f"/campaigns/{m}")
check("PUT = полная замена (marketingName исчез)", not d.get("marketingName"), d.get("marketingName"))

# ---------- §2.4 аудитория
expect_err("ALL_USERS + сегменты", "PUT", f"/campaigns/{m}/segments", {"included": ["CITY_MSK"], "excluded": []}, "SEGMENTS_FORBIDDEN_FOR_ALL_USERS")
s, seg, _ = req("POST", "/campaigns", {**base, "name": "ТЗ сегментная", "audienceType": "SEGMENTED"})
sg = seg["id"]
segs = req("GET", "/segments")[1]
new_seg = next(x["code"] for x in segs if x.get("state") != "ACTIVE")
expect_err("сегмент NEW", "PUT", f"/campaigns/{sg}/segments", {"included": [new_seg], "excluded": []}, "SEGMENT_NOT_ACTIVE")
expect_err("сегмент несуществующий", "PUT", f"/campaigns/{sg}/segments", {"included": ["NOPE"], "excluded": []}, "SEGMENT_NOT_FOUND")
s, b, _ = req("PUT", f"/campaigns/{sg}/segments", {"included": ["CITY_MSK"], "excluded": ["EXC_UNSUBSCRIBED"]})
check("PUT segments ok", s in (200, 204), f"{s} {b}")
expect_err("смена на ALL_USERS при сегментах", "PUT", f"/campaigns/{sg}", {**base, "name": "ТЗ сегментная", "audienceType": "ALL_USERS"}, "SEGMENTS_FORBIDDEN_FOR_ALL_USERS")
s, w, _ = req("GET", f"/campaigns/{sg}/warnings")
req("PUT", f"/campaigns/{sg}/segments", {"included": [], "excluded": []})
s, w, _ = req("GET", f"/campaigns/{sg}/warnings")
check("SEGMENTED без включений — ошибка валидации", "SEGMENTS_REQUIRED" in {e.get("code") for e in w.get("errors", [])}, w)

# ---------- §2.6 баннеры (на черновике m: место 2 SMART_BANNER)
def banner(content, t=2, name="Б"):
    return {"name": name, "bannerTypeId": t, "content": content}
s, b, _ = req("POST", f"/campaigns/{m}/banners", banner({"actionType": "default"}))
check("минимальный баннер {actionType: default}", s in (200, 201), f"{s} {b}")
bid = b.get("id")
expect_err("bannerTypeId 404", "POST", f"/campaigns/{m}/banners", banner({"actionType": "default"}, t=99), "ENTITY_NOT_FOUND", 404)
expect_err("STORY title >100", "POST", f"/campaigns/{m}/banners", banner({"actionType": "default", "title": "я" * 101}, t=1), "BANNER_TITLE_TOO_LONG")
s, b2, _ = req("POST", f"/campaigns/{m}/banners", banner({"actionType": "default", "title": "я" * 101}, t=2, name="Б2"))
check("SMART title 101 можно (лимит 250)", s in (200, 201), f"{s} {b2}")
expect_err("SMART text >1000", "POST", f"/campaigns/{m}/banners", banner({"actionType": "default", "text": "я" * 1001}), "BANNER_TEXT_TOO_LONG")
expect_err("actionType обязателен", "POST", f"/campaigns/{m}/banners", banner({}), "BANNER_ACTION_TYPE_REQUIRED")
expect_err("actionType неверный", "POST", f"/campaigns/{m}/banners", banner({"actionType": "open"}), "ACTION_TYPE_INVALID")
expect_err("externalLink без link", "POST", f"/campaigns/{m}/banners", banner({"actionType": "externalLink"}), "LINK_REQUIRED")
expect_err("closeCampaign с link", "POST", f"/campaigns/{m}/banners", banner({"actionType": "closeCampaign", "link": {"web": "https://x.ru"}}), "LINK_FORBIDDEN")
s, b3, _ = req("POST", f"/campaigns/{m}/banners", banner({"actionType": "openSmartLink", "link": {"android": "mobilebank://x"}}, name="Б3"))
check("частичный link (только android)", s in (200, 201), f"{s} {b3}")
expect_err("fontSize 9", "POST", f"/campaigns/{m}/banners", banner({"actionType": "default", "titleStyle": {"fontSize": 9}}), "STYLE_INVALID")
expect_err("fontSize 41", "POST", f"/campaigns/{m}/banners", banner({"actionType": "default", "textStyle": {"fontSize": 41}}), "STYLE_INVALID")
s, b4, _ = req("POST", f"/campaigns/{m}/banners", banner({"actionType": "default", "titleStyle": {"fontSize": 40, "fontWeight": "semi-bold"}}, name="Б4"))
check("fontSize 40 + semi-bold допустимы", s in (200, 201), f"{s} {b4}")
expect_err("fontWeight неверный", "POST", f"/campaigns/{m}/banners", banner({"actionType": "default", "titleStyle": {"fontWeight": "heavy"}}), "STYLE_INVALID")
expect_err("цвет #RGB", "POST", f"/campaigns/{m}/banners", banner({"actionType": "default", "background": {"color": "#FFF"}}), "COLOR_INVALID")
expect_err("image http", "POST", f"/campaigns/{m}/banners", banner({"actionType": "default", "image": {"url": "http://x.ru/a.png"}}), "IMAGE_URL_INVALID")
expect_err("voiceOver >200", "POST", f"/campaigns/{m}/banners", banner({"actionType": "default", "voiceOver": "я" * 201}), "VOICE_OVER_TOO_LONG")

# ---------- §2.7 контент
def promo(comps, axis="v"):
    return {"name": "П", "contentType": "PROMO", "content": {"role": "promo", "component": {"role": "linearContainer", "axis": axis, "components": comps}}}
T = {"role": "text", "format": "none", "text": "a"}
s, ct, _ = req("POST", f"/campaigns/{m}/contents", promo([T]))
check("PROMO 1 компонент", s in (200, 201), f"{s} {ct}")
ctid = ct.get("id")
expect_err("PROMO axis h", "POST", f"/campaigns/{m}/contents", promo([T], "h"), "CONTENT_AXIS_INVALID")
expect_err("PROMO 0 компонентов", "POST", f"/campaigns/{m}/contents", promo([]), "CONTENT_COMPONENTS_COUNT")
expect_err("PROMO 7 компонентов", "POST", f"/campaigns/{m}/contents", promo([T] * 7), "CONTENT_COMPONENTS_COUNT")
expect_err("text без format", "POST", f"/campaigns/{m}/contents", promo([{"role": "text", "text": "a"}]), "CONTENT_TEXT_FORMAT_REQUIRED")
expect_err("image без url", "POST", f"/campaigns/{m}/contents", promo([{"role": "image"}]), "CONTENT_IMAGE_URL_REQUIRED")
expect_err("роль video", "POST", f"/campaigns/{m}/contents", promo([{"role": "video"}]), "CONTENT_ROLE_INVALID")
expect_err("кнопка externalLink без link", "POST", f"/campaigns/{m}/contents", promo([{"role": "button", "text": "a", "actionType": "externalLink"}]), "LINK_REQUIRED")
bad = promo([T]); bad["contentType"] = "VIDEO"
expect_err("contentType не PROMO", "POST", f"/campaigns/{m}/contents", bad, "CONTENT_TYPE_INVALID")
bad = promo([T]); bad["content"] = {"role": "promo", "component": {"role": "promo", "component": {}}}
s, b, _ = req("POST", f"/campaigns/{m}/contents", bad)
check("вложенный promo — ошибка", s == 400, f"{s} {b}")

# ---------- §2.8 креативы
s, story_b, _ = req("POST", f"/campaigns/{m}/banners", banner({"actionType": "default"}, t=1, name="Сторис"))
expect_err("STORY в WEB", "POST", f"/campaigns/{m}/creatives", {"name": "К", "bannerId": story_b["id"], "channelCode": "WEB"}, "CREATIVE_CHANNEL_NOT_ALLOWED")
s, cr, _ = req("POST", f"/campaigns/{m}/creatives", {"name": "К", "bannerId": bid, "channelCode": "WEB"})
check("креатив без контента", s in (200, 201), f"{s} {cr}")
expect_err("дубликат креатива", "POST", f"/campaigns/{m}/creatives", {"name": "К2", "bannerId": bid, "channelCode": "WEB"}, "CREATIVE_DUPLICATE")
expect_err("канал web (регистр)", "POST", f"/campaigns/{m}/creatives", {"name": "К3", "bannerId": bid, "channelCode": "web"}, "ENTITY_NOT_FOUND", 404)
expect_err("bannerId 404", "POST", f"/campaigns/{m}/creatives", {"name": "К4", "bannerId": 99999, "channelCode": "iOS"}, "ENTITY_NOT_FOUND", 404)
expect_err("contentId 404", "POST", f"/campaigns/{m}/creatives", {"name": "К5", "bannerId": bid, "contentId": 99999, "channelCode": "iOS"}, "ENTITY_NOT_FOUND", 404)
s, x, _ = req("POST", f"/campaigns/{m}/creatives", {"name": "К6", "bannerId": bid, "contentId": ctid, "channelCode": "iOS"})
check("креатив с контентом", s in (200, 201), f"{s} {x}")

# ---------- справочники модуля (§10.4)
s, pl, _ = req("POST", "/places", {"code": "tzCheckPlace", "description": "Проверочное место"})
check("POST /places: ACTIVE, без defaultBanner", s in (200, 201) and pl.get("state") == "ACTIVE" and not pl.get("defaultBanner"), f"{s} {pl}")
expect_err("POST /places дубль кода", "POST", "/places", {"code": "tzCheckPlace", "description": "x"}, "PLACE_CODE_DUPLICATE")
expect_err("POST /places без code", "POST", "/places", {"description": "x"}, "PLACE_CODE_REQUIRED")
s, tg, _ = req("POST", "/tags", {"name": "ТЗ-тег"})
check("POST /tags", s in (200, 201) and tg.get("id"), f"{s} {tg}")
expect_err("POST /places модератором", "POST", "/places", {"code": "x2", "description": "x"}, "ROLE_FORBIDDEN", 400, MOD)

# место без defaultBanner не даёт PLACE_NO_CREATIVE
s, nc, _ = req("POST", "/campaigns", {**base, "name": "ТЗ новое место", "places": [pl["id"]], "tags": [tg["id"]]})
s, w, _ = req("GET", f"/campaigns/{nc['id']}/warnings")
check("место без defaultBanner покрыто", "PLACE_NO_CREATIVE" not in {x.get("code") for x in w.get("warnings", []) if isinstance(x, dict)} and not any("креатив" in str(x) for x in w.get("warnings", [])), w)

# ---------- §2.3 жизненный цикл
expect_err("роль раньше состояния", "POST", "/campaigns/101/approve", None, "ROLE_FORBIDDEN", 400, MGR)
expect_err("approve DRAFT", "POST", "/campaigns/101/approve", None, "APPROVE_NOT_ALLOWED", 400, MOD)
expect_err("decline DRAFT", "POST", "/campaigns/101/decline", {"comment": "x"}, "DECLINE_NOT_ALLOWED", 400, MOD)
expect_err("decline без комментария", "POST", "/campaigns/103/decline", {"comment": ""}, "DECLINE_COMMENT_REQUIRED", 400, MOD)
expect_err("to-moderation модератором", "POST", "/campaigns/101/to-moderation", None, "ROLE_FORBIDDEN", 400, MOD)
expect_err("правка ON_MODERATION", "PUT", "/campaigns/103", {**base, "name": "Сомелье: подбор вина"}, "UPDATE_NOT_ALLOWED")
expect_err("правка баннера в ON_MODERATION", "POST", "/campaigns/103/banners", banner({"actionType": "default"}), "UPDATE_NOT_ALLOWED")
expect_err("правка STOPPED", "PUT", "/campaigns/114/segments", {"included": [], "excluded": []}, "UPDATE_NOT_ALLOWED")
expect_err("activate не APPROVED", "POST", "/campaigns/101/activate", None, "ACTIVATE_NOT_ALLOWED")
expect_err("stop не published", "POST", "/campaigns/101/stop", None, "STOP_NOT_ALLOWED")
expect_err("delete ACTIVE_EDITING", "DELETE", "/campaigns/106", None, "DELETE_NOT_ALLOWED")
expect_err("to-moderation из APPROVED", "POST", "/campaigns/107/to-moderation", None, "TO_MODERATION_NOT_ALLOWED")
# APPROVED → DRAFT при правке; ACTIVE → ACTIVE_EDITING
d107 = req("GET", "/campaigns/107")[1]
hdr107 = {k: d107[k] for k in ("name", "marketingName", "startDate", "startTime", "endDate", "endTime", "topic", "tags", "keywords", "audienceType", "weight", "initialCtr", "places") if k in d107 and d107[k] is not None}
s, b, _ = req("PUT", "/campaigns/107", {**hdr107, "keywords": "страховка"})
check("правка APPROVED → DRAFT", s == 200 and req("GET", "/campaigns/107")[1]["state"] == "DRAFT", f"{s} {b}")
d102 = req("GET", "/campaigns/102")[1]
s, b, _ = req("PUT", f"/campaigns/102/banners/{d102['banners'][0]['id']}", {k: d102["banners"][0][k] for k in ("name", "bannerTypeId", "content")})
s2 = req("GET", "/campaigns/102")[1]
check("правка баннера ACTIVE → ACTIVE_EDITING, показ идёт", s2["state"] == "ACTIVE_EDITING" and s2["published"] is True, f"{s} {s2['state']} {s2['published']}")
# полный цикл на m: ошибки блокируют, warnings нет
s, b, _ = req("POST", f"/campaigns/{sg}/to-moderation")
check("to-moderation с ошибками блокируется", s == 400, f"{s} {b}")
s, b, _ = req("POST", f"/campaigns/{m}/to-moderation")
check("to-moderation", s == 200 and b.get("state") == "ON_MODERATION", f"{s} {b}")
s, b, _ = req("POST", f"/campaigns/{m}/decline", {"comment": "Добавьте теги"}, MOD)
check("decline → NEEDS_WORK", s == 200 and b.get("state") == "NEEDS_WORK", f"{s} {b}")
audit = req("GET", f"/campaigns/{m}/audit")[1]
dec = [a for a in audit if a.get("action") == "DECLINE"]
check("комментарий decline в аудите", dec and dec[-1].get("comment") == "Добавьте теги" and dec[-1].get("actor") == "petrova.m", dec)
check("формат записи аудита", all({"entity", "entityId", "action", "changes", "at", "actor", "comment"} <= set(a) for a in audit), audit[:1])
check("changes=null у CREATE и переходов", all(a["changes"] is None for a in audit if a["action"] in ("CREATE", "TO_MODERATION", "DECLINE")), [a for a in audit if a["action"] in ("CREATE", "TO_MODERATION", "DECLINE") and a["changes"] is not None][:2])
upd = [a for a in audit if a["action"] == "UPDATE" and a["entity"] == "CAMPAIGN"]
check("diff {from,to} у UPDATE", upd and all(isinstance(v, dict) and set(v) == {"from", "to"} for a in upd for v in (a["changes"] or {}).values()), upd[:1])
check("сущности аудита из enum ТЗ", {a["entity"] for a in audit} <= {"CAMPAIGN", "BANNER", "CONTENT", "CREATIVE", "SEGMENTS"}, {a["entity"] for a in audit})
req("POST", f"/campaigns/{m}/to-moderation")
s, b, _ = req("POST", f"/campaigns/{m}/approve", None, MOD)
check("approve", s == 200 and b.get("state") == "APPROVED", f"{s} {b}")
s, b, _ = req("POST", f"/campaigns/{m}/activate")
check("activate → ACTIVE, published, CBRO", s == 200 and b.get("state") == "ACTIVE" and b.get("published") is True, f"{s} {b}")
expect_err("delete published", "DELETE", f"/campaigns/{m}", None, "DELETE_NOT_ALLOWED")
s, b, _ = req("POST", f"/campaigns/{m}/stop")
check("stop → STOPPED, published=false", s == 200 and b.get("state") == "STOPPED" and b.get("published") is False, f"{s} {b}")
expect_err("правка после stop", "PUT", f"/campaigns/{m}", {**base}, "UPDATE_NOT_ALLOWED")
s, b, _ = req("DELETE", f"/campaigns/{sg}")
check("delete DRAFT", s in (200, 204), f"{s} {b}")
s, b, _ = req("POST", "/mock/cbro/export", {"campaignId": 102})
check("CBRO заглушка", s == 200 and b.get("status") == "OK", f"{s} {b}")
# 104: без баннеров дошла до модерации — нет баннеров не блокирует
w104 = req("GET", "/campaigns/104/warnings")[1]
check("104: ошибок нет, 3 warnings", not w104.get("errors") and len(w104.get("warnings", [])) == 3, w104)
print(f"OK {oks}, FAIL {len(fails)}")
for f in fails:
    print(" -", f[:400])
sys.exit(1 if fails else 0)
