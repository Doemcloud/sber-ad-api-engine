// Package store — хранилище: рабочее состояние в памяти под общей блокировкой,
// постоянное хранение — Platform V Pangolin DB (pg.go, при заданном DATABASE_URL)
// или, для тестов и запуска без СУБД, снимок в JSON-файл. Сид — из mocks/.
package store

import (
	"encoding/json"
	"errors"
	"fmt"
	"os"
	"path/filepath"
	"sort"
	"sync"

	"adcamp/internal/domain"
)

type State struct {
	Topics       []domain.Topic       `json:"topics"`
	Tags         []domain.Tag         `json:"tags"`
	Channels     []domain.Channel     `json:"channels"`
	BannerTypes  []domain.BannerType  `json:"bannerTypes"`
	SegmentTypes []domain.SegmentType `json:"segmentTypes"`
	Segments     []domain.Segment     `json:"segments"`
	Places       []domain.Place       `json:"places"`

	Campaigns map[int64]*domain.Campaign `json:"campaigns"`
	Banners   map[int64]*domain.Banner   `json:"banners"`
	Contents  map[int64]*domain.Content  `json:"contents"`
	Creatives map[int64]*domain.Creative `json:"creatives"`
	Audit     []domain.AuditEntry        `json:"audit"`
	// Сегменты кампаний: в Campaign поле не сериализуется, поэтому храним отдельно.
	CampaignSegments map[int64]domain.Segments `json:"campaignSegments"`

	NextID map[string]int64 `json:"nextId"`
}

type Store struct {
	mu        sync.Mutex
	S         *State
	statePath string
	pg        *pgBackend // Pangolin DB; nil — режим без СУБД
}

// Lock/Unlock — сервис держит блокировку на всю операцию (проверка + запись).
func (s *Store) Lock()   { s.mu.Lock() }
func (s *Store) Unlock() { s.mu.Unlock() }

// Open загружает снимок statePath, а если его нет — сид из mockDir.
func Open(mockDir, statePath string) (*Store, error) {
	st := &Store{statePath: statePath}
	if statePath != "" {
		if raw, err := os.ReadFile(statePath); err == nil {
			var s State
			if err := json.Unmarshal(raw, &s); err != nil {
				return nil, fmt.Errorf("снимок %s: %w", statePath, err)
			}
			for id, c := range s.Campaigns {
				c.Segments = s.CampaignSegments[id]
				c.Segments.Included, c.Segments.Excluded = nz(c.Segments.Included), nz(c.Segments.Excluded)
			}
			st.S = &s
			return st, nil
		}
	}
	s, err := Seed(mockDir)
	if err != nil {
		return nil, err
	}
	st.S = s
	return st, nil
}

func read(dir, name string, v any) error {
	raw, err := os.ReadFile(filepath.Join(dir, name))
	if err != nil {
		return err
	}
	if err := json.Unmarshal(raw, v); err != nil {
		return fmt.Errorf("%s: %w", name, err)
	}
	return nil
}

// Seed собирает состояние из файлов моков заказчика (mock-data.md).
func Seed(dir string) (*State, error) {
	s := &State{
		Campaigns: map[int64]*domain.Campaign{},
		Banners:   map[int64]*domain.Banner{},
		Contents:  map[int64]*domain.Content{},
		Creatives: map[int64]*domain.Creative{},
		NextID:    map[string]int64{},
	}
	for name, v := range map[string]any{
		"topics.json": &s.Topics, "tags.json": &s.Tags, "channels.json": &s.Channels,
		"banner_types.json": &s.BannerTypes, "segment_types.json": &s.SegmentTypes,
		"segments.json": &s.Segments, "places.json": &s.Places,
	} {
		if err := read(dir, name, v); err != nil {
			return nil, err
		}
	}
	var camps []*domain.Campaign
	if err := read(dir, "campaigns.json", &camps); err != nil {
		return nil, err
	}
	for _, c := range camps {
		if c.Tags == nil {
			c.Tags = []int64{}
		}
		c.Places = []int64{}
		c.Segments = domain.Segments{Included: []string{}, Excluded: []string{}}
		s.Campaigns[c.ID] = c
	}
	var places []struct {
		CampaignID int64   `json:"campaignId"`
		PlaceIDs   []int64 `json:"placeIds"`
	}
	if err := read(dir, "campaign_places.json", &places); err == nil {
		for _, p := range places {
			if c := s.Campaigns[p.CampaignID]; c != nil {
				c.Places = p.PlaceIDs
			}
		}
	}
	var segs []struct {
		CampaignID int64    `json:"campaignId"`
		Included   []string `json:"included"`
		Excluded   []string `json:"excluded"`
	}
	if err := read(dir, "campaign_segments.json", &segs); err == nil {
		for _, g := range segs {
			if c := s.Campaigns[g.CampaignID]; c != nil {
				c.Segments = domain.Segments{Included: nz(g.Included), Excluded: nz(g.Excluded)}
			}
		}
	}
	var banners []*domain.Banner
	_ = read(dir, "campaign_banners.json", &banners)
	for _, b := range banners {
		s.Banners[b.ID] = b
	}
	var contents []*domain.Content
	_ = read(dir, "campaign_contents.json", &contents)
	for _, c := range contents {
		s.Contents[c.ID] = c
	}
	var creatives []*domain.Creative
	_ = read(dir, "campaign_creatives.json", &creatives)
	for _, c := range creatives {
		s.Creatives[c.ID] = c
	}
	_ = read(dir, "lifecycle_transitions.json", &s.Audit)

	s.NextID["campaign"] = maxKey(s.Campaigns, 100) + 1
	s.NextID["banner"] = maxKey(s.Banners, 200) + 1
	s.NextID["content"] = maxKey(s.Contents, 300) + 1
	s.NextID["creative"] = maxKey(s.Creatives, 400) + 1
	s.NextID["audit"] = int64(len(s.Audit)) + 1
	var maxPlace, maxTag int64
	for _, p := range s.Places {
		maxPlace = max(maxPlace, p.ID)
	}
	for _, t := range s.Tags {
		maxTag = max(maxTag, t.ID)
	}
	s.NextID["place"], s.NextID["tag"] = maxPlace+1, maxTag+1
	return s, nil
}

func nz(v []string) []string {
	if v == nil {
		return []string{}
	}
	return v
}

func maxKey[T any](m map[int64]T, floor int64) int64 {
	for k := range m {
		floor = max(floor, k)
	}
	return floor
}

// Next выдаёт новый id для вида сущности.
func (st *Store) Next(kind string) int64 {
	id := st.S.NextID[kind]
	if id == 0 {
		id = 1
	}
	st.S.NextID[kind] = id + 1
	return id
}

// Save фиксирует состояние: в Pangolin DB транзакцией, иначе снимком в файл (атомарно).
func (st *Store) Save() error {
	if st.pg != nil {
		return st.pg.save(st.S)
	}
	if st.statePath == "" {
		return nil
	}
	st.S.CampaignSegments = map[int64]domain.Segments{}
	for id, c := range st.S.Campaigns {
		st.S.CampaignSegments[id] = c.Segments
	}
	raw, err := json.MarshalIndent(st.S, "", " ")
	if err != nil {
		return err
	}
	if err := os.MkdirAll(filepath.Dir(st.statePath), 0o755); err != nil {
		return err
	}
	tmp := st.statePath + ".tmp"
	if err := os.WriteFile(tmp, raw, 0o644); err != nil {
		return err
	}
	return os.Rename(tmp, st.statePath)
}

// Dicts — справочники в виде индексов для валидации.
func (st *Store) Dicts() domain.Dicts {
	d := domain.Dicts{
		Topics: map[string]domain.Topic{}, Tags: map[int64]domain.Tag{}, Channels: map[string]domain.Channel{},
		BannerTypes: map[int64]domain.BannerType{}, Segments: map[string]domain.Segment{}, Places: map[int64]domain.Place{},
	}
	for _, t := range st.S.Topics {
		d.Topics[t.Value] = t
	}
	for _, t := range st.S.Tags {
		d.Tags[t.ID] = t
	}
	for _, c := range st.S.Channels {
		d.Channels[c.Code] = c
	}
	for _, b := range st.S.BannerTypes {
		d.BannerTypes[b.ID] = b
	}
	for _, s := range st.S.Segments {
		d.Segments[s.Code] = s
	}
	for _, p := range st.S.Places {
		d.Places[p.ID] = p
	}
	return d
}

var ErrNotFound = errors.New("not found")

// Details собирает CampaignDetailsDto.
func (st *Store) Details(id int64) (domain.CampaignDetails, error) {
	c, ok := st.S.Campaigns[id]
	if !ok {
		return domain.CampaignDetails{}, ErrNotFound
	}
	det := domain.CampaignDetails{Campaign: *c, Segments: c.Segments,
		Banners: []domain.Banner{}, Contents: []domain.Content{}, Creatives: []domain.Creative{}}
	for _, b := range st.S.Banners {
		if b.CampaignID == id {
			det.Banners = append(det.Banners, *b)
		}
	}
	for _, x := range st.S.Contents {
		if x.CampaignID == id {
			det.Contents = append(det.Contents, *x)
		}
	}
	for _, x := range st.S.Creatives {
		if x.CampaignID == id {
			det.Creatives = append(det.Creatives, *x)
		}
	}
	sort.Slice(det.Banners, func(i, j int) bool { return det.Banners[i].ID < det.Banners[j].ID })
	sort.Slice(det.Contents, func(i, j int) bool { return det.Contents[i].ID < det.Contents[j].ID })
	sort.Slice(det.Creatives, func(i, j int) bool { return det.Creatives[i].ID < det.Creatives[j].ID })
	return det, nil
}

func (st *Store) CampaignList() []*domain.Campaign {
	out := make([]*domain.Campaign, 0, len(st.S.Campaigns))
	for _, c := range st.S.Campaigns {
		out = append(out, c)
	}
	sort.Slice(out, func(i, j int) bool { return out[i].ID < out[j].ID })
	return out
}
