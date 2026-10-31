// Package service — бизнес-операции API кампаний: роли, жизненный цикл,
// валидации, аудит (task.md §2.3, §3, §4).
package service

import (
	"encoding/json"
	"fmt"
	"reflect"
	"slices"
	"strings"
	"time"

	"adcamp/internal/domain"
	"adcamp/internal/store"
)

type Actor struct {
	User string
	Role string
}

type Service struct {
	st  *store.Store
	Now func() time.Time
}

func New(st *store.Store) *Service {
	return &Service{st: st, Now: func() time.Time { return time.Now().UTC() }}
}

var roleRU = map[string]string{domain.RoleManager: "менеджеру кампании", domain.RoleModerator: "модератору"}

// editable — состояния, в которых разрешены PUT кампании и правка дочерних сущностей.
var editable = []string{domain.StateDraft, domain.StateNeedsWork, domain.StateApproved, domain.StateActive, domain.StateActiveEditing}

func (s *Service) ts() string { return s.Now().Format("2006-01-02T15:04:05") }

func requireRole(a Actor, role string) *domain.APIError {
	if a.Role != role {
		return domain.Fail("ROLE_FORBIDDEN", "X-Role", "действие доступно только "+roleRU[role])
	}
	return nil
}

func (s *Service) campaign(id int64) (*domain.Campaign, *domain.APIError) {
	c, ok := s.st.S.Campaigns[id]
	if !ok {
		return nil, domain.NotFound(fmt.Sprintf("кампания %d", id))
	}
	return c, nil
}

func requireEditable(c *domain.Campaign) *domain.APIError {
	if !slices.Contains(editable, c.State) {
		return domain.Fail("UPDATE_NOT_ALLOWED", "state", fmt.Sprintf("кампания %d в статусе %s", c.ID, c.State))
	}
	return nil
}

// afterEdit — правка снимает одобрение (APPROVED → DRAFT), правка живой → ACTIVE_EDITING.
func afterEdit(c *domain.Campaign, actor Actor) {
	switch c.State {
	case domain.StateApproved:
		c.State = domain.StateDraft
	case domain.StateActive:
		c.State = domain.StateActiveEditing
	}
	c.LastEditAuthor = actor.User
}

func (s *Service) audit(campaignID int64, entity string, entityID int64, action string, changes map[string]any, actor Actor, comment *string) {
	s.st.S.Audit = append(s.st.S.Audit, domain.AuditEntry{
		ID: s.st.Next("audit"), CampaignID: campaignID, Entity: entity, EntityID: entityID,
		Action: action, Changes: changes, At: s.ts(), Actor: actor.User, Comment: comment,
	})
}

func (s *Service) save() *domain.APIError {
	if err := s.st.Save(); err != nil {
		return &domain.APIError{Status: 500, Errors: []domain.FieldError{{Code: "STORAGE_ERROR", Message: err.Error()}}}
	}
	return nil
}

func others(st *store.Store) []*domain.Campaign { return st.CampaignList() }

func fromErrs(errs, notFound []domain.FieldError) *domain.APIError {
	if len(notFound) > 0 {
		return &domain.APIError{Status: 404, Errors: notFound}
	}
	if len(errs) > 0 {
		return domain.BadRequest(errs...)
	}
	return nil
}

// diff — изменённые поля верхнего уровня {поле: {from, to}}.
func diff(before, after any) map[string]any {
	var a, b map[string]any
	ra, _ := json.Marshal(before)
	rb, _ := json.Marshal(after)
	_ = json.Unmarshal(ra, &a)
	_ = json.Unmarshal(rb, &b)
	out := map[string]any{}
	for k := range keys(a, b) {
		if !reflect.DeepEqual(a[k], b[k]) {
			out[k] = map[string]any{"from": a[k], "to": b[k]}
		}
	}
	return out
}

func keys(ms ...map[string]any) map[string]struct{} {
	out := map[string]struct{}{}
	for _, m := range ms {
		for k := range m {
			out[k] = struct{}{}
		}
	}
	return out
}

// ======================= справочники =======================

func (s *Service) Dictionary(name string) any {
	s.st.Lock()
	defer s.st.Unlock()
	S := s.st.S
	switch name {
	case "topics":
		return S.Topics
	case "tags":
		return S.Tags
	case "channels":
		return S.Channels
	case "banner-types":
		return S.BannerTypes
	case "segment-types":
		return S.SegmentTypes
	case "segments":
		return S.Segments
	case "places":
		return S.Places
	}
	return nil
}

func (s *Service) CreatePlace(a Actor, body map[string]any) (any, *domain.APIError) {
	if e := requireRole(a, domain.RoleManager); e != nil {
		return nil, e
	}
	s.st.Lock()
	defer s.st.Unlock()
	code, _ := body["code"].(string)
	desc, _ := body["description"].(string)
	var errs []domain.FieldError
	if strings.TrimSpace(code) == "" {
		errs = append(errs, domain.NewFieldError("PLACE_CODE_REQUIRED", "", ""))
	}
	if strings.TrimSpace(desc) == "" {
		errs = append(errs, domain.NewFieldError("PLACE_DESCRIPTION_REQUIRED", "", ""))
	}
	for _, p := range s.st.S.Places {
		if p.Code == code {
			errs = append(errs, domain.NewFieldError("PLACE_CODE_DUPLICATE", "", code))
		}
	}
	if len(errs) > 0 {
		return nil, domain.BadRequest(errs...)
	}
	p := domain.Place{ID: s.st.Next("place"), Code: code, Description: desc, State: "ACTIVE"}
	s.st.S.Places = append(s.st.S.Places, p)
	s.audit(0, "PLACE", p.ID, "CREATE", nil, a, nil)
	return p, s.save()
}

func (s *Service) CreateTag(a Actor, body map[string]any) (any, *domain.APIError) {
	if e := requireRole(a, domain.RoleManager); e != nil {
		return nil, e
	}
	s.st.Lock()
	defer s.st.Unlock()
	name, _ := body["name"].(string)
	if strings.TrimSpace(name) == "" {
		return nil, domain.Fail("TAG_NAME_REQUIRED", "", "")
	}
	for _, t := range s.st.S.Tags {
		if strings.EqualFold(t.Name, name) {
			return nil, domain.Fail("TAG_NAME_DUPLICATE", "", fmt.Sprintf("«%s» уже есть (id %d)", t.Name, t.ID))
		}
	}
	t := domain.Tag{ID: s.st.Next("tag"), Name: name}
	s.st.S.Tags = append(s.st.S.Tags, t)
	s.audit(0, "TAG", t.ID, "CREATE", nil, a, nil)
	return t, s.save()
}

// ======================= кампании =======================

func (s *Service) List() []domain.CampaignListItem {
	s.st.Lock()
	defer s.st.Unlock()
	out := []domain.CampaignListItem{}
	for _, c := range s.st.CampaignList() {
		out = append(out, domain.CampaignListItem{ID: c.ID, Name: c.Name, State: c.State, Published: c.Published,
			Topic: c.Topic, StartDate: c.StartDate, StartTime: c.StartTime, EndDate: c.EndDate, EndTime: c.EndTime})
	}
	return out
}

func (s *Service) Get(id int64) (domain.CampaignDetails, *domain.APIError) {
	s.st.Lock()
	defer s.st.Unlock()
	det, err := s.st.Details(id)
	if err != nil {
		return det, domain.NotFound(fmt.Sprintf("кампания %d", id))
	}
	return det, nil
}

func (s *Service) Create(a Actor, body map[string]any) (domain.CampaignDetails, *domain.APIError) {
	if e := requireRole(a, domain.RoleManager); e != nil {
		return domain.CampaignDetails{}, e
	}
	s.st.Lock()
	defer s.st.Unlock()
	c := &domain.Campaign{Weight: 0, InitialCtr: 15}
	if e := applyHeader(c, body); e != nil {
		return domain.CampaignDetails{}, e
	}
	c.Segments = domain.Segments{Included: []string{}, Excluded: []string{}}
	if e := fromErrs(domain.ValidateHeader(c, s.st.Dicts(), others(s.st))); e != nil {
		return domain.CampaignDetails{}, e
	}
	c.ID = s.st.Next("campaign")
	c.State, c.Published, c.Author, c.LastEditAuthor = domain.StateDraft, false, a.User, a.User
	s.st.S.Campaigns[c.ID] = c
	s.audit(c.ID, "CAMPAIGN", c.ID, "CREATE", nil, a, nil)
	if e := s.save(); e != nil {
		return domain.CampaignDetails{}, e
	}
	det, _ := s.st.Details(c.ID)
	return det, nil
}

func (s *Service) Update(a Actor, id int64, body map[string]any) (domain.CampaignDetails, *domain.APIError) {
	if e := requireRole(a, domain.RoleManager); e != nil {
		return domain.CampaignDetails{}, e
	}
	s.st.Lock()
	defer s.st.Unlock()
	c, e := s.campaign(id)
	if e != nil {
		return domain.CampaignDetails{}, e
	}
	if e := requireEditable(c); e != nil {
		return domain.CampaignDetails{}, e
	}
	// PUT — полная замена шапки: начинаем с пустой шапки и служебных полей.
	n := &domain.Campaign{ID: c.ID, State: c.State, Published: c.Published, Author: c.Author,
		LastEditAuthor: c.LastEditAuthor, Segments: c.Segments, Weight: 0, InitialCtr: 15}
	if e := applyHeader(n, body); e != nil {
		return domain.CampaignDetails{}, e
	}
	if e := fromErrs(domain.ValidateHeader(n, s.st.Dicts(), others(s.st))); e != nil {
		return domain.CampaignDetails{}, e
	}
	changes := diff(c, n)
	afterEdit(n, a)
	s.st.S.Campaigns[id] = n
	s.audit(id, "CAMPAIGN", id, "UPDATE", changes, a, nil)
	if e := s.save(); e != nil {
		return domain.CampaignDetails{}, e
	}
	det, _ := s.st.Details(id)
	return det, nil
}

func (s *Service) Delete(a Actor, id int64) *domain.APIError {
	if e := requireRole(a, domain.RoleManager); e != nil {
		return e
	}
	s.st.Lock()
	defer s.st.Unlock()
	c, e := s.campaign(id)
	if e != nil {
		return e
	}
	if c.Published || (c.State != domain.StateDraft && c.State != domain.StateNeedsWork) {
		return domain.Fail("DELETE_NOT_ALLOWED", "state", fmt.Sprintf("статус %s, published=%v", c.State, c.Published))
	}
	for k, b := range s.st.S.Banners {
		if b.CampaignID == id {
			delete(s.st.S.Banners, k)
		}
	}
	for k, x := range s.st.S.Contents {
		if x.CampaignID == id {
			delete(s.st.S.Contents, k)
		}
	}
	for k, x := range s.st.S.Creatives {
		if x.CampaignID == id {
			delete(s.st.S.Creatives, k)
		}
	}
	delete(s.st.S.Campaigns, id)
	s.audit(id, "CAMPAIGN", id, "DELETE", nil, a, nil)
	return s.save()
}

func (s *Service) PutSegments(a Actor, id int64, body map[string]any) (domain.Segments, *domain.APIError) {
	if e := requireRole(a, domain.RoleManager); e != nil {
		return domain.Segments{}, e
	}
	s.st.Lock()
	defer s.st.Unlock()
	c, e := s.campaign(id)
	if e != nil {
		return domain.Segments{}, e
	}
	if e := requireEditable(c); e != nil {
		return domain.Segments{}, e
	}
	seg := domain.Segments{Included: strList(body["included"]), Excluded: strList(body["excluded"])}
	if errs := domain.ValidateSegments(c.AudienceType, seg, s.st.Dicts()); len(errs) > 0 {
		return domain.Segments{}, domain.BadRequest(errs...)
	}
	changes := diff(c.Segments, seg)
	c.Segments = seg
	afterEdit(c, a)
	s.audit(id, "SEGMENTS", id, "UPDATE", changes, a, nil)
	return seg, s.save()
}

// ======================= баннеры =======================

func (s *Service) SaveBanner(a Actor, campaignID, bannerID int64, body map[string]any) (*domain.Banner, *domain.APIError) {
	if e := requireRole(a, domain.RoleManager); e != nil {
		return nil, e
	}
	s.st.Lock()
	defer s.st.Unlock()
	c, e := s.campaign(campaignID)
	if e != nil {
		return nil, e
	}
	var old *domain.Banner
	if bannerID != 0 {
		old = s.st.S.Banners[bannerID]
		if old == nil || old.CampaignID != campaignID {
			return nil, domain.NotFound(fmt.Sprintf("баннер %d", bannerID))
		}
	}
	if e := requireEditable(c); e != nil {
		return nil, e
	}
	b := &domain.Banner{ID: bannerID, CampaignID: campaignID}
	b.Name, _ = body["name"].(string)
	b.BannerTypeID = toInt(body["bannerTypeId"])
	b.Content, _ = body["content"].(map[string]any)
	if e := fromErrs(domain.ValidateBanner(b.Name, b.BannerTypeID, b.Content, s.st.Dicts())); e != nil {
		return nil, e
	}
	// смена типа баннера не должна ломать уже привязанные креативы
	if old != nil && old.BannerTypeID != b.BannerTypeID {
		bt := s.st.Dicts().BannerTypes[b.BannerTypeID]
		for _, cr := range s.st.S.Creatives {
			if cr.BannerID == b.ID && !slices.Contains(bt.Channels, cr.ChannelCode) {
				return nil, domain.Fail("CREATIVE_CHANNEL_NOT_ALLOWED", "bannerTypeId", fmt.Sprintf("креатив %d в канале %s несовместим с %s", cr.ID, cr.ChannelCode, bt.Code))
			}
		}
	}
	action, changes := "CREATE", map[string]any(nil)
	if old == nil {
		b.ID = s.st.Next("banner")
	} else {
		action, changes = "UPDATE", diff(old, b)
	}
	s.st.S.Banners[b.ID] = b
	afterEdit(c, a)
	s.audit(campaignID, "BANNER", b.ID, action, changes, a, nil)
	return b, s.save()
}

func (s *Service) DeleteBanner(a Actor, campaignID, bannerID int64) *domain.APIError {
	return s.deleteChild(a, campaignID, "BANNER", bannerID, func() bool {
		b := s.st.S.Banners[bannerID]
		if b == nil || b.CampaignID != campaignID {
			return false
		}
		delete(s.st.S.Banners, bannerID)
		for k, cr := range s.st.S.Creatives { // креативы без баннера не имеют смысла
			if cr.BannerID == bannerID {
				delete(s.st.S.Creatives, k)
			}
		}
		return true
	})
}

// ======================= контент =======================

func (s *Service) SaveContent(a Actor, campaignID, contentID int64, body map[string]any) (*domain.Content, *domain.APIError) {
	if e := requireRole(a, domain.RoleManager); e != nil {
		return nil, e
	}
	s.st.Lock()
	defer s.st.Unlock()
	c, e := s.campaign(campaignID)
	if e != nil {
		return nil, e
	}
	var old *domain.Content
	if contentID != 0 {
		old = s.st.S.Contents[contentID]
		if old == nil || old.CampaignID != campaignID {
			return nil, domain.NotFound(fmt.Sprintf("контент %d", contentID))
		}
	}
	if e := requireEditable(c); e != nil {
		return nil, e
	}
	x := &domain.Content{ID: contentID, CampaignID: campaignID}
	x.Name, _ = body["name"].(string)
	x.ContentType, _ = body["contentType"].(string)
	if x.ContentType == "" {
		x.ContentType = "PROMO"
	}
	x.Content, _ = body["content"].(map[string]any)
	if errs := domain.ValidateContent(x.Name, x.ContentType, x.Content); len(errs) > 0 {
		return nil, domain.BadRequest(errs...)
	}
	action, changes := "CREATE", map[string]any(nil)
	if old == nil {
		x.ID = s.st.Next("content")
	} else {
		action, changes = "UPDATE", diff(old, x)
	}
	s.st.S.Contents[x.ID] = x
	afterEdit(c, a)
	s.audit(campaignID, "CONTENT", x.ID, action, changes, a, nil)
	return x, s.save()
}

func (s *Service) DeleteContent(a Actor, campaignID, contentID int64) *domain.APIError {
	return s.deleteChild(a, campaignID, "CONTENT", contentID, func() bool {
		x := s.st.S.Contents[contentID]
		if x == nil || x.CampaignID != campaignID {
			return false
		}
		delete(s.st.S.Contents, contentID)
		for _, cr := range s.st.S.Creatives { // креатив без контента валиден
			if cr.ContentID != nil && *cr.ContentID == contentID {
				cr.ContentID = nil
			}
		}
		return true
	})
}

// ======================= креативы =======================

func (s *Service) SaveCreative(a Actor, campaignID, creativeID int64, body map[string]any) (*domain.Creative, *domain.APIError) {
	if e := requireRole(a, domain.RoleManager); e != nil {
		return nil, e
	}
	s.st.Lock()
	defer s.st.Unlock()
	c, e := s.campaign(campaignID)
	if e != nil {
		return nil, e
	}
	var old *domain.Creative
	if creativeID != 0 {
		old = s.st.S.Creatives[creativeID]
		if old == nil || old.CampaignID != campaignID {
			return nil, domain.NotFound(fmt.Sprintf("креатив %d", creativeID))
		}
	}
	if e := requireEditable(c); e != nil {
		return nil, e
	}
	cr := &domain.Creative{ID: creativeID, CampaignID: campaignID}
	cr.Name, _ = body["name"].(string)
	cr.BannerID = toInt(body["bannerId"])
	cr.ChannelCode, _ = body["channelCode"].(string)
	if v, ok := body["contentId"]; ok && v != nil {
		id := toInt(v)
		cr.ContentID = &id
	}
	b := s.st.S.Banners[cr.BannerID]
	if b == nil || b.CampaignID != campaignID {
		return nil, domain.NotFound(fmt.Sprintf("баннер %d в кампании %d", cr.BannerID, campaignID))
	}
	if cr.ContentID != nil {
		if x := s.st.S.Contents[*cr.ContentID]; x == nil || x.CampaignID != campaignID {
			return nil, domain.NotFound(fmt.Sprintf("контент %d в кампании %d", *cr.ContentID, campaignID))
		}
	}
	if _, ok := s.st.Dicts().Channels[cr.ChannelCode]; !ok {
		return nil, domain.NotFound(fmt.Sprintf("платформа %q (доступны iOS, ANDROID, WEB)", cr.ChannelCode))
	}
	var existing []domain.Creative
	for _, x := range s.st.S.Creatives {
		if x.CampaignID == campaignID {
			existing = append(existing, *x)
		}
	}
	if errs := domain.ValidateCreative(*cr, s.st.Dicts().BannerTypes[b.BannerTypeID], existing); len(errs) > 0 {
		return nil, domain.BadRequest(errs...)
	}
	action, changes := "CREATE", map[string]any(nil)
	if old == nil {
		cr.ID = s.st.Next("creative")
	} else {
		action, changes = "UPDATE", diff(old, cr)
	}
	s.st.S.Creatives[cr.ID] = cr
	afterEdit(c, a)
	s.audit(campaignID, "CREATIVE", cr.ID, action, changes, a, nil)
	return cr, s.save()
}

func (s *Service) DeleteCreative(a Actor, campaignID, creativeID int64) *domain.APIError {
	return s.deleteChild(a, campaignID, "CREATIVE", creativeID, func() bool {
		x := s.st.S.Creatives[creativeID]
		if x == nil || x.CampaignID != campaignID {
			return false
		}
		delete(s.st.S.Creatives, creativeID)
		return true
	})
}

func (s *Service) deleteChild(a Actor, campaignID int64, entity string, id int64, del func() bool) *domain.APIError {
	if e := requireRole(a, domain.RoleManager); e != nil {
		return e
	}
	s.st.Lock()
	defer s.st.Unlock()
	c, e := s.campaign(campaignID)
	if e != nil {
		return e
	}
	if e := requireEditable(c); e != nil {
		return e
	}
	if !del() {
		return domain.NotFound(fmt.Sprintf("%s %d", strings.ToLower(entity), id))
	}
	afterEdit(c, a)
	s.audit(campaignID, entity, id, "DELETE", nil, a, nil)
	return s.save()
}

// ======================= валидация, аудит =======================

type ValidationResult struct {
	Errors          []domain.FieldError `json:"errors"`
	Warnings        []string            `json:"warnings"`
	WarningsDetails []domain.FieldError `json:"warningDetails"`
}

func (s *Service) validate(id int64) (ValidationResult, *domain.APIError) {
	det, err := s.st.Details(id)
	if err != nil {
		return ValidationResult{}, domain.NotFound(fmt.Sprintf("кампания %d", id))
	}
	errs, warns := domain.ValidateCampaign(det, s.st.Dicts(), others(s.st))
	r := ValidationResult{Errors: errs, Warnings: []string{}, WarningsDetails: warns}
	if r.Errors == nil {
		r.Errors = []domain.FieldError{}
	}
	if r.WarningsDetails == nil {
		r.WarningsDetails = []domain.FieldError{}
	}
	for _, w := range warns {
		r.Warnings = append(r.Warnings, w.Message)
	}
	return r, nil
}

func (s *Service) Warnings(id int64) (ValidationResult, *domain.APIError) {
	s.st.Lock()
	defer s.st.Unlock()
	return s.validate(id)
}

func (s *Service) Audit(id int64) ([]domain.AuditEntry, *domain.APIError) {
	s.st.Lock()
	defer s.st.Unlock()
	if _, ok := s.st.S.Campaigns[id]; !ok {
		// журнал удалённой кампании тоже читается
		found := false
		for _, e := range s.st.S.Audit {
			found = found || e.CampaignID == id
		}
		if !found {
			return nil, domain.NotFound(fmt.Sprintf("кампания %d", id))
		}
	}
	out := []domain.AuditEntry{}
	for _, e := range s.st.S.Audit {
		if e.CampaignID == id {
			out = append(out, e)
		}
	}
	return out, nil
}

// ======================= жизненный цикл =======================

func (s *Service) ToModeration(a Actor, id int64) (*domain.Campaign, *domain.APIError) {
	if e := requireRole(a, domain.RoleManager); e != nil {
		return nil, e
	}
	s.st.Lock()
	defer s.st.Unlock()
	c, e := s.campaign(id)
	if e != nil {
		return nil, e
	}
	if !slices.Contains([]string{domain.StateDraft, domain.StateNeedsWork, domain.StateActiveEditing}, c.State) {
		return nil, domain.Fail("TO_MODERATION_NOT_ALLOWED", "state", "текущий статус "+c.State)
	}
	v, _ := s.validate(id)
	if len(v.Errors) > 0 {
		errs := append([]domain.FieldError{domain.NewFieldError("TO_MODERATION_NOT_ALLOWED", "", fmt.Sprintf("ошибок: %d", len(v.Errors)))}, v.Errors...)
		return nil, domain.BadRequest(errs...)
	}
	return s.transition(c, a, domain.StateOnModeration, "TO_MODERATION", nil)
}

func (s *Service) Decline(a Actor, id int64, comment string) (*domain.Campaign, *domain.APIError) {
	if e := requireRole(a, domain.RoleModerator); e != nil {
		return nil, e
	}
	s.st.Lock()
	defer s.st.Unlock()
	c, e := s.campaign(id)
	if e != nil {
		return nil, e
	}
	if c.State != domain.StateOnModeration {
		return nil, domain.Fail("DECLINE_NOT_ALLOWED", "state", "текущий статус "+c.State)
	}
	if strings.TrimSpace(comment) == "" {
		return nil, domain.Fail("DECLINE_COMMENT_REQUIRED", "", "")
	}
	return s.transition(c, a, domain.StateNeedsWork, "DECLINE", &comment)
}

func (s *Service) Approve(a Actor, id int64) (*domain.Campaign, *domain.APIError) {
	if e := requireRole(a, domain.RoleModerator); e != nil {
		return nil, e
	}
	s.st.Lock()
	defer s.st.Unlock()
	c, e := s.campaign(id)
	if e != nil {
		return nil, e
	}
	if c.State != domain.StateOnModeration {
		return nil, domain.Fail("APPROVE_NOT_ALLOWED", "state", "текущий статус "+c.State)
	}
	if c.LastEditAuthor == a.User {
		return nil, domain.Fail("TWO_HANDS_RULE", "", a.User)
	}
	return s.transition(c, a, domain.StateApproved, "APPROVE", nil)
}

// CBROExport — заглушка Content Broker (mocks/cbro_export.json): всегда успех.
func (s *Service) CBROExport(id int64) map[string]any {
	return map[string]any{"status": "OK", "campaignId": id, "exportedAt": s.ts()}
}

func (s *Service) Activate(a Actor, id int64) (*domain.Campaign, *domain.APIError) {
	if e := requireRole(a, domain.RoleManager); e != nil {
		return nil, e
	}
	s.st.Lock()
	defer s.st.Unlock()
	c, e := s.campaign(id)
	if e != nil {
		return nil, e
	}
	if c.State != domain.StateApproved {
		return nil, domain.Fail("ACTIVATE_NOT_ALLOWED", "state", "текущий статус "+c.State)
	}
	_ = s.CBROExport(id)
	c.Published = true
	return s.transition(c, a, domain.StateActive, "ACTIVATE", nil)
}

// Resume — запрос менеджера на возобновление остановленной кампании.
// Кампания уходит модератору (ON_MODERATION); после одобрения её можно запустить снова.
func (s *Service) Resume(a Actor, id int64, comment string) (*domain.Campaign, *domain.APIError) {
	if e := requireRole(a, domain.RoleManager); e != nil {
		return nil, e
	}
	s.st.Lock()
	defer s.st.Unlock()
	c, e := s.campaign(id)
	if e != nil {
		return nil, e
	}
	if c.State != domain.StateStopped {
		return nil, domain.Fail("RESUME_NOT_ALLOWED", "state", "текущий статус "+c.State)
	}
	if c.EndDate != nil && *c.EndDate < s.Now().Format("2006-01-02") {
		return nil, domain.Fail("RESUME_PERIOD_ENDED", "endDate", "окончание "+*c.EndDate)
	}
	c.LastEditAuthor = a.User // одобрить возобновление должен не тот, кто его запросил
	var cm *string
	if t := strings.TrimSpace(comment); t != "" {
		cm = &t
	}
	return s.transition(c, a, domain.StateOnModeration, "RESUME_REQUEST", cm)
}

func (s *Service) Stop(a Actor, id int64) (*domain.Campaign, *domain.APIError) {
	if e := requireRole(a, domain.RoleManager); e != nil {
		return nil, e
	}
	s.st.Lock()
	defer s.st.Unlock()
	c, e := s.campaign(id)
	if e != nil {
		return nil, e
	}
	if !c.Published {
		return nil, domain.Fail("STOP_NOT_ALLOWED", "published", "показ не идёт, статус "+c.State)
	}
	c.Published = false
	return s.transition(c, a, domain.StateStopped, "STOP", nil)
}

func (s *Service) transition(c *domain.Campaign, a Actor, to, action string, comment *string) (*domain.Campaign, *domain.APIError) {
	c.State = to
	s.audit(c.ID, "CAMPAIGN", c.ID, action, nil, a, comment)
	if e := s.save(); e != nil {
		return nil, e
	}
	cp := *c
	return &cp, nil
}

// ======================= разбор тела кампании =======================

// applyHeader переносит поля тела POST/PUT в кампанию. Словарные поля
// (topic, tags, places) принимаются как {value, label} и как сырые значения.
func applyHeader(c *domain.Campaign, b map[string]any) *domain.APIError {
	str := func(k string) string { s, _ := b[k].(string); return s }
	optStr := func(k string) *string {
		if s, ok := b[k].(string); ok && s != "" {
			return &s
		}
		return nil
	}
	c.Name = str("name")
	c.MarketingName = optStr("marketingName")
	c.StartDate, c.StartTime = str("startDate"), str("startTime")
	c.EndDate, c.EndTime = optStr("endDate"), optStr("endTime")
	c.Keywords = optStr("keywords")
	c.AudienceType = str("audienceType")
	switch t := b["topic"].(type) {
	case string:
		c.Topic = t
	case map[string]any:
		c.Topic, _ = t["value"].(string)
	}
	c.Tags = idList(b["tags"])
	c.Places = idList(b["places"])
	if v, ok := b["weight"]; ok && v != nil {
		f, isNum := v.(float64)
		if !isNum {
			return domain.Fail("WEIGHT_INVALID", "", fmt.Sprint(v))
		}
		c.Weight = f
	}
	if v, ok := b["initialCtr"]; ok && v != nil {
		f, isNum := v.(float64)
		if !isNum {
			return domain.Fail("INITIAL_CTR_INVALID", "", fmt.Sprint(v))
		}
		c.InitialCtr = f
	}
	return nil
}

func idList(v any) []int64 {
	arr, _ := v.([]any)
	out := []int64{}
	for _, x := range arr {
		if m, ok := x.(map[string]any); ok {
			x = m["value"]
		}
		if id := toInt(x); id != 0 {
			out = append(out, id)
		}
	}
	return out
}

func strList(v any) []string {
	arr, _ := v.([]any)
	out := []string{}
	for _, x := range arr {
		if m, ok := x.(map[string]any); ok {
			x = m["value"]
		}
		if s, ok := x.(string); ok && s != "" {
			out = append(out, s)
		}
	}
	return out
}

func toInt(v any) int64 {
	switch x := v.(type) {
	case float64:
		return int64(x)
	case int64:
		return x
	case int:
		return int64(x)
	case json.Number:
		n, _ := x.Int64()
		return n
	}
	return 0
}
