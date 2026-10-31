package main

import (
	"crypto/rand"
	"encoding/hex"
	"log"
	"net/http"
	"os"
	"path/filepath"
	"strings"
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
			log.Fatalf("PostgreSQL: %v", err)
		}
		log.Printf("хранилище: PostgreSQL (%s)", store.DescribeDSN(dsn))
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
	secret := os.Getenv("AUTH_SECRET")
	if secret == "" {
		// без заданного ключа — случайный на каждый запуск: подделать токен нельзя,
		// после перезапуска API пользователи просто входят заново
		b := make([]byte, 32)
		if _, err := rand.Read(b); err != nil {
			log.Fatal(err)
		}
		secret = hex.EncodeToString(b)
		log.Printf("AUTH_SECRET не задан — сгенерирован случайный ключ подписи токенов")
	} else if len(secret) < 16 {
		log.Fatalf("AUTH_SECRET слишком короткий: нужно не меньше 16 символов")
	}
	au, err := auth.Load(filepath.Join(mockDir, "users.json"), secret, ttl)
	if err != nil {
		log.Fatalf("учётки: %v", err)
	}
	origins := map[string]bool{}
	for _, o := range strings.Split(os.Getenv("CORS_ORIGINS"), ",") {
		if o = strings.TrimSpace(o); o != "" {
			origins[o] = true
		}
	}
	api := &httpapi.API{S: service.New(st), Auth: au, Required: env("AUTH_REQUIRED", "0") == "1", ServiceKey: os.Getenv("SERVICE_KEY"), Origins: origins}
	log.Printf("вход по логину: обязателен=%v; CORS: %d источник(ов)", api.Required, len(origins))
	srv := &http.Server{Addr: addr, Handler: api.Routes(),
		ReadHeaderTimeout: 10 * time.Second, ReadTimeout: 30 * time.Second, WriteTimeout: 60 * time.Second, IdleTimeout: 120 * time.Second, MaxHeaderBytes: 64 << 10}
	log.Fatal(srv.ListenAndServe())
}
