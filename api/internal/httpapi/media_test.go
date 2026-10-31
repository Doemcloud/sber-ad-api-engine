package httpapi

import (
	"bytes"
	"encoding/json"
	"image"
	"image/color"
	"image/png"
	"net/http/httptest"
	"path/filepath"
	"strings"
	"testing"
	"time"

	"adcamp/internal/auth"
	"adcamp/internal/domain"
	"adcamp/internal/media"
	"adcamp/internal/service"
	"adcamp/internal/store"
)

func pngBytes(t *testing.T) []byte {
	t.Helper()
	img := image.NewRGBA(image.Rect(0, 0, 4, 4))
	img.Set(1, 1, color.RGBA{0, 138, 69, 255})
	var b bytes.Buffer
	if err := png.Encode(&b, img); err != nil {
		t.Fatal(err)
	}
	return b.Bytes()
}

func TestMediaUploadServeAndUseInBanner(t *testing.T) {
	if err := domain.LoadCatalog(filepath.Join(mockDir, "validation_rules.json")); err != nil {
		t.Fatal(err)
	}
	st, err := store.Open(mockDir, "")
	if err != nil {
		t.Fatal(err)
	}
	au, _ := auth.Load(filepath.Join(mockDir, "users.json"), "test-secret", time.Hour)
	base := "http://localhost:8080"
	domain.MediaBase = base
	defer func() { domain.MediaBase = "" }()
	h := (&API{S: service.New(st), Auth: au, Required: true, ServiceKey: "svc",
		Media: media.Dir{Path: t.TempDir()}, PublicURL: base}).Routes()
	manager, moder := login(t, h, "client", "client"), login(t, h, "moder", "moder")

	upload := func(tok string, body []byte) (int, map[string]any) {
		r := httptest.NewRequest("POST", "/media?prompt=осенний+парк", bytes.NewReader(body))
		if tok != "" {
			r.Header.Set("Authorization", "Bearer "+tok)
		}
		w := httptest.NewRecorder()
		h.ServeHTTP(w, r)
		var out map[string]any
		_ = json.Unmarshal(w.Body.Bytes(), &out)
		return w.Code, out
	}
	if code, _ := upload("", pngBytes(t)); code != 401 {
		t.Fatalf("без входа: ждали 401, получили %d", code)
	}
	if code, _ := upload(moder, pngBytes(t)); code != 403 {
		t.Fatalf("модератор: ждали 403, получили %d", code)
	}
	if code, _ := upload(manager, []byte("<svg onload=alert(1)>")); code != 415 {
		t.Fatalf("не картинка: ждали 415, получили %d", code)
	}
	code, out := upload(manager, pngBytes(t))
	if code != 201 {
		t.Fatalf("загрузка: %d %v", code, out)
	}
	url := out["url"].(string)
	if !strings.HasPrefix(url, base+"/media/") {
		t.Fatalf("ссылка %q", url)
	}

	// картинка отдаётся без входа, с типом по содержимому
	w := httptest.NewRecorder()
	h.ServeHTTP(w, httptest.NewRequest("GET", strings.TrimPrefix(url, base), nil))
	if w.Code != 200 || w.Header().Get("Content-Type") != "image/png" || !strings.Contains(w.Header().Get("Cache-Control"), "immutable") {
		t.Fatalf("выдача: %d %v", w.Code, w.Header())
	}
	w = httptest.NewRecorder()
	h.ServeHTTP(w, httptest.NewRequest("GET", "/media/../../etc/passwd", nil))
	if w.Code == 200 {
		t.Fatal("обход пути не должен отдавать файл")
	}

	// собственная ссылка принимается в баннере даже без https
	body := `{"name":"С картинкой","bannerTypeId":2,"content":{"title":"Кэшбэк","text":"До 10%","image":{"url":"` + url + `"},"actionType":"default"}}`
	if code, out := call(h, "POST", "/campaigns/101/banners", body, map[string]string{"Authorization": "Bearer " + manager}); code != 201 {
		t.Fatalf("баннер с изображением: %d %v", code, out)
	}
	bad := strings.Replace(body, url, "http://evil.example/x.png", 1)
	if code, _ := call(h, "POST", "/campaigns/101/banners", bad, map[string]string{"Authorization": "Bearer " + manager}); code != 400 {
		t.Fatalf("чужая http-ссылка: ждали 400, получили %d", code)
	}
}
