package domain

import (
	"encoding/json"
	"fmt"
	"os"
	"sync"
)

// FieldError — элемент тела ошибки {"errors": [...]} (task.md §3).
type FieldError struct {
	Code    string `json:"code"`
	Message string `json:"message"`
	Field   string `json:"field,omitempty"`
}

// APIError — ошибка бизнес-операции: HTTP-статус + список ошибок.
type APIError struct {
	Status int
	Errors []FieldError
}

func (e *APIError) Error() string {
	if len(e.Errors) == 0 {
		return fmt.Sprintf("HTTP %d", e.Status)
	}
	return e.Errors[0].Code + ": " + e.Errors[0].Message
}

type ruleFile struct {
	Errors []struct {
		Code    string  `json:"code"`
		Message string  `json:"message"`
		Field   *string `json:"field"`
	} `json:"errors"`
	Warnings []struct {
		Code    string `json:"code"`
		Message string `json:"message"`
	} `json:"warnings"`
}

var (
	catMu       sync.RWMutex
	errMessages = map[string]string{}
	errFields   = map[string]string{}
	warnMessage = map[string]string{
		"PLACE_NO_CREATIVE": "Не для всех мест показа настроены креативы",
		"PLACE_INACTIVE":    "Некоторые места показа деактивированы",
		"TAGS_MISSING":      "У кампании отсутствуют теги",
	}
)

// LoadCatalog читает каталог кодов ошибок (mocks/validation_rules.json).
func LoadCatalog(path string) error {
	raw, err := os.ReadFile(path)
	if err != nil {
		return err
	}
	var rf ruleFile
	if err := json.Unmarshal(raw, &rf); err != nil {
		return err
	}
	catMu.Lock()
	defer catMu.Unlock()
	for _, e := range rf.Errors {
		errMessages[e.Code] = e.Message
		if e.Field != nil {
			errFields[e.Code] = *e.Field
		}
	}
	for _, w := range rf.Warnings {
		warnMessage[w.Code] = w.Message
	}
	return nil
}

// NewFieldError собирает ошибку по коду каталога; detail уточняет сообщение.
func NewFieldError(code, field, detail string) FieldError {
	catMu.RLock()
	msg, ok := errMessages[code]
	if field == "" {
		field = errFields[code]
	}
	catMu.RUnlock()
	if !ok {
		msg = code
	}
	if detail != "" {
		msg += ": " + detail
	}
	return FieldError{Code: code, Message: msg, Field: field}
}

func WarningMessage(code string) string {
	catMu.RLock()
	defer catMu.RUnlock()
	return warnMessage[code]
}

func BadRequest(errs ...FieldError) *APIError { return &APIError{Status: 400, Errors: errs} }

func NotFound(what string) *APIError {
	return &APIError{Status: 404, Errors: []FieldError{NewFieldError("ENTITY_NOT_FOUND", "", what)}}
}

func Fail(code, field, detail string) *APIError {
	return BadRequest(NewFieldError(code, field, detail))
}
