// Package domain — правила сущности кампании: обязательные поля, ссылки на
// справочники, статусы. Решение «хватает данных?» принимает этот код, а не LLM.
package domain

import (
	"fmt"
	"slices"
	"time"

	"adcamp/api/internal/store"
)

// RequiredFields — обязательные поля кампании. Сверить с доменной моделью заказчика.
var RequiredFields = []string{"name", "advertiser_id", "goal", "offer", "segment_ids", "placement_ids", "budget_rub", "start_date", "end_date"}

var Statuses = []string{"draft", "needs_info", "ready", "generated", "moderation", "approved", "rejected", "active", "paused", "finished"}

// Разрешённые переходы статусов.
var transitions = map[string][]string{
	"draft":      {"needs_info", "ready", "moderation"},
	"needs_info": {"ready", "draft"},
	"ready":      {"generated", "moderation", "draft"},
	"generated":  {"moderation", "draft"},
	"moderation": {"approved", "rejected"},
	"rejected":   {"draft"},
	"approved":   {"active", "draft"},
	"active":     {"paused", "finished"},
	"paused":     {"active", "finished"},
}

type Problem struct {
	Field   string `json:"field"`
	Message string `json:"message"`
}

// Validate возвращает список недостающих полей и битых ссылок.
func Validate(c store.Doc, s store.Store) []Problem {
	var out []Problem
	for _, f := range RequiredFields {
		if isEmpty(c[f]) {
			out = append(out, Problem{f, "обязательное поле не заполнено"})
		}
	}
	if id, ok := c["advertiser_id"].(string); ok && id != "" && !s.Exists("advertisers", id) {
		out = append(out, Problem{"advertiser_id", "рекламодатель " + id + " не найден"})
	}
	for _, ref := range []struct{ field, coll string }{{"segment_ids", "segments"}, {"placement_ids", "placements"}} {
		for _, id := range strings(c[ref.field]) {
			if !s.Exists(ref.coll, id) {
				out = append(out, Problem{ref.field, fmt.Sprintf("%s не найден в справочнике %s", id, ref.coll)})
			}
		}
	}
	start, e1 := time.Parse(time.DateOnly, str(c["start_date"]))
	end, e2 := time.Parse(time.DateOnly, str(c["end_date"]))
	if e1 == nil && e2 == nil && end.Before(start) {
		out = append(out, Problem{"end_date", "дата окончания раньше даты начала"})
	}
	if b, ok := c["budget_rub"].(float64); ok && b <= 0 {
		out = append(out, Problem{"budget_rub", "бюджет должен быть больше 0"})
	}
	return out
}

func CanTransition(from, to string) bool {
	return slices.Contains(transitions[from], to)
}

func isEmpty(v any) bool {
	switch x := v.(type) {
	case nil:
		return true
	case string:
		return x == ""
	case []any:
		return len(x) == 0
	}
	return false
}

func str(v any) string { s, _ := v.(string); return s }

func strings(v any) []string {
	arr, _ := v.([]any)
	out := make([]string, 0, len(arr))
	for _, x := range arr {
		if s, ok := x.(string); ok {
			out = append(out, s)
		}
	}
	return out
}
