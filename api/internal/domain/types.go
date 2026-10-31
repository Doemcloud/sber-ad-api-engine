// Package domain — доменная модель MVP из task.md §2: кампания, баннер,
// PROMO-контент, креатив, места показа, сегменты, справочники, аудит.
package domain

// Состояния жизненного цикла (task.md §2.3).
const (
	StateDraft         = "DRAFT"
	StateOnModeration  = "ON_MODERATION"
	StateNeedsWork     = "NEEDS_WORK"
	StateApproved      = "APPROVED"
	StateActive        = "ACTIVE"
	StateActiveEditing = "ACTIVE_EDITING"
	StateStopped       = "STOPPED"
	StateArchived      = "ARCHIVED"
)

const (
	AudienceAll       = "ALL_USERS"
	AudienceSegmented = "SEGMENTED"
)

// Роли (заголовок X-Role).
const (
	RoleManager   = "campaignManager"
	RoleModerator = "campaignModerator"
)

type Campaign struct {
	ID             int64    `json:"id"`
	Name           string   `json:"name"`
	MarketingName  *string  `json:"marketingName,omitempty"`
	StartDate      string   `json:"startDate"`
	StartTime      string   `json:"startTime"`
	EndDate        *string  `json:"endDate,omitempty"`
	EndTime        *string  `json:"endTime,omitempty"`
	Topic          string   `json:"topic"`
	Tags           []int64  `json:"tags"`
	Keywords       *string  `json:"keywords,omitempty"`
	AudienceType   string   `json:"audienceType"`
	Weight         float64  `json:"weight"`
	InitialCtr     float64  `json:"initialCtr"`
	State          string   `json:"state"`
	Published      bool     `json:"published"`
	Author         string   `json:"author"`
	LastEditAuthor string   `json:"lastEditAuthor"`
	Places         []int64  `json:"places"`
	Segments       Segments `json:"-"`
}

// CampaignListItem — лёгкий DTO для GET /campaigns.
type CampaignListItem struct {
	ID        int64   `json:"id"`
	Name      string  `json:"name"`
	State     string  `json:"state"`
	Published bool    `json:"published"`
	Topic     string  `json:"topic"`
	StartDate string  `json:"startDate"`
	StartTime string  `json:"startTime"`
	EndDate   *string `json:"endDate,omitempty"`
	EndTime   *string `json:"endTime,omitempty"`
}

// CampaignDetails — DTO для GET /campaigns/{id}.
type CampaignDetails struct {
	Campaign
	Banners   []Banner   `json:"banners"`
	Contents  []Content  `json:"contents"`
	Creatives []Creative `json:"creatives"`
	Segments  Segments   `json:"segments"`
}

type Segments struct {
	Included []string `json:"included"`
	Excluded []string `json:"excluded"`
}

type Banner struct {
	ID           int64          `json:"id"`
	CampaignID   int64          `json:"campaignId"`
	Name         string         `json:"name"`
	BannerTypeID int64          `json:"bannerTypeId"`
	Content      map[string]any `json:"content"`
}

type Content struct {
	ID          int64          `json:"id"`
	CampaignID  int64          `json:"campaignId"`
	Name        string         `json:"name"`
	ContentType string         `json:"contentType"`
	Content     map[string]any `json:"content"`
}

type Creative struct {
	ID          int64  `json:"id"`
	CampaignID  int64  `json:"campaignId"`
	Name        string `json:"name"`
	BannerID    int64  `json:"bannerId"`
	ContentID   *int64 `json:"contentId,omitempty"`
	ChannelCode string `json:"channelCode"`
}

// --- справочники ---

type Topic struct {
	Value string `json:"value"`
	Label string `json:"label"`
}

type Tag struct {
	ID   int64  `json:"id"`
	Name string `json:"name"`
}

type Channel struct {
	ID          int64  `json:"id"`
	Code        string `json:"code"`
	Description string `json:"description"`
}

type BannerType struct {
	ID             int64    `json:"id"`
	Code           string   `json:"code"`
	Description    string   `json:"description"`
	PreviewForm    string   `json:"previewForm"`
	TitleMaxLength int      `json:"titleMaxLength"`
	TextMaxLength  int      `json:"textMaxLength"`
	Channels       []string `json:"channels"`
}

type SegmentType struct {
	Code string `json:"code"`
	Name string `json:"name"`
}

type Segment struct {
	Code  string `json:"code"`
	Name  string `json:"name"`
	Type  string `json:"type"`
	State string `json:"state"`
	Count int64  `json:"count"`
}

type Place struct {
	ID            int64   `json:"id"`
	Code          string  `json:"code"`
	Description   string  `json:"description"`
	DefaultBanner *string `json:"defaultBanner"`
	State         string  `json:"state"`
}

// AuditEntry — запись журнала аудита (task.md §3 «Аудит»).
type AuditEntry struct {
	ID         int64          `json:"id"`
	CampaignID int64          `json:"campaignId"`
	Entity     string         `json:"entity"`
	EntityID   int64          `json:"entityId"`
	Action     string         `json:"action"`
	Changes    map[string]any `json:"changes"`
	At         string         `json:"at"`
	Actor      string         `json:"actor"`
	Comment    *string        `json:"comment"`
}
