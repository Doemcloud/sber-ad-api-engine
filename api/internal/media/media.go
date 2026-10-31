// Package media хранит изображения креативов (нейрогенерация агента): PostgreSQL или
// каталог на диске в режиме без СУБД. Изображения неизменяемы и адресуются UUID.
package media

import (
	"crypto/rand"
	"database/sql"
	"encoding/hex"
	"encoding/json"
	"errors"
	"fmt"
	"net/http"
	"os"
	"path/filepath"
	"regexp"
	"time"
)

const MaxSize = 8 << 20 // 8 МБ на изображение

var (
	ErrNotFound = errors.New("изображение не найдено")
	ErrType     = errors.New("поддерживаются только JPEG, PNG и WebP")
	ErrSize     = errors.New("изображение больше 8 МБ")
	reID        = regexp.MustCompile(`^[0-9a-f]{8}-[0-9a-f]{4}-4[0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$`)
)

type Image struct {
	ID     string
	Mime   string
	Data   []byte
	Prompt string
	Author string
}

type Store interface {
	Put(img Image) (string, error)
	Get(id string) (*Image, error)
}

// ValidID — только UUID v4 в нижнем регистре: id приходит из URL.
func ValidID(id string) bool { return reID.MatchString(id) }

// Sniff определяет тип по содержимому (заголовок Content-Type не доверяем).
func Sniff(data []byte) (string, error) {
	if len(data) == 0 {
		return "", ErrType
	}
	if len(data) > MaxSize {
		return "", ErrSize
	}
	switch t := http.DetectContentType(data); t {
	case "image/jpeg", "image/png", "image/webp":
		return t, nil
	}
	return "", ErrType
}

func newID() string {
	b := make([]byte, 16)
	_, _ = rand.Read(b)
	b[6] = b[6]&0x0f | 0x40
	b[8] = b[8]&0x3f | 0x80
	h := hex.EncodeToString(b)
	return h[0:8] + "-" + h[8:12] + "-" + h[12:16] + "-" + h[16:20] + "-" + h[20:]
}

func prepare(img *Image) error {
	mime, err := Sniff(img.Data)
	if err != nil {
		return err
	}
	img.Mime, img.ID = mime, newID()
	if r := []rune(img.Prompt); len(r) > 1000 {
		img.Prompt = string(r[:1000])
	}
	return nil
}

// ---------- PostgreSQL ----------

type PG struct{ DB *sql.DB }

func (p PG) Put(img Image) (string, error) {
	if err := prepare(&img); err != nil {
		return "", err
	}
	_, err := p.DB.Exec(`INSERT INTO media (id, mime, data, prompt, author) VALUES ($1, $2, $3, $4, $5)`,
		img.ID, img.Mime, img.Data, img.Prompt, img.Author)
	return img.ID, err
}

func (p PG) Get(id string) (*Image, error) {
	if !ValidID(id) {
		return nil, ErrNotFound
	}
	img := Image{ID: id}
	var prompt sql.NullString
	err := p.DB.QueryRow(`SELECT mime, data, prompt, author FROM media WHERE id = $1`, id).Scan(&img.Mime, &img.Data, &prompt, &img.Author)
	if errors.Is(err, sql.ErrNoRows) {
		return nil, ErrNotFound
	}
	img.Prompt = prompt.String
	return &img, err
}

// ---------- каталог на диске ----------

type Dir struct{ Path string }

type meta struct {
	Mime   string    `json:"mime"`
	Prompt string    `json:"prompt"`
	Author string    `json:"author"`
	At     time.Time `json:"at"`
}

func (d Dir) Put(img Image) (string, error) {
	if err := prepare(&img); err != nil {
		return "", err
	}
	if err := os.MkdirAll(d.Path, 0o750); err != nil {
		return "", err
	}
	m, _ := json.Marshal(meta{img.Mime, img.Prompt, img.Author, time.Now().UTC()})
	if err := os.WriteFile(filepath.Join(d.Path, img.ID+".json"), m, 0o640); err != nil {
		return "", err
	}
	return img.ID, os.WriteFile(filepath.Join(d.Path, img.ID), img.Data, 0o640)
}

func (d Dir) Get(id string) (*Image, error) {
	if !ValidID(id) {
		return nil, ErrNotFound
	}
	raw, err := os.ReadFile(filepath.Join(d.Path, id+".json"))
	if err != nil {
		return nil, ErrNotFound
	}
	var m meta
	if err := json.Unmarshal(raw, &m); err != nil {
		return nil, fmt.Errorf("метаданные %s: %w", id, err)
	}
	data, err := os.ReadFile(filepath.Join(d.Path, id))
	if err != nil {
		return nil, ErrNotFound
	}
	return &Image{ID: id, Mime: m.Mime, Data: data, Prompt: m.Prompt, Author: m.Author}, nil
}
