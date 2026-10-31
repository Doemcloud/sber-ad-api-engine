package store

import (
	"os"
	"reflect"
	"testing"
)

// Интеграционный тест хранилища в Pangolin DB / PostgreSQL.
// Запуск: TEST_DATABASE_URL=postgres://user:pass@host:5432/db?sslmode=disable go test ./internal/store/
// БД должна быть пустой: тест заполнит её из моков и проверит, что состояние читается обратно без потерь.
func TestPangolinRoundTrip(t *testing.T) {
	dsn := os.Getenv("TEST_DATABASE_URL")
	if dsn == "" {
		t.Skip("TEST_DATABASE_URL не задан")
	}
	a, err := OpenDB("../../../data/mock", dsn)
	if err != nil {
		t.Fatal(err)
	}
	c := a.S.Campaigns[101]
	c.State, c.LastEditAuthor = "ON_MODERATION", "ivanov.p"
	c.Segments.Excluded = append(c.Segments.Excluded, "EXC_EMPLOYEES")
	if err := a.Save(); err != nil {
		t.Fatal(err)
	}
	b, err := OpenDB("../../../data/mock", dsn)
	if err != nil {
		t.Fatal(err)
	}
	for id, want := range a.S.Campaigns {
		if got := b.S.Campaigns[id]; !reflect.DeepEqual(got, want) {
			t.Fatalf("кампания %d: после чтения из БД\n got %+v\nwant %+v", id, got, want)
		}
	}
	if len(b.S.Audit) != len(a.S.Audit) || len(b.S.Banners) != len(a.S.Banners) || len(b.S.Creatives) != len(a.S.Creatives) {
		t.Fatalf("потери: аудит %d/%d, баннеры %d/%d, креативы %d/%d", len(b.S.Audit), len(a.S.Audit), len(b.S.Banners), len(a.S.Banners), len(b.S.Creatives), len(a.S.Creatives))
	}
}
