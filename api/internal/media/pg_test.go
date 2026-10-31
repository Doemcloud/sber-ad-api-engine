package media

import (
	"database/sql"
	"os"
	"testing"

	_ "github.com/lib/pq"
)

func TestPGRoundTrip(t *testing.T) {
	dsn := os.Getenv("TEST_DATABASE_URL")
	if dsn == "" {
		t.Skip("TEST_DATABASE_URL не задан")
	}
	db, err := sql.Open("postgres", dsn)
	if err != nil {
		t.Fatal(err)
	}
	defer db.Close()
	raw, _ := os.ReadFile("../store/migrations/002_media.sql")
	if _, err := db.Exec(string(raw)); err != nil {
		t.Fatal(err)
	}
	p := PG{DB: db}
	png := append([]byte("\x89PNG\r\n\x1a\n"), make([]byte, 32)...)
	id, err := p.Put(Image{Data: png, Prompt: "парк", Author: "ivanov.p"})
	if err != nil {
		t.Fatal(err)
	}
	img, err := p.Get(id)
	if err != nil || img.Mime != "image/png" || img.Prompt != "парк" {
		t.Fatalf("%+v %v", img, err)
	}
	if _, err := p.Get("00000000-0000-4000-8000-000000000000"); err != ErrNotFound {
		t.Fatalf("нет записи: %v", err)
	}
}
