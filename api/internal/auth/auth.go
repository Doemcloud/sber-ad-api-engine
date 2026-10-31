// Package auth — вход в интерфейс по логину и паролю и подписанные токены.
//
// Учётки лежат в MOCK_DIR/users.json (пароль — SHA-256). Токен — base64url(JSON)
// + "." + HMAC-SHA256: проверяется без хранилища, живёт AUTH_TTL (по умолчанию 12 ч).
// Из валидного токена API берёт пользователя и роль, поэтому подменить роль
// заголовком X-Role из браузера нельзя.
package auth

import (
	"crypto/hmac"
	"crypto/sha256"
	"crypto/subtle"
	"encoding/base64"
	"encoding/hex"
	"encoding/json"
	"errors"
	"os"
	"strings"
	"time"
)

type User struct {
	Login          string `json:"login"`
	PasswordSHA256 string `json:"passwordSha256,omitempty"`
	User           string `json:"user"`
	Role           string `json:"role"`
	Name           string `json:"name"`
	Title          string `json:"title"`
}

// Public — то, что уходит клиенту (без хеша пароля).
func (u User) Public() User { u.PasswordSHA256 = ""; return u }

type claims struct {
	Login string `json:"l"`
	User  string `json:"u"`
	Role  string `json:"r"`
	Exp   int64  `json:"e"`
}

type Auth struct {
	users  map[string]User
	secret []byte
	ttl    time.Duration
}

var (
	ErrBadCredentials = errors.New("неверный логин или пароль")
	ErrBadToken       = errors.New("сессия недействительна — войдите заново")
)

// Load читает users.json. Нет файла — вход отключён (пустой список), API работает как раньше.
func Load(path, secret string, ttl time.Duration) (*Auth, error) {
	a := &Auth{users: map[string]User{}, secret: []byte(secret), ttl: ttl}
	raw, err := os.ReadFile(path)
	if errors.Is(err, os.ErrNotExist) {
		return a, nil
	}
	if err != nil {
		return nil, err
	}
	var f struct {
		Users []User `json:"users"`
	}
	if err := json.Unmarshal(raw, &f); err != nil {
		return nil, err
	}
	for _, u := range f.Users {
		a.users[strings.ToLower(u.Login)] = u
	}
	return a, nil
}

func (a *Auth) Login(login, password string) (string, User, time.Time, error) {
	u, ok := a.users[strings.ToLower(strings.TrimSpace(login))]
	sum := sha256.Sum256([]byte(password))
	if !ok || subtle.ConstantTimeCompare([]byte(hex.EncodeToString(sum[:])), []byte(strings.ToLower(u.PasswordSHA256))) != 1 {
		return "", User{}, time.Time{}, ErrBadCredentials
	}
	exp := time.Now().Add(a.ttl)
	body, _ := json.Marshal(claims{Login: u.Login, User: u.User, Role: u.Role, Exp: exp.Unix()})
	p := base64.RawURLEncoding.EncodeToString(body)
	return p + "." + a.sign(p), u.Public(), exp, nil
}

// Verify возвращает пользователя из токена.
func (a *Auth) Verify(token string) (User, error) {
	p, sig, ok := strings.Cut(token, ".")
	if !ok || !hmac.Equal([]byte(sig), []byte(a.sign(p))) {
		return User{}, ErrBadToken
	}
	raw, err := base64.RawURLEncoding.DecodeString(p)
	if err != nil {
		return User{}, ErrBadToken
	}
	var c claims
	if json.Unmarshal(raw, &c) != nil || time.Now().Unix() > c.Exp {
		return User{}, ErrBadToken
	}
	if u, ok := a.users[strings.ToLower(c.Login)]; ok {
		return u.Public(), nil
	}
	return User{Login: c.Login, User: c.User, Role: c.Role}, nil
}

func (a *Auth) sign(p string) string {
	m := hmac.New(sha256.New, a.secret)
	m.Write([]byte(p))
	return base64.RawURLEncoding.EncodeToString(m.Sum(nil))
}
