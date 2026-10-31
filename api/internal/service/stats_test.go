package service

import (
	"math"
	"testing"
	"time"
)

func TestStats(t *testing.T) {
	s := newSvc(t)
	s.Now = func() time.Time { return time.Date(2026, 10, 31, 12, 0, 0, 0, time.UTC) }

	live, e := s.Stats(102, "") // запущена — факт
	if e != nil {
		t.Fatal(e)
	}
	again, _ := s.Stats(102, "")
	if live.Mode != "fact" || live.Reach != again.Reach || live.Impressions == 0 {
		t.Fatalf("факт должен быть воспроизводимым: %+v", live)
	}
	if live.Reach > live.AudienceSize || live.Clicks > live.Impressions {
		t.Fatalf("воронка нарушена: %+v", live)
	}
	for name, xs := range map[string][]Share{"age": live.Age, "gender": live.Gender, "cities": live.Cities, "platforms": live.Platforms} {
		var sum float64
		for _, x := range xs {
			sum += x.Share
		}
		if math.Abs(sum-1) > 0.01 {
			t.Fatalf("%s: доли в сумме %.3f", name, sum)
		}
	}

	// периоды: день — по часам, неделя ⊂ месяц ⊂ весь период
	d, _ := s.Stats(102, "day")
	w, _ := s.Stats(102, "week")
	all, _ := s.Stats(102, "all")
	if d.Granularity != "hour" || len(d.Daily) != 24 || w.Days != 7 || len(w.Daily) != 7 {
		t.Fatalf("периоды: день %s/%d, неделя %d/%d", d.Granularity, len(d.Daily), w.Days, len(w.Daily))
	}
	if !(d.Impressions < w.Impressions && w.Impressions < all.Impressions) || w.Reach > all.Reach {
		t.Fatalf("окна не вложены: день %d, неделя %d, всего %d", d.Impressions, w.Impressions, all.Impressions)
	}

	draft, _ := s.Stats(101, "") // черновик — прогноз
	if draft.Mode != "forecast" {
		t.Fatalf("черновик: ждали прогноз, получили %s", draft.Mode)
	}

	nw, _ := s.Stats(104, "") // таргет 26–45: эта группа доминирует; отключённое место не показывается
	if nw.Age[1].Label != "26–45" || nw.Age[1].Share < 0.8 {
		t.Fatalf("возраст 104: %+v", nw.Age)
	}
	for _, p := range nw.Places {
		if p.Label == "" {
			t.Fatalf("в статистике место без названия (отключённое?): %+v", nw.Places)
		}
	}
}
