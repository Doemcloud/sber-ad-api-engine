package service

// Статистика кампании: охват, показы, клики, CTR и разбивки аудитории.
//
// В моках заказчика фактической статистики нет (её считает система показов, а не сервис
// кампаний), поэтому для демо цифры моделируются — детерминированно из самой кампании:
// размера и состава аудитории (сегменты и их число клиентов), мест размещения, платформ
// креативов и периода показа. Одна и та же кампания всегда даёт одни и те же цифры.
// Запущенные и остановленные — «факт» за прошедшие дни, остальные — «прогноз» на весь период.

import (
	"fmt"
	"hash/fnv"
	"math"
	"sort"
	"strings"
	"time"

	"adcamp/internal/domain"
)

type Share struct {
	Key   string  `json:"key"`
	Label string  `json:"label"`
	Share float64 `json:"share"` // доля 0..1
	Count int64   `json:"count"` // клиентов из охвата
}

type DayStat struct {
	Date        string `json:"date"`
	Impressions int64  `json:"impressions"`
	Clicks      int64  `json:"clicks"`
	Reach       int64  `json:"reach"`
}

type Stats struct {
	CampaignID   int64     `json:"campaignId"`
	Mode         string    `json:"mode"` // fact | forecast
	From         string    `json:"from"`
	To           string    `json:"to"`
	Days         int       `json:"days"`
	AudienceSize int64     `json:"audienceSize"` // сколько клиентов подходит под таргетинг
	Reach        int64     `json:"reach"`        // уникальные клиенты, увидевшие рекламу
	Impressions  int64     `json:"impressions"`
	Clicks       int64     `json:"clicks"`
	CTR          float64   `json:"ctr"` // %
	Frequency    float64   `json:"frequency"`
	Conversions  int64     `json:"conversions"` // целевые действия на промо-экране
	Daily        []DayStat `json:"daily"`
	Age          []Share   `json:"age"`
	Gender       []Share   `json:"gender"`
	Cities       []Share   `json:"cities"`
	Platforms    []Share   `json:"platforms"`
	Places       []Share   `json:"places"`
	Note         string    `json:"note"`
}

type rng struct{ s uint64 }

func newRng(seed string) *rng {
	h := fnv.New64a()
	h.Write([]byte(seed))
	return &rng{h.Sum64() | 1}
}

// f — псевдослучайное 0..1 (xorshift64*), воспроизводимое для одного seed.
func (r *rng) f() float64 {
	r.s ^= r.s >> 12
	r.s ^= r.s << 25
	r.s ^= r.s >> 27
	return float64((r.s*2685821657736338717)>>11) / float64(1<<53)
}
func (r *rng) between(a, b float64) float64 { return a + (b-a)*r.f() }

const appAudience = 42_000_000 // активная месячная аудитория приложения в демо

var (
	ageBuckets    = []struct{ code, label string }{{"AGE_18_25", "18–25"}, {"AGE_26_45", "26–45"}, {"AGE_46_60", "46–60"}, {"AGE_60_PLUS", "60+"}}
	genderBuckets = []struct{ code, label string }{{"FEMALE", "Женщины"}, {"MALE", "Мужчины"}}
	cityBuckets   = []string{"CITY_MSK", "CITY_SPB", "CITY_NVS", "CITY_EKB", "CITY_KZN", "CITY_SLD"}
	platformShare = map[string]float64{"iOS": 0.38, "ANDROID": 0.52, "WEB": 0.10}
	platformLabel = map[string]string{"iOS": "iOS", "ANDROID": "Android", "WEB": "Веб-версия"}
)

func (s *Service) Stats(id int64) (*Stats, *domain.APIError) {
	det, e := s.Get(id)
	if e != nil {
		return nil, e
	}
	s.st.Lock()
	segs := map[string]domain.Segment{}
	for _, x := range s.st.S.Segments {
		segs[x.Code] = x
	}
	places := map[int64]string{}
	for _, p := range s.st.S.Places {
		if p.State == "ACTIVE" { // в отключённых местах показов нет
			places[p.ID] = p.Description
		}
	}
	s.st.Unlock()

	r := newRng(fmt.Sprintf("campaign-%d-%s", det.ID, det.Name))
	inc := map[string]bool{}
	for _, c := range det.Segments.Included {
		inc[c] = true
	}

	// --- размер аудитории ---
	audience := float64(appAudience)
	if det.AudienceType == "SEGMENTED" {
		var counts []float64
		for _, c := range det.Segments.Included {
			counts = append(counts, float64(segs[c].Count))
		}
		sort.Sort(sort.Reverse(sort.Float64Slice(counts)))
		audience = 0
		for i, n := range counts { // сегменты объединяются по ИЛИ: пересечения не считаем дважды
			audience += n * math.Pow(0.62, float64(i))
		}
		audience = math.Min(audience, appAudience)
	}
	for _, c := range det.Segments.Excluded {
		audience -= float64(segs[c].Count) * audience / appAudience
	}
	audience = math.Max(audience, 0)

	// --- период ---
	start, _ := time.Parse("2006-01-02", det.StartDate)
	end := start.AddDate(0, 0, 60)
	if det.EndDate != nil {
		if t, err := time.Parse("2006-01-02", *det.EndDate); err == nil {
			end = t
		}
	}
	today := s.Now().Truncate(24 * time.Hour)
	mode := "forecast"
	to := end
	if det.Published || det.State == domain.StateStopped {
		mode = "fact"
		if today.Before(to) {
			to = today
		}
		if det.State == domain.StateStopped && to.After(start.AddDate(0, 0, 21)) {
			to = start.AddDate(0, 0, 21) // остановили примерно через три недели
		}
	}
	days := int(to.Sub(start).Hours()/24) + 1
	if days < 1 {
		days = 1
	}
	if days > 120 {
		days = 120
	}

	// --- воронка ---
	active := []int64{}
	for _, id := range det.Places {
		if _, ok := places[id]; ok {
			active = append(active, id)
		}
	}
	nPlaces := math.Max(float64(len(active)), 1)
	daily := r.between(0.012, 0.03) * (1 + 0.35*(nPlaces-1))
	reach := audience * (1 - math.Exp(-daily*float64(days)))
	freq := math.Min(1.3+0.06*float64(days)+r.between(0, 0.4), 4.8)
	impressions := reach * freq
	ctr := r.between(1.4, 4.2) // %
	for _, b := range det.Banners {
		if b.BannerTypeID == 1 {
			ctr += 0.8 // сторис кликают чаще
			break
		}
	}
	clicks := impressions * ctr / 100
	conv := clicks * r.between(0.05, 0.13)
	if len(det.Contents) == 0 {
		conv *= 0.4 // без промо-экрана меньше целевых действий
	}

	st := &Stats{CampaignID: det.ID, Mode: mode, From: start.Format("2006-01-02"), To: start.AddDate(0, 0, days-1).Format("2006-01-02"), Days: days,
		AudienceSize: round(audience), Reach: round(reach), Impressions: round(impressions), Clicks: round(clicks),
		CTR: math.Round(ctr*100) / 100, Frequency: math.Round(freq*10) / 10, Conversions: round(conv)}

	// --- по дням (до 30 последних) ---
	shown := days
	if shown > 30 {
		shown = 30
	}
	first := days - shown // факт — последние дни, прогноз — первые
	if mode == "forecast" {
		first = 0
	}
	weights := make([]float64, shown)
	var wsum float64
	for i := range weights {
		d := start.AddDate(0, 0, first+i)
		w := 1.0 + 0.12*math.Sin(float64(i)/2.3) + r.between(-0.08, 0.08)
		if wd := d.Weekday(); wd == time.Saturday || wd == time.Sunday {
			w *= 0.82
		}
		if first+i < 3 {
			w *= 1.25 // на старте кампания показывается активнее
		}
		weights[i], wsum = w, wsum+w
	}
	part := float64(shown) / float64(days)
	for i, w := range weights {
		k := w / wsum * part
		st.Daily = append(st.Daily, DayStat{Date: start.AddDate(0, 0, first+i).Format("2006-01-02"),
			Impressions: round(impressions * k), Clicks: round(clicks * k * r.between(0.9, 1.1)), Reach: round(reach * k / freq * 1.6)})
	}

	// --- разбивки ---
	focus := func(codes []string) map[string]bool {
		m := map[string]bool{}
		for _, c := range codes {
			if inc[c] {
				m[c] = true
			}
		}
		return m
	}
	var ageCodes, genderCodes []string
	for _, a := range ageBuckets {
		ageCodes = append(ageCodes, a.code)
	}
	for _, g := range genderBuckets {
		genderCodes = append(genderCodes, g.code)
	}
	fa, fg, fc := focus(ageCodes), focus(genderCodes), focus(cityBuckets)

	var age []Share
	for _, a := range ageBuckets {
		w := float64(segs[a.code].Count)
		if len(fa) > 0 && !fa[a.code] {
			w *= 0.05
		}
		age = append(age, Share{Key: a.code, Label: a.label, Share: w * r.between(0.9, 1.1)})
	}
	st.Age = normalize(age, st.Reach)

	var gender []Share
	for _, g := range genderBuckets {
		w := float64(segs[g.code].Count)
		if len(fg) > 0 && !fg[g.code] {
			w *= 0.07
		}
		gender = append(gender, Share{Key: g.code, Label: g.label, Share: w * r.between(0.95, 1.05)})
	}
	st.Gender = normalize(gender, st.Reach)

	var cities []Share
	var cityW float64
	for _, c := range cityBuckets {
		w := float64(segs[c].Count)
		if len(fc) > 0 && !fc[c] {
			w *= 0.04
		}
		cityW += w
		cities = append(cities, Share{Key: c, Label: segs[c].Name, Share: w * r.between(0.9, 1.1)})
	}
	other := float64(appAudience) - cityW
	if len(fc) > 0 {
		other = cityW * 0.08
	}
	cities = append(cities, Share{Key: "OTHER", Label: "Другие города", Share: math.Max(other, 0)})
	st.Cities = normalize(cities, st.Reach)

	chans := map[string]bool{}
	for _, c := range det.Creatives {
		chans[c.ChannelCode] = true
	}
	var plat []Share
	for _, k := range []string{"iOS", "ANDROID", "WEB"} {
		if len(chans) > 0 && !chans[k] {
			continue
		}
		plat = append(plat, Share{Key: k, Label: platformLabel[k], Share: platformShare[k] * r.between(0.9, 1.1)})
	}
	st.Platforms = normalize(plat, st.Impressions)

	var pl []Share
	for i, id := range active {
		pl = append(pl, Share{Key: fmt.Sprint(id), Label: places[id], Share: math.Pow(0.6, float64(i)) * r.between(0.85, 1.15)})
	}
	st.Places = normalize(pl, st.Impressions)

	if mode == "forecast" {
		st.Note = "Прогноз на весь период показа: кампания ещё не запущена. Оценка по размеру аудитории, местам размещения и платформам."
	} else {
		st.Note = "Демо-данные: в прототипе статистика моделируется по аудитории и размещению кампании, в продуктиве её отдаёт система показов."
	}
	return st, nil
}

func round(v float64) int64 { return int64(math.Round(v)) }

// normalize: доли в сумме 1, количество — от total; сортировка по убыванию (кроме возраста — он по порядку).
func normalize(xs []Share, total int64) []Share {
	var sum float64
	for _, x := range xs {
		sum += x.Share
	}
	if sum == 0 {
		return []Share{}
	}
	keepOrder := len(xs) > 0 && strings.HasPrefix(xs[0].Key, "AGE_")
	for i := range xs {
		xs[i].Share = math.Round(xs[i].Share/sum*1000) / 1000
		xs[i].Count = round(float64(total) * xs[i].Share)
	}
	if !keepOrder {
		sort.SliceStable(xs, func(i, j int) bool {
			if xs[i].Key == "OTHER" || xs[j].Key == "OTHER" {
				return xs[j].Key == "OTHER" && xs[i].Key != "OTHER"
			}
			return xs[i].Share > xs[j].Share
		})
	}
	return xs
}
