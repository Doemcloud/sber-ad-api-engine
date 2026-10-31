package main

import (
	"log"
	"net/http"
	"os"
	"path/filepath"
	"time"

	"adcamp/internal/auth"
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
	var st *store.Store
	var err error
	if dsn := os.Getenv("DATABASE_URL"); dsn != "" {
		st, err = store.OpenDB(mockDir, dsn)
		if err != nil {
			log.Fatalf("Pangolin DB: %v", err)
		}
		log.Printf("хранилище: Pangolin DB (%s)", store.DescribeDSN(dsn))
	} else {
		st, err = store.Open(mockDir, env("STATE_FILE", "./state/state.json"))
		if err != nil {
			log.Fatal(err)
		}
		log.Printf("хранилище: файл (DATABASE_URL не задан)")
	}
	addr := ":" + env("PORT", "8080")
	log.Printf("campaigns API on %s (mocks: %s)", addr, mockDir)
	ttl, err := time.ParseDuration(env("AUTH_TTL", "12h"))
	if err != nil {
		log.Fatalf("AUTH_TTL: %v", err)
	}
	au, err := auth.Load(filepath.Join(mockDir, "users.json"), env("AUTH_SECRET", "sber-ad-dev-secret-change-me"), ttl)
	if err != nil {
		log.Fatalf("учётки: %v", err)
	}
	api := &httpapi.API{S: service.New(st), Auth: au, Required: env("AUTH_REQUIRED", "0") == "1", ServiceKey: os.Getenv("SERVICE_KEY")}
	log.Printf("вход по логину: обязателен=%v", api.Required)
	log.Fatal(http.ListenAndServe(addr, api.Routes()))
}
