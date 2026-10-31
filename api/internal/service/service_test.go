package service

import (
	"encoding/json"
	"os"
	"path/filepath"
	"slices"
	"strings"
	"testing"
	"time"

	"adcamp/internal/domain"
	"adcamp/internal/store"
)

const mockDir = "../../../data/mock"

var (
	manager   = Actor{User: "ivanov.p", Role: domain.RoleManager}
	moderator = Actor{User: "petrova.m", Role: domain.RoleModerator}
)

func newSvc(t *testing.T) *Service {
	t.Helper()
	if err := domain.LoadCatalog(filepath.Join(mockDir, "validation_rules.json")); err != nil {
		t.Fatal(err)
	}
	st, err := store.Open(mockDir, "")
	if err != nil {
		t.Fatal(err)
	}
	return New(st)
}

func obj(t *testing.T, s string) map[string]any {
	t.Helper()
	var m map[string]any
	if err := json.Unmarshal([]byte(s), &m); err != nil {
		t.Fatal(err)
	}
	return m
}

func codes(e *domain.APIError) []string {
	if e == nil {
		return nil
	}
	var out []string
	for _, x := range e.Errors {
		out = append(out, x.Code)
	}
	return out
}

func wantCode(t *testing.T, e *domain.APIError, code string) {
	t.Helper()
	if e == nil || !slices.Contains(codes(e), code) {
		t.Fatalf("ожидали %s, получили %v", code, codes(e))
	}
}

func must(t *testing.T, e *domain.APIError) {
	t.Helper()
	if e != nil {
		t.Fatalf("неожиданная ошибка: %v", e.Errors)
	}
}

// Моки заказчика: warnings совпадают с campaign_warnings.json, ошибок нет.
func TestSeedMatchesMockWarnings(t *testing.T) {
	s := newSvc(t)
	raw, _ := os.ReadFile(filepath.Join(mockDir, "campaign_warnings.json"))
	var want []struct {
		CampaignID int64    `json:"campaignId"`
		Warnings   []string `json:"warnings"`
	}
	_ = json.Unmarshal(raw, &want)
	for _, w := range want {
		got, e := s.Warnings(w.CampaignID)
		must(t, e)
		slices.Sort(got.Warnings)
		slices.Sort(w.Warnings)
		if !slices.Equal(got.Warnings, w.Warnings) {
			t.Errorf("кампания %d: warnings %v, ожидали %v", w.CampaignID, got.Warnings, w.Warnings)
		}
	}
	for _, c := range s.List() {
		v, _ := s.Warnings(c.ID)
		if len(v.Errors) > 0 {
			t.Errorf("кампания %d из моков не проходит валидацию: %v", c.ID, v.Errors)
		}
	}
}

// Демо-сценарий task.md §9: бриф → кампания → креативы → модерация → одобрение → активация.
func TestDemoScenario(t *testing.T) {
	s := newSvc(t)
	det, e := s.Create(manager, obj(t, `{"name":"Вклад 16%: до конца года","startDate":"2026-11-05","startTime":"00:00",
		"endDate":"2026-12-31","endTime":"23:59","topic":{"value":"SALES","label":"Продажи"},
		"tags":[{"value":5,"label":"Вклад"}],"audienceType":"SEGMENTED","places":[{"value":1,"label":"mainScreenStories"}]}`))
	must(t, e)
	id := det.ID
	if det.State != domain.StateDraft || det.Published || det.InitialCtr != 15 || det.Weight != 0 {
		t.Fatalf("неверные дефолты: %+v", det.Campaign)
	}
	_, e = s.ToModeration(manager, id)
	wantCode(t, e, "SEGMENTS_REQUIRED") // SEGMENTED без сегментов не уходит на модерацию

	_, e = s.PutSegments(manager, id, obj(t, `{"included":["AGE_26_45","CITY_MSK","CITY_SPB"],"excluded":["EXC_UNSUBSCRIBED"]}`))
	must(t, e)
	b, e := s.SaveBanner(manager, id, 0, obj(t, `{"name":"Сторис вклад","bannerTypeId":1,
		"content":{"title":"Вклад под 16%","text":"До конца года","actionType":"default","buttonName":"Подробнее"}}`))
	must(t, e)
	c, e := s.SaveContent(manager, id, 0, obj(t, `{"name":"Промо вклад","contentType":"PROMO","content":{"role":"promo",
		"component":{"role":"linearContainer","axis":"v","components":[{"role":"text","format":"none","text":"Ставка 16%"},
		{"role":"button","text":"Открыть вклад","actionType":"externalLink","link":{"iOS":"mobilebank://deposit","android":"mobilebank://deposit"}}]}}}`))
	must(t, e)
	_, e = s.SaveCreative(manager, id, 0, map[string]any{"name": "Android", "bannerId": float64(b.ID), "contentId": float64(c.ID), "channelCode": "ANDROID"})
	must(t, e)

	v, _ := s.Warnings(id)
	if len(v.Errors) != 0 || len(v.Warnings) != 0 {
		t.Fatalf("ожидали чистую кампанию, получили %+v", v)
	}
	got, e := s.ToModeration(manager, id)
	must(t, e)
	if got.State != domain.StateOnModeration {
		t.Fatal(got.State)
	}
	_, e = s.Activate(manager, id)
	wantCode(t, e, "ACTIVATE_NOT_ALLOWED")
	_, e = s.Approve(moderator, id)
	must(t, e)
	got, e = s.Activate(manager, id)
	must(t, e)
	if got.State != domain.StateActive || !got.Published {
		t.Fatalf("после activate: %s published=%v", got.State, got.Published)
	}
	log, _ := s.Audit(id)
	var actions []string
	for _, a := range log {
		actions = append(actions, a.Entity+":"+a.Action)
	}
	for _, want := range []string{"CAMPAIGN:CREATE", "SEGMENTS:UPDATE", "BANNER:CREATE", "CONTENT:CREATE", "CREATIVE:CREATE", "CAMPAIGN:TO_MODERATION", "CAMPAIGN:APPROVE", "CAMPAIGN:ACTIVATE"} {
		if !slices.Contains(actions, want) {
			t.Errorf("в аудите нет %s: %v", want, actions)
		}
	}
}

func TestRoleCheckedBeforeState(t *testing.T) {
	s := newSvc(t)
	_, e := s.Approve(manager, 101) // и роль, и состояние неверные
	wantCode(t, e, "ROLE_FORBIDDEN")
	_, e = s.Approve(moderator, 101)
	wantCode(t, e, "APPROVE_NOT_ALLOWED")
}

func TestDeclineCycle104(t *testing.T) {
	s := newSvc(t)
	log, _ := s.Audit(104)
	if last := log[len(log)-1]; last.Action != "DECLINE" || last.Comment == nil {
		t.Fatalf("у 104 нет комментария модератора: %+v", last)
	}
	// NEEDS_WORK редактируется без смены статуса
	det, _ := s.Get(104)
	body := obj(t, `{"name":"Ипотека: ставка 4,9%","startDate":"2026-11-01","startTime":"00:00","endDate":"2026-12-15","endTime":"23:59",
		"topic":"SALES","tags":[1],"audienceType":"SEGMENTED","places":[1]}`)
	upd, e := s.Update(manager, 104, body)
	must(t, e)
	if upd.State != domain.StateNeedsWork || len(upd.Places) != 1 || det.State != domain.StateNeedsWork {
		t.Fatalf("state=%s places=%v", upd.State, upd.Places)
	}
	b, e := s.SaveBanner(manager, 104, 0, obj(t, `{"name":"Ипотека сторис","bannerTypeId":1,"content":{"title":"Ипотека 4,9%","actionType":"default"}}`))
	must(t, e)
	_, e = s.SaveCreative(manager, 104, 0, map[string]any{"name": "iOS", "bannerId": float64(b.ID), "channelCode": "iOS"})
	must(t, e)
	v, _ := s.Warnings(104)
	if len(v.Warnings) != 0 {
		t.Fatalf("warnings не устранены: %v", v.Warnings)
	}
	_, e = s.ToModeration(manager, 104)
	must(t, e)
	_, e = s.Decline(moderator, 104, "")
	wantCode(t, e, "DECLINE_COMMENT_REQUIRED")
}

func TestBannerValidation(t *testing.T) {
	s := newSvc(t)
	long := strings.Repeat("я", 101)
	_, e := s.SaveBanner(manager, 101, 0, map[string]any{"name": "x", "bannerTypeId": float64(1),
		"content": map[string]any{"title": long, "actionType": "default"}})
	wantCode(t, e, "BANNER_TITLE_TOO_LONG")
	_, e = s.SaveBanner(manager, 101, 0, obj(t, `{"name":"x","bannerTypeId":2,"content":{"actionType":"externalLink"}}`))
	wantCode(t, e, "LINK_REQUIRED")
	_, e = s.SaveBanner(manager, 101, 0, obj(t, `{"name":"x","bannerTypeId":2,"content":{"actionType":"closeCampaign","link":{"web":"https://a"}}}`))
	wantCode(t, e, "LINK_FORBIDDEN")
	_, e = s.SaveBanner(manager, 101, 0, obj(t, `{"name":"x","bannerTypeId":2,"content":{"actionType":"default","titleStyle":{"fontSize":50,"textColor":"red"}}}`))
	wantCode(t, e, "STYLE_INVALID")
	wantCode(t, e, "COLOR_INVALID")
	_, e = s.SaveBanner(manager, 101, 0, obj(t, `{"name":"x","bannerTypeId":9,"content":{"actionType":"default"}}`))
	if e == nil || e.Status != 404 {
		t.Fatalf("неизвестный тип баннера должен давать 404: %v", e)
	}
}

func TestStoryNotInWeb(t *testing.T) {
	s := newSvc(t)
	// баннер 211 — STORY в кампании 111
	_, e := s.SaveCreative(manager, 111, 0, map[string]any{"name": "web", "bannerId": float64(211), "channelCode": "WEB"})
	wantCode(t, e, "CREATIVE_CHANNEL_NOT_ALLOWED")
	_, e = s.SaveCreative(manager, 111, 0, map[string]any{"name": "dup", "bannerId": float64(211), "channelCode": "iOS"})
	wantCode(t, e, "CREATIVE_DUPLICATE")
	_, e = s.SaveCreative(manager, 111, 0, map[string]any{"name": "ios", "bannerId": float64(211), "channelCode": "IOS"})
	if e == nil || e.Status != 404 {
		t.Fatalf("регистр кода канала должен проверяться: %v", e)
	}
}

func TestAudienceInvariant(t *testing.T) {
	s := newSvc(t)
	_, e := s.PutSegments(manager, 108, obj(t, `{"included":["CITY_MSK"],"excluded":[]}`)) // 108 — ALL_USERS
	wantCode(t, e, "SEGMENTS_FORBIDDEN_FOR_ALL_USERS")
	_, e = s.PutSegments(manager, 101, obj(t, `{"included":["SEG_DRAFT_WINTER"],"excluded":[]}`))
	wantCode(t, e, "SEGMENT_NOT_ACTIVE")
	det, _ := s.Get(101) // у 101 есть сегменты → смена на ALL_USERS запрещена
	body := map[string]any{"name": det.Name, "startDate": det.StartDate, "startTime": det.StartTime, "topic": det.Topic, "audienceType": "ALL_USERS", "places": []any{float64(2)}}
	_, e = s.Update(manager, 101, body)
	wantCode(t, e, "SEGMENTS_FORBIDDEN_FOR_ALL_USERS")
}

func TestEditTransitions(t *testing.T) {
	s := newSvc(t)
	// 107 APPROVED → правка снимает одобрение
	_, e := s.SaveBanner(manager, 107, 207, obj(t, `{"name":"Новое имя","bannerTypeId":2,"content":{"actionType":"default"}}`))
	must(t, e)
	if d, _ := s.Get(107); d.State != domain.StateDraft {
		t.Fatalf("APPROVED после правки: %s", d.State)
	}
	// 102 ACTIVE → ACTIVE_EDITING, показ не прерывается
	_, e = s.SaveBanner(manager, 102, 202, obj(t, `{"name":"Сторис v2","bannerTypeId":1,"content":{"actionType":"default"}}`))
	must(t, e)
	if d, _ := s.Get(102); d.State != domain.StateActiveEditing || !d.Published {
		t.Fatalf("ACTIVE после правки: %s published=%v", d.State, d.Published)
	}
	// 103 ON_MODERATION и 114 STOPPED не редактируются
	_, e = s.SaveBanner(manager, 103, 203, obj(t, `{"name":"x","bannerTypeId":2,"content":{"actionType":"default"}}`))
	wantCode(t, e, "UPDATE_NOT_ALLOWED")
	_, e = s.Stop(manager, 114)
	wantCode(t, e, "STOP_NOT_ALLOWED")
	// удалять опубликованное нельзя
	wantCode(t, s.Delete(manager, 102), "DELETE_NOT_ALLOWED")
	must(t, s.Delete(manager, 108))
}

func TestNameDuplicateIgnoresSelf(t *testing.T) {
	s := newSvc(t)
	_, e := s.Create(manager, obj(t, `{"name":"Премиальная карта: осенняя акция","startDate":"2026-11-05","startTime":"10:00","topic":"SALES","audienceType":"ALL_USERS"}`))
	wantCode(t, e, "NAME_DUPLICATE")
	det, _ := s.Get(108)
	_, e = s.Update(manager, 108, map[string]any{"name": det.Name, "startDate": det.StartDate, "startTime": "08:00", "topic": det.Topic, "audienceType": "ALL_USERS", "places": []any{float64(2)}, "tags": []any{float64(6)}})
	must(t, e)
	_, e = s.Create(manager, obj(t, `{"name":"Даты","startDate":"2026-11-05","startTime":"10:00","endDate":"2026-11-05","endTime":"09:00","topic":"SALES","audienceType":"ALL_USERS"}`))
	wantCode(t, e, "DATE_RANGE_INVALID")
}

// Остановленную кампанию можно возобновить только через модератора.
func TestResumeStoppedCampaign(t *testing.T) {
	s := newSvc(t)
	s.Now = func() time.Time { return time.Date(2026, 10, 31, 12, 0, 0, 0, time.UTC) }
	mgr := Actor{User: "ivanov.p", Role: "campaignManager"}
	mod := Actor{User: "petrova.m", Role: "campaignModerator"}

	if _, e := s.Stop(mgr, 102); e != nil {
		t.Fatal(e)
	}
	if _, e := s.Activate(mgr, 102); e == nil {
		t.Fatal("остановленную кампанию нельзя запустить без модератора")
	}
	if _, e := s.Resume(mod, 102, ""); e == nil || e.Errors[0].Code != "ROLE_FORBIDDEN" {
		t.Fatalf("запрос возобновления — только менеджер: %v", e)
	}
	c, e := s.Resume(mgr, 102, "Продлеваем акцию до конца ноября")
	if e != nil || c.State != "ON_MODERATION" || c.Published {
		t.Fatalf("resume: %+v %v", c, e)
	}
	if _, e := s.Resume(mgr, 102, ""); e == nil || e.Errors[0].Code != "RESUME_NOT_ALLOWED" {
		t.Fatalf("повторный запрос: %v", e)
	}
	if c, e = s.Approve(mod, 102); e != nil || c.State != "APPROVED" {
		t.Fatalf("approve: %v", e)
	}
	if c, e = s.Activate(mgr, 102); e != nil || c.State != "ACTIVE" || !c.Published {
		t.Fatalf("activate: %+v %v", c, e)
	}
	log, _ := s.Audit(102)
	var actions []string
	for _, x := range log {
		actions = append(actions, x.Action)
	}
	if got := strings.Join(actions[len(actions)-4:], ","); got != "STOP,RESUME_REQUEST,APPROVE,ACTIVATE" {
		t.Fatalf("аудит: %s", got)
	}

	// закончившийся период — возобновлять нечего
	s.Now = func() time.Time { return time.Date(2027, 1, 10, 0, 0, 0, 0, time.UTC) }
	_, _ = s.Stop(mgr, 102)
	if _, e := s.Resume(mgr, 102, ""); e == nil || e.Errors[0].Code != "RESUME_PERIOD_ENDED" {
		t.Fatalf("период закончился: %v", e)
	}
}
