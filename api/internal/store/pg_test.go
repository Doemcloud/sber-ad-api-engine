package store

import (
	"database/sql"
	"os"
	"reflect"
	"testing"
)

// freshDB — тестовая БД с нуля (TEST_DATABASE_URL — только под тесты: схема пересоздаётся).
func freshDB(t *testing.T) string {
	t.Helper()
	dsn := os.Getenv("TEST_DATABASE_URL")
	if dsn == "" {
		t.Skip("TEST_DATABASE_URL не задан")
	}
	db, err := sql.Open("postgres", dsn)
	if err != nil {
		t.Fatal(err)
	}
	defer db.Close()
	if _, err := db.Exec(`DROP SCHEMA public CASCADE; CREATE SCHEMA public`); err != nil {
		t.Fatal(err)
	}
	return dsn
}

// Интеграционный тест хранилища в PostgreSQL.
// Запуск: TEST_DATABASE_URL=postgres://user:pass@host:5432/db?sslmode=disable go test ./internal/store/
// Схема пересоздаётся: тест заполнит БД из моков и проверит, что состояние читается обратно без потерь.
func TestPostgresRoundTrip(t *testing.T) {
	dsn := freshDB(t)
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

// Если запись в БД не удалась, память возвращается к состоянию БД — без расхождений.
func TestFailedSaveResyncsMemory(t *testing.T) {
	st, err := OpenDB("../../../data/mock", freshDB(t))
	if err != nil {
		t.Fatal(err)
	}
	c := st.S.Campaigns[101]
	before := append([]string(nil), c.Segments.Excluded...)
	c.Segments.Excluded = append(c.Segments.Excluded, before[0]) // дубликат нарушает первичный ключ
	if err := st.Save(); err == nil {
		t.Fatal("ждали ошибку записи")
	}
	if got := st.S.Campaigns[101].Segments.Excluded; !reflect.DeepEqual(got, before) {
		t.Fatalf("память не вернулась к БД: %v, ждали %v", got, before)
	}
}
