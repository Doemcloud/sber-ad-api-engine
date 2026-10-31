// Package httpapi — HTTP-поверхность MVP (task.md §3): 7 справочников,
// POST /places и /tags, 22 операции с кампаниями и дочерними сущностями.
package httpapi

import (
	"encoding/json"
	"log"
	"net/http"
	"strconv"

	"crypto/subtle"
	"net"
	"strings"
	"sync"
	"time"

	"adcamp/internal/auth"
	"adcamp/internal/domain"
	"adcamp/internal/service"
)

// API — HTTP-слой. Auth/Required/ServiceKey — вход по логину и паролю:
//   - Authorization: Bearer <токен> → пользователь и роль берутся из токена (заголовкам браузера не верим);
//   - X-Service-Key — сервис-агент действует от имени уже проверенного пользователя (X-User/X-Role);
//   - Required=false — режим ТЗ: роль из X-Role без входа (тесты, curl).
type API struct {
	S          *service.Service
	Auth       *auth.Auth
	Required   bool
	ServiceKey string
	Origins    map[string]bool // разрешённые источники CORS; пусто — любой (режим разработки)

	loginMu   sync.Mutex
	loginHits map[string][]time.Time // попытки входа по IP — защита от перебора паролей
}

const (
	loginLimit  = 10
	loginWindow = time.Minute
)

// allowLogin — не больше loginLimit попыток входа с одного адреса за loginWindow.
func (a *API) allowLogin(r *http.Request) bool {
	ip, _, err := net.SplitHostPort(r.RemoteAddr)
	if err != nil {
		ip = r.RemoteAddr
	}
	now := time.Now()
	a.loginMu.Lock()
	defer a.loginMu.Unlock()
	if a.loginHits == nil {
		a.loginHits = map[string][]time.Time{}
	}
	recent := a.loginHits[ip][:0]
	for _, t := range a.loginHits[ip] {
		if now.Sub(t) < loginWindow {
			recent = append(recent, t)
		}
	}
	if len(recent) >= loginLimit {
		a.loginHits[ip] = recent
		return false
	}
	a.loginHits[ip] = append(recent, now)
	if len(a.loginHits) > 10000 { // не копим адреса бесконечно
		a.loginHits = map[string][]time.Time{ip: a.loginHits[ip]}
	}
	return true
}

func (a *API) Routes() http.Handler {
	m := http.NewServeMux()
	m.HandleFunc("GET /health", func(w http.ResponseWriter, _ *http.Request) { writeJSON(w, 200, map[string]string{"status": "ok"}) })
	m.HandleFunc("POST /auth/login", a.login)
	m.HandleFunc("GET /auth/me", a.me)

	for _, name := range []string{"topics", "tags", "channels", "banner-types", "segment-types", "segments", "places"} {
		n := name
		m.HandleFunc("GET /"+n, func(w http.ResponseWriter, _ *http.Request) { writeJSON(w, 200, a.S.Dictionary(n)) })
	}
	m.HandleFunc("POST /places", a.body(func(ac service.Actor, _ *http.Request, b map[string]any) (any, *domain.APIError) {
		return a.S.CreatePlace(ac, b)
	}, 201))
	m.HandleFunc("POST /tags", a.body(func(ac service.Actor, _ *http.Request, b map[string]any) (any, *domain.APIError) {
		return a.S.CreateTag(ac, b)
	}, 201))

	m.HandleFunc("GET /campaigns", func(w http.ResponseWriter, _ *http.Request) { writeJSON(w, 200, a.S.List()) })
	m.HandleFunc("GET /campaigns/{id}", a.read(func(r *http.Request) (any, *domain.APIError) { return a.S.Get(id(r)) }))
	m.HandleFunc("POST /campaigns", a.body(func(ac service.Actor, _ *http.Request, b map[string]any) (any, *domain.APIError) {
		return a.S.Create(ac, b)
	}, 201))
	m.HandleFunc("PUT /campaigns/{id}", a.body(func(ac service.Actor, r *http.Request, b map[string]any) (any, *domain.APIError) {
		return a.S.Update(ac, id(r), b)
	}, 200))
	m.HandleFunc("DELETE /campaigns/{id}", a.noBody(func(ac service.Actor, r *http.Request) (any, *domain.APIError) {
		return nil, a.S.Delete(ac, id(r))
	}))
	m.HandleFunc("PUT /campaigns/{id}/segments", a.body(func(ac service.Actor, r *http.Request, b map[string]any) (any, *domain.APIError) {
		return a.S.PutSegments(ac, id(r), b)
	}, 200))

	// баннеры, контент, креативы
	m.HandleFunc("POST /campaigns/{id}/banners", a.body(func(ac service.Actor, r *http.Request, b map[string]any) (any, *domain.APIError) {
		return a.S.SaveBanner(ac, id(r), 0, b)
	}, 201))
	m.HandleFunc("PUT /campaigns/{id}/banners/{cid}", a.body(func(ac service.Actor, r *http.Request, b map[string]any) (any, *domain.APIError) {
		return a.S.SaveBanner(ac, id(r), cid(r), b)
	}, 200))
	m.HandleFunc("DELETE /campaigns/{id}/banners/{cid}", a.noBody(func(ac service.Actor, r *http.Request) (any, *domain.APIError) {
		return nil, a.S.DeleteBanner(ac, id(r), cid(r))
	}))
	m.HandleFunc("POST /campaigns/{id}/contents", a.body(func(ac service.Actor, r *http.Request, b map[string]any) (any, *domain.APIError) {
		return a.S.SaveContent(ac, id(r), 0, b)
	}, 201))
	m.HandleFunc("PUT /campaigns/{id}/contents/{cid}", a.body(func(ac service.Actor, r *http.Request, b map[string]any) (any, *domain.APIError) {
		return a.S.SaveContent(ac, id(r), cid(r), b)
	}, 200))
	m.HandleFunc("DELETE /campaigns/{id}/contents/{cid}", a.noBody(func(ac service.Actor, r *http.Request) (any, *domain.APIError) {
		return nil, a.S.DeleteContent(ac, id(r), cid(r))
	}))
	m.HandleFunc("POST /campaigns/{id}/creatives", a.body(func(ac service.Actor, r *http.Request, b map[string]any) (any, *domain.APIError) {
		return a.S.SaveCreative(ac, id(r), 0, b)
	}, 201))
	m.HandleFunc("PUT /campaigns/{id}/creatives/{cid}", a.body(func(ac service.Actor, r *http.Request, b map[string]any) (any, *domain.APIError) {
		return a.S.SaveCreative(ac, id(r), cid(r), b)
	}, 200))
	m.HandleFunc("DELETE /campaigns/{id}/creatives/{cid}", a.noBody(func(ac service.Actor, r *http.Request) (any, *domain.APIError) {
		return nil, a.S.DeleteCreative(ac, id(r), cid(r))
	}))

	m.HandleFunc("GET /campaigns/{id}/warnings", a.read(func(r *http.Request) (any, *domain.APIError) { return a.S.Warnings(id(r)) }))
	m.HandleFunc("GET /campaigns/{id}/stats", a.read(func(r *http.Request) (any, *domain.APIError) { return a.S.Stats(id(r), r.URL.Query().Get("period")) }))
	m.HandleFunc("GET /campaigns/{id}/audit", a.read(func(r *http.Request) (any, *domain.APIError) { return a.S.Audit(id(r)) }))

	// жизненный цикл
	m.HandleFunc("POST /campaigns/{id}/to-moderation", a.noBody(func(ac service.Actor, r *http.Request) (any, *domain.APIError) {
		return a.S.ToModeration(ac, id(r))
	}))
	m.HandleFunc("POST /campaigns/{id}/decline", a.body(func(ac service.Actor, r *http.Request, b map[string]any) (any, *domain.APIError) {
		c, _ := b["comment"].(string)
		return a.S.Decline(ac, id(r), c)
	}, 200))
	m.HandleFunc("POST /campaigns/{id}/approve", a.noBody(func(ac service.Actor, r *http.Request) (any, *domain.APIError) {
		return a.S.Approve(ac, id(r))
	}))
	m.HandleFunc("POST /campaigns/{id}/activate", a.noBody(func(ac service.Actor, r *http.Request) (any, *domain.APIError) {
		return a.S.Activate(ac, id(r))
	}))
	m.HandleFunc("POST /campaigns/{id}/resume", func(w http.ResponseWriter, r *http.Request) {
		var b struct{ Comment string }
		_ = json.NewDecoder(http.MaxBytesReader(w, r.Body, 1<<16)).Decode(&b) // тело необязательно
		v, e := a.S.Resume(actor(r), id(r), b.Comment)
		respond(w, v, e, 200)
	})
	m.HandleFunc("POST /campaigns/{id}/stop", a.noBody(func(ac service.Actor, r *http.Request) (any, *domain.APIError) {
		return a.S.Stop(ac, id(r))
	}))

	// заглушка CBRO (mocks/cbro_export.json)
	m.HandleFunc("POST /mock/cbro/export", a.body(func(_ service.Actor, _ *http.Request, b map[string]any) (any, *domain.APIError) {
		v, _ := b["campaignId"].(float64)
		return a.S.CBROExport(int64(v)), nil
	}, 200))

	return a.withHeaders(m)
}

func authError(w http.ResponseWriter, code int, c, msg string) {
	writeJSON(w, code, map[string]any{"errors": []map[string]string{{"code": c, "message": msg}}})
}

func (a *API) login(w http.ResponseWriter, r *http.Request) {
	var b struct{ Login, Password string }
	if err := json.NewDecoder(http.MaxBytesReader(w, r.Body, 1<<16)).Decode(&b); err != nil {
		authError(w, 400, "BODY_INVALID", "Ожидается JSON с полями login и password")
		return
	}
	if a.Auth == nil {
		authError(w, 503, "AUTH_DISABLED", "Вход не настроен")
		return
	}
	if !a.allowLogin(r) {
		w.Header().Set("Retry-After", "60")
		authError(w, 429, "AUTH_TOO_MANY", "Слишком много попыток входа — подождите минуту")
		return
	}
	tok, u, exp, err := a.Auth.Login(b.Login, b.Password)
	if err != nil {
		authError(w, 401, "AUTH_INVALID", "Неверный логин или пароль")
		return
	}
	writeJSON(w, 200, map[string]any{"token": tok, "user": u, "expiresAt": exp.UTC().Format(time.RFC3339)})
}

func (a *API) me(w http.ResponseWriter, r *http.Request) {
	tok := bearer(r)
	if a.Auth == nil || tok == "" {
		authError(w, 401, "AUTH_REQUIRED", "Войдите в рекламный кабинет")
		return
	}
	u, err := a.Auth.Verify(tok)
	if err != nil {
		authError(w, 401, "AUTH_EXPIRED", err.Error())
		return
	}
	writeJSON(w, 200, map[string]any{"user": u})
}

func bearer(r *http.Request) string {
	h := r.Header.Get("Authorization")
	if len(h) > 7 && strings.EqualFold(h[:7], "Bearer ") {
		return strings.TrimSpace(h[7:])
	}
	return ""
}

func actor(r *http.Request) service.Actor {
	return service.Actor{User: r.Header.Get("X-User"), Role: r.Header.Get("X-Role")}
}

func id(r *http.Request) int64  { n, _ := strconv.ParseInt(r.PathValue("id"), 10, 64); return n }
func cid(r *http.Request) int64 { n, _ := strconv.ParseInt(r.PathValue("cid"), 10, 64); return n }

func (a *API) read(fn func(*http.Request) (any, *domain.APIError)) http.HandlerFunc {
	return func(w http.ResponseWriter, r *http.Request) {
		v, e := fn(r)
		respond(w, v, e, 200)
	}
}

func (a *API) noBody(fn func(service.Actor, *http.Request) (any, *domain.APIError)) http.HandlerFunc {
	return func(w http.ResponseWriter, r *http.Request) {
		v, e := fn(actor(r), r)
		code := 200
		if v == nil && e == nil {
			code = 204
		}
		respond(w, v, e, code)
	}
}

func (a *API) body(fn func(service.Actor, *http.Request, map[string]any) (any, *domain.APIError), okCode int) http.HandlerFunc {
	return func(w http.ResponseWriter, r *http.Request) {
		var b map[string]any
		if err := json.NewDecoder(http.MaxBytesReader(w, r.Body, 1<<20)).Decode(&b); err != nil {
			respond(w, nil, domain.Fail("BODY_INVALID", "", err.Error()), 0)
			return
		}
		v, e := fn(actor(r), r, b)
		respond(w, v, e, okCode)
	}
}

func respond(w http.ResponseWriter, v any, e *domain.APIError, okCode int) {
	if e != nil {
		writeJSON(w, e.Status, map[string]any{"errors": e.Errors})
		return
	}
	if okCode == 204 {
		w.WriteHeader(204)
		return
	}
	writeJSON(w, okCode, v)
}

func writeJSON(w http.ResponseWriter, code int, v any) {
	w.Header().Set("Content-Type", "application/json; charset=utf-8")
	w.WriteHeader(code)
	if err := json.NewEncoder(w).Encode(v); err != nil {
		log.Printf("encode: %v", err)
	}
}

// withHeaders: CORS для фронта, проверка входа и эхо X-User/X-Role в ответе (task.md §3).
func (a *API) withHeaders(h http.Handler) http.Handler {
	return http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		if origin := r.Header.Get("Origin"); len(a.Origins) == 0 {
			w.Header().Set("Access-Control-Allow-Origin", "*")
		} else if a.Origins[origin] {
			w.Header().Set("Access-Control-Allow-Origin", origin)
			w.Header().Add("Vary", "Origin")
		}
		w.Header().Set("X-Content-Type-Options", "nosniff")
		w.Header().Set("Cache-Control", "no-store")
		w.Header().Set("Access-Control-Allow-Methods", "GET, POST, PUT, DELETE, OPTIONS")
		w.Header().Set("Access-Control-Allow-Headers", "Content-Type, Authorization, X-User, X-Role, X-Service-Key")
		w.Header().Set("Access-Control-Expose-Headers", "X-User, X-Role")
		if r.Method == http.MethodOptions {
			w.WriteHeader(204)
			return
		}
		if !strings.HasPrefix(r.URL.Path, "/auth/") && r.URL.Path != "/health" {
			if tok := bearer(r); tok != "" && a.Auth != nil {
				u, err := a.Auth.Verify(tok)
				if err != nil {
					authError(w, 401, "AUTH_EXPIRED", err.Error())
					return
				}
				r.Header.Set("X-User", u.User) // роль — только из токена
				r.Header.Set("X-Role", u.Role)
			} else if a.Required && !a.trustedService(r) {
				// без входа данные кабинета недоступны ни на чтение, ни на запись
				authError(w, 401, "AUTH_REQUIRED", "Войдите в рекламный кабинет")
				return
			}
		}
		if u := r.Header.Get("X-User"); u != "" {
			w.Header().Set("X-User", u)
		}
		if role := r.Header.Get("X-Role"); role != "" {
			w.Header().Set("X-Role", role)
		}
		h.ServeHTTP(w, r)
	})
}

func (a *API) trustedService(r *http.Request) bool {
	k := r.Header.Get("X-Service-Key")
	return a.ServiceKey != "" && k != "" && subtle.ConstantTimeCompare([]byte(k), []byte(a.ServiceKey)) == 1
}
