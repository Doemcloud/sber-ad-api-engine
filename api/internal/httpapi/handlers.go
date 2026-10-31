package httpapi

import (
	"crypto/rand"
	"encoding/hex"
	"encoding/json"
	"errors"
	"net/http"
	"slices"
	"strings"
	"time"

	"adcamp/api/internal/domain"
	"adcamp/api/internal/store"
)

type API struct{ S store.Store }

func (a *API) Routes() http.Handler {
	m := http.NewServeMux()
	m.HandleFunc("GET /health", func(w http.ResponseWriter, _ *http.Request) { writeJSON(w, 200, map[string]string{"status": "ok"}) })

	// Справочники: чтение и создание (сегменты и рекламодатели создаются из диалога).
	for _, c := range []string{"segments", "placements", "advertisers", "creative_types"} {
		coll := c
		m.HandleFunc("GET /api/"+coll, func(w http.ResponseWriter, _ *http.Request) { writeJSON(w, 200, a.S.List(coll)) })
		m.HandleFunc("GET /api/"+coll+"/{id}", a.getOne(coll))
	}
	m.HandleFunc("POST /api/segments", a.createRef("segments", "seg", []string{"name", "conditions"}))
	m.HandleFunc("POST /api/advertisers", a.createRef("advertisers", "adv", []string{"name", "inn", "category"}))

	// Кампании.
	m.HandleFunc("GET /api/campaigns", a.listCampaigns)
	m.HandleFunc("GET /api/campaigns/{id}", a.getOne("campaigns"))
	m.HandleFunc("POST /api/campaigns", a.createCampaign)
	m.HandleFunc("PUT /api/campaigns/{id}", a.updateCampaign)
	m.HandleFunc("POST /api/campaigns/{id}/status", a.changeStatus)
	m.HandleFunc("POST /api/campaigns/validate", a.validateDraft)
	m.HandleFunc("GET /api/schema/required", func(w http.ResponseWriter, _ *http.Request) {
		writeJSON(w, 200, map[string]any{"required": domain.RequiredFields, "statuses": domain.Statuses})
	})
	return cors(m)
}

func (a *API) getOne(coll string) http.HandlerFunc {
	return func(w http.ResponseWriter, r *http.Request) {
		d, err := a.S.Get(coll, r.PathValue("id"))
		if errors.Is(err, store.ErrNotFound) {
			writeErr(w, 404, "не найдено")
			return
		}
		writeJSON(w, 200, d)
	}
}

func (a *API) createRef(coll, prefix string, required []string) http.HandlerFunc {
	return func(w http.ResponseWriter, r *http.Request) {
		d, ok := readDoc(w, r)
		if !ok {
			return
		}
		for _, f := range required {
			if d[f] == nil || d[f] == "" {
				writeErr(w, 422, "не заполнено поле "+f)
				return
			}
		}
		d["id"] = newID(prefix)
		d["created_at"] = now()
		if err := a.S.Put(coll, d); err != nil {
			writeErr(w, 500, err.Error())
			return
		}
		writeJSON(w, 201, d)
	}
}

// listCampaigns: фильтры ?status=&advertiser_id=&placement_id=&segment_id=&q=
func (a *API) listCampaigns(w http.ResponseWriter, r *http.Request) {
	q := r.URL.Query()
	out := []store.Doc{}
	for _, c := range a.S.List("campaigns") {
		if v := q.Get("status"); v != "" && c["status"] != v {
			continue
		}
		if v := q.Get("advertiser_id"); v != "" && c["advertiser_id"] != v {
			continue
		}
		if v := q.Get("placement_id"); v != "" && !containsStr(c["placement_ids"], v) {
			continue
		}
		if v := q.Get("segment_id"); v != "" && !containsStr(c["segment_ids"], v) {
			continue
		}
		if v := strings.ToLower(q.Get("q")); v != "" && !strings.Contains(strings.ToLower(str(c["name"])), v) {
			continue
		}
		out = append(out, c)
	}
	writeJSON(w, 200, out)
}

// createCampaign сохраняет даже неполный черновик: итог работы ассистента
// должен быть в БД. Статус ставится по результату валидации.
func (a *API) createCampaign(w http.ResponseWriter, r *http.Request) {
	d, ok := readDoc(w, r)
	if !ok {
		return
	}
	d["id"] = newID("cmp")
	d["created_at"] = now()
	a.saveCampaign(w, d, 201)
}

func (a *API) updateCampaign(w http.ResponseWriter, r *http.Request) {
	old, err := a.S.Get("campaigns", r.PathValue("id"))
	if err != nil {
		writeErr(w, 404, "кампания не найдена")
		return
	}
	patch, ok := readDoc(w, r)
	if !ok {
		return
	}
	if st := str(old["status"]); slices.Contains([]string{"moderation", "active"}, st) {
		writeErr(w, 409, "кампанию в статусе "+st+" менять нельзя: сначала верните в черновик или поставьте на паузу")
		return
	}
	merged := store.Doc{}
	for k, v := range old {
		merged[k] = v
	}
	for k, v := range patch {
		merged[k] = v
	}
	merged["id"], merged["created_at"] = old["id"], old["created_at"]
	// Любая правка одобренной кампании возвращает её на согласование.
	if old["status"] == "approved" {
		merged["status"] = "draft"
	}
	a.saveCampaign(w, merged, 200)
}

func (a *API) saveCampaign(w http.ResponseWriter, d store.Doc, code int) {
	problems := domain.Validate(d, a.S)
	st := str(d["status"])
	if st == "" || st == "draft" || st == "needs_info" || st == "ready" {
		if len(problems) > 0 {
			d["status"] = "needs_info"
		} else {
			d["status"] = "ready"
		}
	}
	d["updated_at"] = now()
	if err := a.S.Put("campaigns", d); err != nil {
		writeErr(w, 500, err.Error())
		return
	}
	writeJSON(w, code, map[string]any{"campaign": d, "problems": problems})
}

func (a *API) changeStatus(w http.ResponseWriter, r *http.Request) {
	c, err := a.S.Get("campaigns", r.PathValue("id"))
	if err != nil {
		writeErr(w, 404, "кампания не найдена")
		return
	}
	body, ok := readDoc(w, r)
	if !ok {
		return
	}
	to := str(body["status"])
	from := str(c["status"])
	if !domain.CanTransition(from, to) {
		writeErr(w, 409, "переход "+from+" → "+to+" запрещён")
		return
	}
	if to == "moderation" {
		if p := domain.Validate(c, a.S); len(p) > 0 {
			writeJSON(w, 422, map[string]any{"error": "кампания неполная", "problems": p})
			return
		}
	}
	c["status"] = to
	c["updated_at"] = now()
	if err := a.S.Put("campaigns", c); err != nil {
		writeErr(w, 500, err.Error())
		return
	}
	writeJSON(w, 200, c)
}

func (a *API) validateDraft(w http.ResponseWriter, r *http.Request) {
	d, ok := readDoc(w, r)
	if !ok {
		return
	}
	p := domain.Validate(d, a.S)
	missing := []string{}
	for _, x := range p {
		missing = append(missing, x.Field)
	}
	writeJSON(w, 200, map[string]any{"complete": len(p) == 0, "problems": p, "missing": missing})
}

// --- helpers ---

func readDoc(w http.ResponseWriter, r *http.Request) (store.Doc, bool) {
	var d store.Doc
	dec := json.NewDecoder(http.MaxBytesReader(w, r.Body, 1<<20))
	if err := dec.Decode(&d); err != nil {
		writeErr(w, 400, "некорректный JSON: "+err.Error())
		return nil, false
	}
	return d, true
}

func writeJSON(w http.ResponseWriter, code int, v any) {
	w.Header().Set("Content-Type", "application/json; charset=utf-8")
	w.WriteHeader(code)
	_ = json.NewEncoder(w).Encode(v)
}

func writeErr(w http.ResponseWriter, code int, msg string) {
	writeJSON(w, code, map[string]string{"error": msg})
}

func cors(h http.Handler) http.Handler {
	return http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		w.Header().Set("Access-Control-Allow-Origin", "*")
		w.Header().Set("Access-Control-Allow-Methods", "GET, POST, PUT, OPTIONS")
		w.Header().Set("Access-Control-Allow-Headers", "Content-Type")
		if r.Method == http.MethodOptions {
			w.WriteHeader(204)
			return
		}
		h.ServeHTTP(w, r)
	})
}

func newID(prefix string) string {
	b := make([]byte, 4)
	_, _ = rand.Read(b)
	return prefix + "_" + hex.EncodeToString(b)
}

func now() string { return time.Now().UTC().Format(time.RFC3339) }

func str(v any) string { s, _ := v.(string); return s }

func containsStr(v any, s string) bool {
	arr, _ := v.([]any)
	for _, x := range arr {
		if x == s {
			return true
		}
	}
	return false
}
