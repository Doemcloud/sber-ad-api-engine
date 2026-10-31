package store

// Хранение в PostgreSQL.
//
// Схема — migrations/*.sql по доменной модели ТЗ. Сервис по-прежнему работает
// с состоянием в памяти под общей блокировкой (так проще держать инварианты
// жизненного цикла), а каждая запись фиксируется в БД одной транзакцией:
// после перезапуска состояние читается из БД, а не из файла. Пустая БД при
// первом запуске заполняется из моков заказчика.

import (
	"database/sql"
	"embed"
	"encoding/json"
	"fmt"
	"sort"
	"strings"
	"time"

	"adcamp/internal/domain"

	"github.com/lib/pq"
)

//go:embed migrations/*.sql
var migrations embed.FS

type pgBackend struct {
	db         *sql.DB
	auditSaved int // сколько записей аудита уже в БД (аудит только дописывается)
}

// OpenDB подключается к БД (DATABASE_URL), применяет схему и загружает состояние;
// пустую БД заполняет из моков.
func OpenDB(mockDir, dsn string) (*Store, error) {
	db, err := sql.Open("postgres", dsn)
	if err != nil {
		return nil, err
	}
	for i := 0; ; i++ { // СУБД в docker-compose может подниматься дольше API
		if err = db.Ping(); err == nil {
			break
		}
		if i == 30 {
			return nil, fmt.Errorf("БД недоступна: %w", err)
		}
		time.Sleep(time.Second)
	}
	if err := migrate(db); err != nil {
		return nil, err
	}
	pg := &pgBackend{db: db}
	var n int
	if err := db.QueryRow(`SELECT count(*) FROM campaign`).Scan(&n); err != nil {
		return nil, err
	}
	st := &Store{pg: pg}
	if n == 0 {
		s, err := Seed(mockDir)
		if err != nil {
			return nil, err
		}
		st.S = s
		if err := pg.seedDicts(s); err != nil {
			return nil, fmt.Errorf("сид справочников: %w", err)
		}
		if err := pg.save(s); err != nil {
			return nil, fmt.Errorf("сид кампаний: %w", err)
		}
		return st, nil
	}
	s, err := pg.load()
	if err != nil {
		return nil, fmt.Errorf("загрузка из БД: %w", err)
	}
	st.S = s
	pg.auditSaved = len(s.Audit)
	return st, nil
}

func migrate(db *sql.DB) error {
	files, _ := migrations.ReadDir("migrations")
	sort.Slice(files, func(i, j int) bool { return files[i].Name() < files[j].Name() })
	for _, f := range files {
		raw, _ := migrations.ReadFile("migrations/" + f.Name())
		if _, err := db.Exec(string(raw)); err != nil {
			return fmt.Errorf("миграция %s: %w", f.Name(), err)
		}
	}
	return nil
}

func jsonb(v any) any {
	if v == nil {
		return nil
	}
	b, _ := json.Marshal(v)
	return string(b)
}

func nullStr(p *string) any {
	if p == nil {
		return nil
	}
	return *p
}

// seedDicts — справочники (только при первом заполнении; теги и места пишет save).
func (p *pgBackend) seedDicts(s *State) error {
	tx, err := p.db.Begin()
	if err != nil {
		return err
	}
	defer tx.Rollback()
	for _, t := range s.Topics {
		if _, err := tx.Exec(`INSERT INTO topic(value,label) VALUES ($1,$2) ON CONFLICT (value) DO UPDATE SET label=EXCLUDED.label`, t.Value, t.Label); err != nil {
			return err
		}
	}
	for _, c := range s.Channels {
		if _, err := tx.Exec(`INSERT INTO channel(id,code,description) VALUES ($1,$2,$3) ON CONFLICT (id) DO NOTHING`, c.ID, c.Code, c.Description); err != nil {
			return err
		}
	}
	for _, b := range s.BannerTypes {
		if _, err := tx.Exec(`INSERT INTO banner_type(id,code,description,preview_form,title_max_length,text_max_length,channels)
			VALUES ($1,$2,$3,$4,$5,$6,$7) ON CONFLICT (id) DO NOTHING`, b.ID, b.Code, b.Description, b.PreviewForm, b.TitleMaxLength, b.TextMaxLength, pq.Array(b.Channels)); err != nil {
			return err
		}
	}
	for _, t := range s.SegmentTypes {
		if _, err := tx.Exec(`INSERT INTO segment_type(code,name) VALUES ($1,$2) ON CONFLICT (code) DO NOTHING`, t.Code, t.Name); err != nil {
			return err
		}
	}
	for _, g := range s.Segments {
		if _, err := tx.Exec(`INSERT INTO segment(code,name,type,state,count) VALUES ($1,$2,$3,$4,$5) ON CONFLICT (code) DO NOTHING`, g.Code, g.Name, g.Type, g.State, g.Count); err != nil {
			return err
		}
	}
	return tx.Commit()
}

// save фиксирует изменяемую часть состояния одной транзакцией.
// Данных прототипа немного, поэтому кампании и дочерние сущности переписываются целиком,
// а аудит только дописывается.
func (p *pgBackend) save(s *State) error {
	tx, err := p.db.Begin()
	if err != nil {
		return err
	}
	defer tx.Rollback()
	ex := func(q string, args ...any) {
		if err == nil {
			_, err = tx.Exec(q, args...)
		}
	}
	ex(`DELETE FROM creative`)
	ex(`DELETE FROM content`)
	ex(`DELETE FROM banner`)
	ex(`DELETE FROM campaign_segment`)
	ex(`DELETE FROM campaign_place`)
	ex(`DELETE FROM campaign_tag`)
	ex(`DELETE FROM campaign`)
	for _, t := range s.Tags {
		ex(`INSERT INTO tag(id,name) VALUES ($1,$2) ON CONFLICT (id) DO UPDATE SET name=EXCLUDED.name`, t.ID, t.Name)
	}
	for _, pl := range s.Places {
		ex(`INSERT INTO place(id,code,description,default_banner,state) VALUES ($1,$2,$3,$4,$5)
			ON CONFLICT (id) DO UPDATE SET code=EXCLUDED.code, description=EXCLUDED.description, default_banner=EXCLUDED.default_banner, state=EXCLUDED.state`,
			pl.ID, pl.Code, pl.Description, nullStr(pl.DefaultBanner), pl.State)
	}
	ids := make([]int64, 0, len(s.Campaigns))
	for id := range s.Campaigns {
		ids = append(ids, id)
	}
	sort.Slice(ids, func(i, j int) bool { return ids[i] < ids[j] })
	for _, id := range ids {
		c := s.Campaigns[id]
		ex(`INSERT INTO campaign(id,name,marketing_name,start_date,start_time,end_date,end_time,topic,keywords,audience_type,weight,initial_ctr,state,published,author,last_edit_author)
			VALUES ($1,$2,$3,$4,$5,$6,$7,$8,$9,$10,$11,$12,$13,$14,$15,$16)`,
			c.ID, c.Name, nullStr(c.MarketingName), c.StartDate, c.StartTime, nullStr(c.EndDate), nullStr(c.EndTime), c.Topic, nullStr(c.Keywords),
			c.AudienceType, c.Weight, c.InitialCtr, c.State, c.Published, c.Author, c.LastEditAuthor)
		for i, t := range c.Tags {
			ex(`INSERT INTO campaign_tag(campaign_id,tag_id,pos) VALUES ($1,$2,$3)`, c.ID, t, i)
		}
		for i, pl := range c.Places {
			ex(`INSERT INTO campaign_place(campaign_id,place_id,pos) VALUES ($1,$2,$3)`, c.ID, pl, i)
		}
		for i, g := range c.Segments.Included {
			ex(`INSERT INTO campaign_segment(campaign_id,segment_code,kind,pos) VALUES ($1,$2,'INCLUDED',$3)`, c.ID, g, i)
		}
		for i, g := range c.Segments.Excluded {
			ex(`INSERT INTO campaign_segment(campaign_id,segment_code,kind,pos) VALUES ($1,$2,'EXCLUDED',$3)`, c.ID, g, i)
		}
	}
	for _, b := range sortedVals(s.Banners) {
		ex(`INSERT INTO banner(id,campaign_id,name,banner_type_id,content) VALUES ($1,$2,$3,$4,$5)`, b.ID, b.CampaignID, b.Name, b.BannerTypeID, jsonb(b.Content))
	}
	for _, x := range sortedVals(s.Contents) {
		ex(`INSERT INTO content(id,campaign_id,name,content_type,content) VALUES ($1,$2,$3,$4,$5)`, x.ID, x.CampaignID, x.Name, x.ContentType, jsonb(x.Content))
	}
	for _, x := range sortedVals(s.Creatives) {
		var cid any
		if x.ContentID != nil {
			cid = *x.ContentID
		}
		ex(`INSERT INTO creative(id,campaign_id,name,banner_id,content_id,channel_code) VALUES ($1,$2,$3,$4,$5,$6)`, x.ID, x.CampaignID, x.Name, x.BannerID, cid, x.ChannelCode)
	}
	for _, a := range s.Audit[min(p.auditSaved, len(s.Audit)):] {
		var changes any
		if a.Changes != nil {
			changes = jsonb(a.Changes)
		}
		ex(`INSERT INTO lifecycle_transitions(id,campaign_id,entity,entity_id,action,changes,at,actor,comment) VALUES ($1,$2,$3,$4,$5,$6,$7,$8,$9)
			ON CONFLICT (id) DO NOTHING`, a.ID, a.CampaignID, a.Entity, a.EntityID, a.Action, changes, a.At, a.Actor, nullStr(a.Comment))
	}
	for k, v := range s.NextID {
		ex(`INSERT INTO id_sequence(kind,next_id) VALUES ($1,$2) ON CONFLICT (kind) DO UPDATE SET next_id=EXCLUDED.next_id`, k, v)
	}
	if err != nil {
		return err
	}
	if err := tx.Commit(); err != nil {
		return err
	}
	p.auditSaved = len(s.Audit)
	return nil
}

func sortedVals[T interface {
	*domain.Banner | *domain.Content | *domain.Creative
}](m map[int64]T) []T {
	ids := make([]int64, 0, len(m))
	for id := range m {
		ids = append(ids, id)
	}
	sort.Slice(ids, func(i, j int) bool { return ids[i] < ids[j] })
	out := make([]T, 0, len(ids))
	for _, id := range ids {
		out = append(out, m[id])
	}
	return out
}

func dateStr(t sql.NullTime) *string {
	if !t.Valid {
		return nil
	}
	s := t.Time.Format("2006-01-02")
	return &s
}

func strPtr(v sql.NullString) *string {
	if !v.Valid {
		return nil
	}
	s := v.String
	return &s
}

// load читает всё состояние из БД.
func (p *pgBackend) load() (*State, error) {
	s := &State{Campaigns: map[int64]*domain.Campaign{}, Banners: map[int64]*domain.Banner{}, Contents: map[int64]*domain.Content{},
		Creatives: map[int64]*domain.Creative{}, NextID: map[string]int64{}, Audit: []domain.AuditEntry{}}
	q := func(query string, scan func(*sql.Rows) error) error {
		rows, err := p.db.Query(query)
		if err != nil {
			return err
		}
		defer rows.Close()
		for rows.Next() {
			if err := scan(rows); err != nil {
				return err
			}
		}
		return rows.Err()
	}
	steps := []error{
		q(`SELECT value,label FROM topic ORDER BY value`, func(r *sql.Rows) error {
			var t domain.Topic
			err := r.Scan(&t.Value, &t.Label)
			s.Topics = append(s.Topics, t)
			return err
		}),
		q(`SELECT id,name FROM tag ORDER BY id`, func(r *sql.Rows) error {
			var t domain.Tag
			err := r.Scan(&t.ID, &t.Name)
			s.Tags = append(s.Tags, t)
			return err
		}),
		q(`SELECT id,code,description FROM channel ORDER BY id`, func(r *sql.Rows) error {
			var c domain.Channel
			err := r.Scan(&c.ID, &c.Code, &c.Description)
			s.Channels = append(s.Channels, c)
			return err
		}),
		q(`SELECT id,code,description,preview_form,title_max_length,text_max_length,channels FROM banner_type ORDER BY id`, func(r *sql.Rows) error {
			var b domain.BannerType
			err := r.Scan(&b.ID, &b.Code, &b.Description, &b.PreviewForm, &b.TitleMaxLength, &b.TextMaxLength, pq.Array(&b.Channels))
			s.BannerTypes = append(s.BannerTypes, b)
			return err
		}),
		q(`SELECT code,name FROM segment_type ORDER BY code`, func(r *sql.Rows) error {
			var t domain.SegmentType
			err := r.Scan(&t.Code, &t.Name)
			s.SegmentTypes = append(s.SegmentTypes, t)
			return err
		}),
		q(`SELECT code,name,type,state,count FROM segment ORDER BY code`, func(r *sql.Rows) error {
			var g domain.Segment
			err := r.Scan(&g.Code, &g.Name, &g.Type, &g.State, &g.Count)
			s.Segments = append(s.Segments, g)
			return err
		}),
		q(`SELECT id,code,description,default_banner,state FROM place ORDER BY id`, func(r *sql.Rows) error {
			var pl domain.Place
			var db sql.NullString
			err := r.Scan(&pl.ID, &pl.Code, &pl.Description, &db, &pl.State)
			pl.DefaultBanner = strPtr(db)
			s.Places = append(s.Places, pl)
			return err
		}),
		q(`SELECT id,name,marketing_name,start_date,start_time,end_date,end_time,topic,keywords,audience_type,weight,initial_ctr,state,published,author,last_edit_author FROM campaign`, func(r *sql.Rows) error {
			c := &domain.Campaign{Tags: []int64{}, Places: []int64{}, Segments: domain.Segments{Included: []string{}, Excluded: []string{}}}
			var mn, et, kw sql.NullString
			var sd time.Time
			var ed sql.NullTime
			err := r.Scan(&c.ID, &c.Name, &mn, &sd, &c.StartTime, &ed, &et, &c.Topic, &kw, &c.AudienceType, &c.Weight, &c.InitialCtr, &c.State, &c.Published, &c.Author, &c.LastEditAuthor)
			c.MarketingName, c.EndTime, c.Keywords, c.EndDate = strPtr(mn), strPtr(et), strPtr(kw), dateStr(ed)
			c.StartDate = sd.Format("2006-01-02")
			s.Campaigns[c.ID] = c
			return err
		}),
	}
	for _, e := range steps {
		if e != nil {
			return nil, e
		}
	}
	link := []error{
		q(`SELECT campaign_id,tag_id FROM campaign_tag ORDER BY campaign_id,pos`, func(r *sql.Rows) error {
			var c, t int64
			err := r.Scan(&c, &t)
			if x := s.Campaigns[c]; x != nil {
				x.Tags = append(x.Tags, t)
			}
			return err
		}),
		q(`SELECT campaign_id,place_id FROM campaign_place ORDER BY campaign_id,pos`, func(r *sql.Rows) error {
			var c, pl int64
			err := r.Scan(&c, &pl)
			if x := s.Campaigns[c]; x != nil {
				x.Places = append(x.Places, pl)
			}
			return err
		}),
		q(`SELECT campaign_id,segment_code,kind FROM campaign_segment ORDER BY campaign_id,kind,pos`, func(r *sql.Rows) error {
			var c int64
			var g, kind string
			err := r.Scan(&c, &g, &kind)
			if x := s.Campaigns[c]; x != nil {
				if kind == "INCLUDED" {
					x.Segments.Included = append(x.Segments.Included, g)
				} else {
					x.Segments.Excluded = append(x.Segments.Excluded, g)
				}
			}
			return err
		}),
		q(`SELECT id,campaign_id,name,banner_type_id,content FROM banner`, func(r *sql.Rows) error {
			b := &domain.Banner{}
			var raw []byte
			err := r.Scan(&b.ID, &b.CampaignID, &b.Name, &b.BannerTypeID, &raw)
			_ = json.Unmarshal(raw, &b.Content)
			s.Banners[b.ID] = b
			return err
		}),
		q(`SELECT id,campaign_id,name,content_type,content FROM content`, func(r *sql.Rows) error {
			x := &domain.Content{}
			var raw []byte
			err := r.Scan(&x.ID, &x.CampaignID, &x.Name, &x.ContentType, &raw)
			_ = json.Unmarshal(raw, &x.Content)
			s.Contents[x.ID] = x
			return err
		}),
		q(`SELECT id,campaign_id,name,banner_id,content_id,channel_code FROM creative`, func(r *sql.Rows) error {
			x := &domain.Creative{}
			var cid sql.NullInt64
			err := r.Scan(&x.ID, &x.CampaignID, &x.Name, &x.BannerID, &cid, &x.ChannelCode)
			if cid.Valid {
				v := cid.Int64
				x.ContentID = &v
			}
			s.Creatives[x.ID] = x
			return err
		}),
		q(`SELECT id,campaign_id,entity,entity_id,action,changes,at,actor,comment FROM lifecycle_transitions ORDER BY id`, func(r *sql.Rows) error {
			var a domain.AuditEntry
			var raw []byte
			var at time.Time
			var cm sql.NullString
			err := r.Scan(&a.ID, &a.CampaignID, &a.Entity, &a.EntityID, &a.Action, &raw, &at, &a.Actor, &cm)
			if len(raw) > 0 && string(raw) != "null" {
				_ = json.Unmarshal(raw, &a.Changes)
			}
			a.At, a.Comment = at.Format("2006-01-02T15:04:05"), strPtr(cm)
			s.Audit = append(s.Audit, a)
			return err
		}),
		q(`SELECT kind,next_id FROM id_sequence`, func(r *sql.Rows) error {
			var k string
			var v int64
			err := r.Scan(&k, &v)
			s.NextID[k] = v
			return err
		}),
	}
	for _, e := range link {
		if e != nil {
			return nil, e
		}
	}
	return s, nil
}

// DescribeDSN — адрес БД без пароля для лога.
func DescribeDSN(dsn string) string {
	if i := strings.Index(dsn, "@"); i > 0 {
		if j := strings.Index(dsn, "://"); j > 0 && j < i {
			return dsn[:j+3] + "***" + dsn[i:]
		}
	}
	return dsn
}

// DB — соединение с PostgreSQL (nil в режиме без СУБД); нужно хранилищу изображений.
func (s *Store) DB() *sql.DB {
	if s.pg == nil {
		return nil
	}
	return s.pg.db
}
