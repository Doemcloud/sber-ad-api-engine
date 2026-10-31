package main

import (
	"log"
	"net/http"
	"os"

	"adcamp/api/internal/httpapi"
	"adcamp/api/internal/store"
)

func env(k, def string) string {
	if v := os.Getenv(k); v != "" {
		return v
	}
	return def
}

func main() {
	s, err := store.Open(env("SEED_DIR", "../data/mock"), env("STATE_DIR", "./state"))
	if err != nil {
		log.Fatal(err)
	}
	addr := ":" + env("PORT", "8080")
	log.Printf("api listening on %s", addr)
	log.Fatal(http.ListenAndServe(addr, (&httpapi.API{S: s}).Routes()))
}
