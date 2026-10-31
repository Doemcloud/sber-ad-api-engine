// Package httpapi — HTTP-поверхность MVP (task.md §3): 7 справочников,
// POST /places и /tags, 22 операции с кампаниями и дочерними сущностями.
package httpapi

import (
	"encoding/json"
	"log"
	"net/http"
	"strconv"

	"adcamp/internal/domain"
	"adcamp/internal/service"
)

type API struct{ S *service.Service }

func (a *API) Routes() http.Handler {
	m := http.NewServeMux()
	m.HandleFunc("GET /health", func(w http.ResponseWriter, _ *http.Request) { writeJSON(w, 200, map[string]string{"status": "ok"}) })

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
	m.HandleFunc("POST /campaigns/{id}/stop", a.noBody(func(ac service.Actor, r *http.Request) (any, *domain.APIError) {
		return a.S.Stop(ac, id(r))
	}))

	// заглушка CBRO (mocks/cbro_export.json)
	m.HandleFunc("POST /mock/cbro/export", a.body(func(_ service.Actor, _ *http.Request, b map[string]any) (any, *domain.APIError) {
		v, _ := b["campaignId"].(float64)
		return a.S.CBROExport(int64(v)), nil
	}, 200))

	return withHeaders(m)
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

// withHeaders: CORS для фронта и эхо X-User/X-Role в ответе (task.md §3).
func withHeaders(h http.Handler) http.Handler {
	return http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		w.Header().Set("Access-Control-Allow-Origin", "*")
		w.Header().Set("Access-Control-Allow-Methods", "GET, POST, PUT, DELETE, OPTIONS")
		w.Header().Set("Access-Control-Allow-Headers", "Content-Type, X-User, X-Role")
		w.Header().Set("Access-Control-Expose-Headers", "X-User, X-Role")
		if u := r.Header.Get("X-User"); u != "" {
			w.Header().Set("X-User", u)
		}
		if role := r.Header.Get("X-Role"); role != "" {
			w.Header().Set("X-Role", role)
		}
		if r.Method == http.MethodOptions {
			w.WriteHeader(204)
			return
		}
		h.ServeHTTP(w, r)
	})
}
