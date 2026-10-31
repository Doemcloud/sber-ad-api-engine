package httpapi

import (
	"encoding/json"
	"net/http"
	"net/http/httptest"
	"path/filepath"
	"strings"
	"testing"
	"time"

	"adcamp/internal/auth"
	"adcamp/internal/domain"
	"adcamp/internal/service"
	"adcamp/internal/store"
)

const mockDir = "../../../data/mock"

func newAPI(t *testing.T) http.Handler {
	t.Helper()
	if err := domain.LoadCatalog(filepath.Join(mockDir, "validation_rules.json")); err != nil {
		t.Fatal(err)
	}
	st, err := store.Open(mockDir, "")
	if err != nil {
		t.Fatal(err)
	}
	au, err := auth.Load(filepath.Join(mockDir, "users.json"), "test-secret", time.Hour)
	if err != nil {
		t.Fatal(err)
	}
	return (&API{S: service.New(st), Auth: au, Required: true, ServiceKey: "svc"}).Routes()
}

func call(h http.Handler, method, path, body string, hdr map[string]string) (int, map[string]any) {
	r := httptest.NewRequest(method, path, strings.NewReader(body))
	r.Header.Set("Content-Type", "application/json")
	for k, v := range hdr {
		r.Header.Set(k, v)
	}
	w := httptest.NewRecorder()
	h.ServeHTTP(w, r)
	var out map[string]any
	_ = json.Unmarshal(w.Body.Bytes(), &out)
	return w.Code, out
}

func login(t *testing.T, h http.Handler, l, p string) string {
	code, out := call(h, "POST", "/auth/login", `{"login":"`+l+`","password":"`+p+`"}`, nil)
	if code != 200 {
		t.Fatalf("вход %s: %d %v", l, code, out)
	}
	return out["token"].(string)
}

func TestLoginAndRoles(t *testing.T) {
	h := newAPI(t)
	if code, _ := call(h, "POST", "/auth/login", `{"login":"client","password":"wrong"}`, nil); code != 401 {
		t.Fatalf("неверный пароль: ждали 401, получили %d", code)
	}
	client := login(t, h, "client", "client")
	moder := login(t, h, "moder", "moder")

	_, me := call(h, "GET", "/auth/me", "", map[string]string{"Authorization": "Bearer " + moder})
	if u := me["user"].(map[string]any); u["role"] != "campaignModerator" || u["passwordSha256"] != nil {
		t.Fatalf("me: %v", me)
	}
	// без входа писать нельзя, читать можно
	if code, _ := call(h, "POST", "/campaigns/103/approve", "", map[string]string{"X-User": "petrova.m", "X-Role": "campaignModerator"}); code != 401 {
		t.Fatalf("запись без входа: ждали 401, получили %d", code)
	}
	if code, _ := call(h, "GET", "/campaigns", "", nil); code != 200 {
		t.Fatalf("чтение без входа: %d", code)
	}
	// менеджер с токеном не станет модератором, подставив X-Role
	code, out := call(h, "POST", "/campaigns/103/decline", `{"comment":"x"}`, map[string]string{"Authorization": "Bearer " + client, "X-Role": "campaignModerator"})
	if code != 400 || !strings.Contains(strings.ToUpper(jsonStr(out)), "ROLE_FORBIDDEN") {
		t.Fatalf("подмена роли: ждали ROLE_FORBIDDEN, получили %d %v", code, out)
	}
	// модератор возвращает на доработку
	code, out = call(h, "POST", "/campaigns/103/decline", `{"comment":"Добавьте теги"}`, map[string]string{"Authorization": "Bearer " + moder})
	if code != 200 || out["state"] != "NEEDS_WORK" {
		t.Fatalf("decline: %d %v", code, out)
	}
	// испорченный токен
	if code, _ := call(h, "GET", "/campaigns", "", map[string]string{"Authorization": "Bearer " + client + "x"}); code != 401 {
		t.Fatalf("испорченный токен: %d", code)
	}
	// сервис-агент с ключом действует от имени пользователя
	if code, out := call(h, "POST", "/campaigns/104/to-moderation", "", map[string]string{"X-Service-Key": "svc", "X-User": "ivanov.p", "X-Role": "campaignManager"}); code == 401 {
		t.Fatalf("сервисный ключ не принят: %v", out)
	}
}

func jsonStr(v any) string { b, _ := json.Marshal(v); return string(b) }
