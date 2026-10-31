package main

import (
	"log"
	"net/http"
	"os"
	"path/filepath"

	"adcamp/internal/domain"
	"adcamp/internal/httpapi"
	"adcamp/internal/service"
	"adcamp/internal/store"
)

func env(k, def string) string {
	if v := os.Getenv(k); v != "" {
		return v
	}
	return def
}

func main() {
	mockDir := env("MOCK_DIR", "../data/mock")
	if err := domain.LoadCatalog(filepath.Join(mockDir, "validation_rules.json")); err != nil {
		log.Fatalf("каталог ошибок: %v", err)
	}
	st, err := store.Open(mockDir, env("STATE_FILE", "./state/state.json"))
	if err != nil {
		log.Fatal(err)
	}
	addr := ":" + env("PORT", "8080")
	log.Printf("campaigns API on %s (mocks: %s)", addr, mockDir)
	log.Fatal(http.ListenAndServe(addr, (&httpapi.API{S: service.New(st)}).Routes()))
}
