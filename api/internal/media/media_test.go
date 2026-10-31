package media

import "testing"

func TestDirRoundTripAndGuards(t *testing.T) {
	d := Dir{Path: t.TempDir()}
	jpeg := append([]byte{0xFF, 0xD8, 0xFF, 0xE0, 0, 0x10, 'J', 'F', 'I', 'F', 0}, make([]byte, 64)...)
	id, err := d.Put(Image{Data: jpeg, Prompt: "тест", Author: "ivanov.p"})
	if err != nil || !ValidID(id) {
		t.Fatalf("put: %q %v", id, err)
	}
	img, err := d.Get(id)
	if err != nil || img.Mime != "image/jpeg" || img.Author != "ivanov.p" || len(img.Data) != len(jpeg) {
		t.Fatalf("get: %+v %v", img, err)
	}
	if _, err := d.Put(Image{Data: []byte("<html>")}); err != ErrType {
		t.Fatalf("html: %v", err)
	}
	for _, bad := range []string{"../x", "ABC", id + "/../x", ""} {
		if _, err := d.Get(bad); err != ErrNotFound {
			t.Fatalf("id %q: %v", bad, err)
		}
	}
}
