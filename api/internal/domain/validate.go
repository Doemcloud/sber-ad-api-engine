package domain

import (
	"fmt"
	"regexp"
	"slices"
	"strings"
	"time"
	"unicode/utf8"
)

// Dicts — справочники, нужные валидации.
type Dicts struct {
	Topics      map[string]Topic
	Tags        map[int64]Tag
	Channels    map[string]Channel
	BannerTypes map[int64]BannerType
	Segments    map[string]Segment
	Places      map[int64]Place
}

var (
	reColor = regexp.MustCompile(`^#[0-9A-Fa-f]{8}$`)
	reTime  = regexp.MustCompile(`^([01]\d|2[0-3]):[0-5]\d$`)

	ActionTypes  = []string{"default", "externalLink", "openSmartLink", "closeCampaign", "doneCampaign"}
	FontWeights  = []string{"thin", "light", "regular", "medium", "semi-bold", "bold"}
	bannerKeys   = []string{"title", "text", "titleStyle", "textStyle", "background", "image", "buttonName", "actionType", "link", "voiceOver"}
	linkKeys     = []string{"iOS", "android", "web"}
	linkRequired = []string{"externalLink", "openSmartLink"}
	linkBanned   = []string{"closeCampaign", "doneCampaign"}
)

// ---------------- шапка кампании ----------------

// ValidateHeader проверяет шапку. others — остальные кампании (для NAME_DUPLICATE).
// Ссылки на несуществующие теги/места возвращаются отдельно как notFound (HTTP 404).
func ValidateHeader(c *Campaign, d Dicts, others []*Campaign) (errs []FieldError, notFound []FieldError) {
	name := strings.TrimSpace(c.Name)
	switch {
	case name == "":
		errs = append(errs, NewFieldError("NAME_REQUIRED", "", ""))
	case utf8.RuneCountInString(c.Name) > 100:
		errs = append(errs, NewFieldError("NAME_TOO_LONG", "", fmt.Sprintf("%d символов", utf8.RuneCountInString(c.Name))))
	}
	for _, o := range others {
		if o.ID != c.ID && strings.EqualFold(strings.TrimSpace(o.Name), name) && name != "" {
			errs = append(errs, NewFieldError("NAME_DUPLICATE", "", fmt.Sprintf("«%s»", o.Name)))
			break
		}
	}
	if c.MarketingName != nil && utf8.RuneCountInString(*c.MarketingName) > 100 {
		errs = append(errs, NewFieldError("MARKETING_NAME_TOO_LONG", "", ""))
	}

	start, startOK := time.Time{}, false
	if c.StartDate == "" {
		errs = append(errs, NewFieldError("START_DATE_REQUIRED", "", ""))
	} else if _, err := time.Parse(time.DateOnly, c.StartDate); err != nil {
		errs = append(errs, NewFieldError("DATE_FORMAT_INVALID", "startDate", c.StartDate))
	}
	if c.StartTime == "" {
		errs = append(errs, NewFieldError("START_TIME_REQUIRED", "", ""))
	} else if !reTime.MatchString(c.StartTime) {
		errs = append(errs, NewFieldError("TIME_FORMAT_INVALID", "startTime", c.StartTime))
	}
	if t, err := time.Parse("2006-01-02 15:04", c.StartDate+" "+c.StartTime); err == nil {
		start, startOK = t, true
	}
	if c.EndDate != nil && *c.EndDate != "" {
		if _, err := time.Parse(time.DateOnly, *c.EndDate); err != nil {
			errs = append(errs, NewFieldError("DATE_FORMAT_INVALID", "endDate", *c.EndDate))
		}
	}
	if c.EndTime != nil && *c.EndTime != "" {
		if !reTime.MatchString(*c.EndTime) {
			errs = append(errs, NewFieldError("TIME_FORMAT_INVALID", "endTime", *c.EndTime))
		}
		if c.EndDate == nil || *c.EndDate == "" {
			errs = append(errs, NewFieldError("END_TIME_WITHOUT_END_DATE", "", ""))
		}
	}
	if c.EndDate != nil && *c.EndDate != "" && startOK {
		et := "23:59"
		if c.EndTime != nil && *c.EndTime != "" {
			et = *c.EndTime
		}
		if end, err := time.Parse("2006-01-02 15:04", *c.EndDate+" "+et); err == nil && !end.After(start) {
			errs = append(errs, NewFieldError("DATE_RANGE_INVALID", "", fmt.Sprintf("старт %s %s, окончание %s %s", c.StartDate, c.StartTime, *c.EndDate, et)))
		}
	}

	if c.Topic == "" {
		errs = append(errs, NewFieldError("TOPIC_REQUIRED", "", ""))
	} else if _, ok := d.Topics[c.Topic]; !ok {
		errs = append(errs, NewFieldError("TOPIC_INVALID", "", c.Topic))
	}
	for _, t := range c.Tags {
		if _, ok := d.Tags[t]; !ok {
			notFound = append(notFound, NewFieldError("ENTITY_NOT_FOUND", "tags", fmt.Sprintf("тег %d", t)))
		}
	}
	if c.Keywords != nil && utf8.RuneCountInString(*c.Keywords) > 512 {
		errs = append(errs, NewFieldError("KEYWORDS_TOO_LONG", "", ""))
	}
	switch c.AudienceType {
	case "":
		errs = append(errs, NewFieldError("AUDIENCE_TYPE_REQUIRED", "", ""))
	case AudienceAll, AudienceSegmented:
	default:
		errs = append(errs, NewFieldError("AUDIENCE_TYPE_INVALID", "", c.AudienceType))
	}
	if c.AudienceType == AudienceAll && (len(c.Segments.Included) > 0 || len(c.Segments.Excluded) > 0) {
		errs = append(errs, NewFieldError("SEGMENTS_FORBIDDEN_FOR_ALL_USERS", "audienceType", "сначала очистите сегменты"))
	}
	if c.Weight < 0 {
		errs = append(errs, NewFieldError("WEIGHT_INVALID", "", ""))
	}
	if c.InitialCtr < 0 || c.InitialCtr > 100 {
		errs = append(errs, NewFieldError("INITIAL_CTR_INVALID", "", ""))
	}
	for _, p := range c.Places {
		if _, ok := d.Places[p]; !ok {
			notFound = append(notFound, NewFieldError("ENTITY_NOT_FOUND", "places", fmt.Sprintf("место показа %d", p)))
		}
	}
	return errs, notFound
}

// ---------------- сегменты ----------------

func ValidateSegments(audience string, s Segments, d Dicts) []FieldError {
	var errs []FieldError
	if audience == AudienceAll && (len(s.Included) > 0 || len(s.Excluded) > 0) {
		return []FieldError{NewFieldError("SEGMENTS_FORBIDDEN_FOR_ALL_USERS", "", "")}
	}
	check := func(list []string, field string) {
		for _, code := range list {
			seg, ok := d.Segments[code]
			switch {
			case !ok:
				errs = append(errs, NewFieldError("SEGMENT_NOT_FOUND", field, code))
			case seg.State != "ACTIVE":
				errs = append(errs, NewFieldError("SEGMENT_NOT_ACTIVE", field, fmt.Sprintf("%s — охват %d", code, seg.Count)))
			}
		}
	}
	check(s.Included, "segments.included")
	check(s.Excluded, "segments.excluded")
	for _, code := range s.Included {
		if slices.Contains(s.Excluded, code) {
			errs = append(errs, NewFieldError("SEGMENT_DUPLICATE", "segments", code))
		}
	}
	return errs
}

// ---------------- баннер (§2.6) ----------------

func ValidateBanner(name string, bannerTypeID int64, content map[string]any, d Dicts) (errs []FieldError, notFound []FieldError) {
	if strings.TrimSpace(name) == "" {
		errs = append(errs, NewFieldError("BANNER_NAME_REQUIRED", "", ""))
	}
	bt, ok := d.BannerTypes[bannerTypeID]
	if bannerTypeID == 0 {
		errs = append(errs, NewFieldError("BANNER_TYPE_REQUIRED", "", ""))
	} else if !ok {
		notFound = append(notFound, NewFieldError("ENTITY_NOT_FOUND", "bannerTypeId", fmt.Sprintf("тип баннера %d", bannerTypeID)))
	}
	if content == nil {
		return append(errs, NewFieldError("BANNER_CONTENT_INVALID", "content", "content должен быть объектом")), notFound
	}
	for k := range content {
		if !slices.Contains(bannerKeys, k) {
			errs = append(errs, NewFieldError("BANNER_CONTENT_INVALID", "content."+k, "неизвестное поле "+k))
		}
	}
	if v, ok := content["title"]; ok {
		s, isStr := v.(string)
		if !isStr {
			errs = append(errs, NewFieldError("BANNER_CONTENT_INVALID", "content.title", "title должен быть строкой"))
		} else if bt.TitleMaxLength > 0 && utf8.RuneCountInString(s) > bt.TitleMaxLength {
			errs = append(errs, NewFieldError("BANNER_TITLE_TOO_LONG", "", fmt.Sprintf("%d символов, для формата %s — не больше %d", utf8.RuneCountInString(s), bt.Code, bt.TitleMaxLength)))
		}
	}
	if v, ok := content["text"]; ok {
		s, isStr := v.(string)
		if !isStr {
			errs = append(errs, NewFieldError("BANNER_CONTENT_INVALID", "content.text", "text должен быть строкой"))
		} else if bt.TextMaxLength > 0 && utf8.RuneCountInString(s) > bt.TextMaxLength {
			errs = append(errs, NewFieldError("BANNER_TEXT_TOO_LONG", "", fmt.Sprintf("%d символов, для формата %s — не больше %d", utf8.RuneCountInString(s), bt.Code, bt.TextMaxLength)))
		}
	}
	for _, k := range []string{"titleStyle", "textStyle"} {
		if v, ok := content[k]; ok {
			errs = append(errs, validateTextStyle(v, "content."+k)...)
		}
	}
	if v, ok := content["background"]; ok {
		m, isMap := v.(map[string]any)
		if !isMap {
			errs = append(errs, NewFieldError("BANNER_CONTENT_INVALID", "content.background", "background должен быть объектом"))
		} else if c, has := m["color"]; has && !isColor(c) {
			errs = append(errs, NewFieldError("COLOR_INVALID", "content.background.color", fmt.Sprint(c)))
		}
	}
	if v, ok := content["image"]; ok {
		m, isMap := v.(map[string]any)
		if !isMap {
			errs = append(errs, NewFieldError("BANNER_CONTENT_INVALID", "content.image", "image должен быть объектом {url}"))
		} else if !isHTTPS(m["url"]) {
			errs = append(errs, NewFieldError("IMAGE_URL_INVALID", "content.image.url", fmt.Sprint(m["url"])))
		}
	}
	if v, ok := content["buttonName"]; ok {
		if _, isStr := v.(string); !isStr {
			errs = append(errs, NewFieldError("BANNER_CONTENT_INVALID", "content.buttonName", "buttonName должен быть строкой"))
		}
	}
	if v, ok := content["voiceOver"]; ok {
		s, isStr := v.(string)
		if !isStr || utf8.RuneCountInString(s) > 200 {
			errs = append(errs, NewFieldError("VOICE_OVER_TOO_LONG", "", ""))
		}
	}
	errs = append(errs, validateAction(content, "content", true)...)
	return errs, notFound
}

// validateAction проверяет пару actionType ↔ link (общая для баннера и кнопки контента).
func validateAction(m map[string]any, path string, required bool) []FieldError {
	var errs []FieldError
	at, has := m["actionType"]
	if !has {
		if required {
			errs = append(errs, NewFieldError("BANNER_ACTION_TYPE_REQUIRED", path+".actionType", ""))
		}
		return errs
	}
	s, _ := at.(string)
	if !slices.Contains(ActionTypes, s) {
		return append(errs, NewFieldError("ACTION_TYPE_INVALID", path+".actionType", fmt.Sprint(at)))
	}
	link, hasLink := m["link"]
	nonEmpty := false
	if hasLink {
		lm, isMap := link.(map[string]any)
		if !isMap {
			errs = append(errs, NewFieldError("LINK_INVALID", path+".link", ""))
		} else {
			for k, v := range lm {
				if !slices.Contains(linkKeys, k) {
					errs = append(errs, NewFieldError("LINK_INVALID", path+".link."+k, "неизвестный ключ "+k))
				}
				if str, ok := v.(string); ok && str != "" {
					nonEmpty = true
				}
			}
		}
	}
	if slices.Contains(linkRequired, s) && !nonEmpty {
		errs = append(errs, NewFieldError("LINK_REQUIRED", path+".link", "actionType="+s))
	}
	if slices.Contains(linkBanned, s) && hasLink {
		errs = append(errs, NewFieldError("LINK_FORBIDDEN", path+".link", "actionType="+s))
	}
	return errs
}

func validateTextStyle(v any, path string) []FieldError {
	m, ok := v.(map[string]any)
	if !ok {
		return []FieldError{NewFieldError("STYLE_INVALID", path, "стиль должен быть объектом")}
	}
	var errs []FieldError
	if fs, has := m["fontSize"]; has {
		n, isNum := fs.(float64)
		if !isNum || n < 10 || n > 40 {
			errs = append(errs, NewFieldError("STYLE_INVALID", path+".fontSize", fmt.Sprintf("размер шрифта %v", fs)))
		}
	}
	if fw, has := m["fontWeight"]; has {
		if s, _ := fw.(string); !slices.Contains(FontWeights, s) {
			errs = append(errs, NewFieldError("STYLE_INVALID", path+".fontWeight", fmt.Sprint(fw)))
		}
	}
	if tc, has := m["textColor"]; has && !isColor(tc) {
		errs = append(errs, NewFieldError("COLOR_INVALID", path+".textColor", fmt.Sprint(tc)))
	}
	return errs
}

// ---------------- PROMO-контент (§2.7) ----------------

func ValidateContent(name, contentType string, content map[string]any) []FieldError {
	var errs []FieldError
	if strings.TrimSpace(name) == "" {
		errs = append(errs, NewFieldError("CONTENT_NAME_REQUIRED", "", ""))
	}
	if contentType != "PROMO" {
		errs = append(errs, NewFieldError("CONTENT_TYPE_INVALID", "", contentType))
	}
	if content == nil || content["role"] != "promo" {
		return append(errs, NewFieldError("CONTENT_SCHEMA_INVALID", "content.role", "корень должен быть {role: \"promo\", component: linearContainer}"))
	}
	lc, ok := content["component"].(map[string]any)
	if !ok || lc["role"] != "linearContainer" {
		return append(errs, NewFieldError("CONTENT_SCHEMA_INVALID", "content.component", "component должен быть linearContainer"))
	}
	if lc["axis"] != "v" {
		errs = append(errs, NewFieldError("CONTENT_AXIS_INVALID", "", fmt.Sprint(lc["axis"])))
	}
	if st, has := lc["style"]; has {
		if sm, isMap := st.(map[string]any); !isMap {
			errs = append(errs, NewFieldError("CONTENT_SCHEMA_INVALID", "content.component.style", "style должен быть объектом"))
		} else if bg, has := sm["backgroundColor"]; has && !isColor(bg) {
			errs = append(errs, NewFieldError("COLOR_INVALID", "content.component.style.backgroundColor", fmt.Sprint(bg)))
		}
	}
	comps, isArr := lc["components"].([]any)
	if !isArr || len(comps) < 1 || len(comps) > 6 {
		errs = append(errs, NewFieldError("CONTENT_COMPONENTS_COUNT", "", fmt.Sprintf("сейчас блоков: %d", len(comps))))
	}
	for i, raw := range comps {
		path := fmt.Sprintf("content.component.components[%d]", i)
		c, isMap := raw.(map[string]any)
		if !isMap {
			errs = append(errs, NewFieldError("CONTENT_SCHEMA_INVALID", path, "компонент должен быть объектом"))
			continue
		}
		switch c["role"] {
		case "text":
			if f, _ := c["format"].(string); f != "none" && f != "html" {
				errs = append(errs, NewFieldError("CONTENT_TEXT_FORMAT_REQUIRED", path+".format", ""))
			}
			if _, isStr := c["text"].(string); !isStr {
				errs = append(errs, NewFieldError("CONTENT_SCHEMA_INVALID", path+".text", "у text нужен строковый text"))
			}
		case "image":
			if !isHTTPS(c["url"]) {
				errs = append(errs, NewFieldError("CONTENT_IMAGE_URL_REQUIRED", path+".url", ""))
			}
			if ar, has := c["aspectRatio"]; has {
				if _, isNum := ar.(float64); !isNum {
					errs = append(errs, NewFieldError("CONTENT_SCHEMA_INVALID", path+".aspectRatio", "aspectRatio должен быть числом"))
				}
			}
		case "button":
			if _, isStr := c["text"].(string); !isStr {
				errs = append(errs, NewFieldError("CONTENT_SCHEMA_INVALID", path+".text", "у кнопки нужен text"))
			}
			errs = append(errs, validateAction(c, path, true)...)
		default:
			errs = append(errs, NewFieldError("CONTENT_ROLE_INVALID", path+".role", fmt.Sprint(c["role"])))
		}
	}
	return errs
}

// ---------------- креатив (§2.8) ----------------

func ValidateCreative(cr Creative, bannerType BannerType, existing []Creative) []FieldError {
	var errs []FieldError
	if strings.TrimSpace(cr.Name) == "" {
		errs = append(errs, NewFieldError("CREATIVE_NAME_REQUIRED", "", ""))
	}
	if !slices.Contains(bannerType.Channels, cr.ChannelCode) {
		errs = append(errs, NewFieldError("CREATIVE_CHANNEL_NOT_ALLOWED", "", fmt.Sprintf("%s не показывается на платформе %s, доступно: %s", bannerType.Code, cr.ChannelCode, strings.Join(bannerType.Channels, ", "))))
	}
	for _, e := range existing {
		if e.ID != cr.ID && e.BannerID == cr.BannerID && e.ChannelCode == cr.ChannelCode {
			errs = append(errs, NewFieldError("CREATIVE_DUPLICATE", "", fmt.Sprintf("баннер уже размещён на платформе %s", e.ChannelCode)))
		}
	}
	return errs
}

// ---------------- кампания целиком ----------------

// ValidateCampaign — полный прогон: ошибки (блокируют to-moderation) и warnings.
func ValidateCampaign(det CampaignDetails, d Dicts, others []*Campaign) (errs []FieldError, warnings []FieldError) {
	c := det.Campaign
	c.Segments = det.Segments
	h, nf := ValidateHeader(&c, d, others)
	errs = append(errs, h...)
	errs = append(errs, nf...)
	if c.AudienceType == AudienceSegmented && len(det.Segments.Included) == 0 {
		errs = append(errs, NewFieldError("SEGMENTS_REQUIRED", "", ""))
	}
	errs = append(errs, ValidateSegments(c.AudienceType, det.Segments, d)...)
	if len(c.Places) == 0 {
		errs = append(errs, NewFieldError("PLACES_REQUIRED", "", ""))
	}
	for _, b := range det.Banners {
		be, bnf := ValidateBanner(b.Name, b.BannerTypeID, b.Content, d)
		for _, e := range append(be, bnf...) {
			e.Field = fmt.Sprintf("banners[%d].%s", b.ID, e.Field)
			errs = append(errs, e)
		}
	}
	for _, ct := range det.Contents {
		for _, e := range ValidateContent(ct.Name, ct.ContentType, ct.Content) {
			e.Field = fmt.Sprintf("contents[%d].%s", ct.ID, e.Field)
			errs = append(errs, e)
		}
	}
	banners := map[int64]Banner{}
	for _, b := range det.Banners {
		banners[b.ID] = b
	}
	for _, cr := range det.Creatives {
		b, ok := banners[cr.BannerID]
		if !ok {
			errs = append(errs, NewFieldError("ENTITY_NOT_FOUND", fmt.Sprintf("creatives[%d].bannerId", cr.ID), fmt.Sprintf("баннер %d", cr.BannerID)))
			continue
		}
		for _, e := range ValidateCreative(cr, d.BannerTypes[b.BannerTypeID], det.Creatives) {
			e.Field = fmt.Sprintf("creatives[%d].%s", cr.ID, e.Field)
			errs = append(errs, e)
		}
	}
	return dedupe(errs), Warnings(det, d)
}

func dedupe(errs []FieldError) []FieldError {
	seen := map[string]bool{}
	out := errs[:0]
	for _, e := range errs {
		k := e.Code + "|" + e.Field + "|" + e.Message
		if !seen[k] {
			seen[k] = true
			out = append(out, e)
		}
	}
	return out
}

// Warnings — три предупреждения из task.md §4 и правило покрытия mock-data §7.2.
func Warnings(det CampaignDetails, d Dicts) []FieldError {
	var out []FieldError
	covered := map[string]bool{}
	banners := map[int64]Banner{}
	for _, b := range det.Banners {
		banners[b.ID] = b
	}
	for _, cr := range det.Creatives {
		if b, ok := banners[cr.BannerID]; ok {
			covered[d.BannerTypes[b.BannerTypeID].Code] = true
		}
	}
	var uncovered, inactive []string
	for _, pid := range det.Places {
		p, ok := d.Places[pid]
		if !ok {
			continue
		}
		if p.DefaultBanner != nil && !covered[*p.DefaultBanner] {
			uncovered = append(uncovered, p.Code)
		}
		if p.State != "ACTIVE" {
			inactive = append(inactive, p.Code)
		}
	}
	if len(uncovered) > 0 {
		out = append(out, FieldError{Code: "PLACE_NO_CREATIVE", Message: WarningMessage("PLACE_NO_CREATIVE"), Field: strings.Join(uncovered, ",")})
	}
	if len(inactive) > 0 {
		out = append(out, FieldError{Code: "PLACE_INACTIVE", Message: WarningMessage("PLACE_INACTIVE"), Field: strings.Join(inactive, ",")})
	}
	if len(det.Tags) == 0 {
		out = append(out, FieldError{Code: "TAGS_MISSING", Message: WarningMessage("TAGS_MISSING"), Field: "tags"})
	}
	return out
}

func isColor(v any) bool {
	s, ok := v.(string)
	return ok && reColor.MatchString(s)
}

// MediaBase — публичный адрес API ({PUBLIC_URL}); ссылки на собственные изображения
// ({MediaBase}/media/{id}) принимаются и без https — например, при локальном запуске.
var MediaBase string

func isHTTPS(v any) bool {
	s, ok := v.(string)
	if ok && MediaBase != "" && strings.HasPrefix(s, MediaBase+"/media/") && len(s) > len(MediaBase+"/media/") {
		return true
	}
	return ok && strings.HasPrefix(s, "https://") && len(s) > len("https://")
}
