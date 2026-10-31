// Package store — хранилище MVP: коллекции JSON-документов в памяти,
// загружаемые из mock-файлов и сохраняемые на диск после каждой записи.
// Интерфейс Store позволяет позже заменить реализацию на Postgres.
package store

import (
	"encoding/json"
	"errors"
	"fmt"
	"os"
	"path/filepath"
	"sort"
	"sync"
)

type Doc = map[string]any

var ErrNotFound = errors.New("not found")

type Store interface {
	List(coll string) []Doc
	Get(coll, id string) (Doc, error)
	Put(coll string, d Doc) error
	Exists(coll, id string) bool
}

// Collections — справочники и сущности, которые знает API.
var Collections = []string{"segments", "placements", "advertisers", "creative_types", "campaigns"}

type FileStore struct {
	mu   sync.RWMutex
	dir  string // куда сохраняем состояние
	data map[string]map[string]Doc
}

// Open читает состояние из stateDir; если его нет — из seedDir (mock-файлы).
func Open(seedDir, stateDir string) (*FileStore, error) {
	s := &FileStore{dir: stateDir, data: map[string]map[string]Doc{}}
	if err := os.MkdirAll(stateDir, 0o755); err != nil {
		return nil, err
	}
	for _, c := range Collections {
		s.data[c] = map[string]Doc{}
		path := filepath.Join(stateDir, c+".json")
		if _, err := os.Stat(path); err != nil {
			path = filepath.Join(seedDir, c+".json")
		}
		raw, err := os.ReadFile(path)
		if errors.Is(err, os.ErrNotExist) {
			continue
		}
		if err != nil {
			return nil, err
		}
		var docs []Doc
		if err := json.Unmarshal(raw, &docs); err != nil {
			return nil, fmt.Errorf("%s: %w", path, err)
		}
		for _, d := range docs {
			id, _ := d["id"].(string)
			if id == "" {
				return nil, fmt.Errorf("%s: документ без id", path)
			}
			s.data[c][id] = d
		}
	}
	return s, nil
}

func (s *FileStore) List(coll string) []Doc {
	s.mu.RLock()
	defer s.mu.RUnlock()
	out := make([]Doc, 0, len(s.data[coll]))
	for _, d := range s.data[coll] {
		out = append(out, d)
	}
	sort.Slice(out, func(i, j int) bool { return fmt.Sprint(out[i]["id"]) < fmt.Sprint(out[j]["id"]) })
	return out
}

func (s *FileStore) Get(coll, id string) (Doc, error) {
	s.mu.RLock()
	defer s.mu.RUnlock()
	d, ok := s.data[coll][id]
	if !ok {
		return nil, ErrNotFound
	}
	return d, nil
}

func (s *FileStore) Exists(coll, id string) bool {
	_, err := s.Get(coll, id)
	return err == nil
}

func (s *FileStore) Put(coll string, d Doc) error {
	id, _ := d["id"].(string)
	if id == "" {
		return errors.New("id required")
	}
	s.mu.Lock()
	defer s.mu.Unlock()
	if s.data[coll] == nil {
		return fmt.Errorf("unknown collection %q", coll)
	}
	s.data[coll][id] = d
	return s.flush(coll)
}

func (s *FileStore) flush(coll string) error {
	docs := make([]Doc, 0, len(s.data[coll]))
	for _, d := range s.data[coll] {
		docs = append(docs, d)
	}
	raw, err := json.MarshalIndent(docs, "", "  ")
	if err != nil {
		return err
	}
	tmp := filepath.Join(s.dir, coll+".json.tmp")
	if err := os.WriteFile(tmp, raw, 0o644); err != nil {
		return err
	}
	return os.Rename(tmp, filepath.Join(s.dir, coll+".json"))
}
