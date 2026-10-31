import unittest

from app import validators as V

STORY = {"id": 1, "code": "STORY", "titleMaxLength": 100, "textMaxLength": 500, "channels": ["iOS", "ANDROID"]}


def codes(errs):
    return {e["code"] for e in errs}


class BannerTest(unittest.TestCase):
    def test_minimal_valid(self):
        self.assertEqual(V.validate_banner("b", STORY, {"actionType": "default"}), [])

    def test_title_limit(self):
        errs = V.validate_banner("b", STORY, {"title": "я" * 132, "actionType": "default"})
        self.assertIn("BANNER_TITLE_TOO_LONG", codes(errs))
        self.assertIn("132 символов, лимит для STORY — 100", errs[0]["message"])

    def test_link_rules(self):
        self.assertIn("LINK_REQUIRED", codes(V.validate_banner("b", STORY, {"actionType": "externalLink"})))
        self.assertIn("LINK_FORBIDDEN", codes(V.validate_banner("b", STORY, {"actionType": "doneCampaign", "link": {"web": "https://x"}})))
        self.assertEqual(V.validate_banner("b", STORY, {"actionType": "openSmartLink", "link": {"iOS": "mobilebank://x"}}), [])

    def test_styles_and_colors(self):
        errs = V.validate_banner("b", STORY, {"actionType": "default", "titleStyle": {"fontSize": 8, "fontWeight": "heavy", "textColor": "#FFF"},
                                              "background": {"color": "green"}, "image": {"url": "http://x"}})
        self.assertTrue({"STYLE_INVALID", "COLOR_INVALID", "IMAGE_URL_INVALID"} <= codes(errs))

    def test_unknown_field(self):
        self.assertIn("BANNER_CONTENT_INVALID", codes(V.validate_banner("b", STORY, {"actionType": "default", "subtitle": "x"})))


class ContentTest(unittest.TestCase):
    def ok(self, comps):
        return {"role": "promo", "component": {"role": "linearContainer", "axis": "v", "components": comps}}

    def test_valid(self):
        c = self.ok([{"role": "text", "format": "html", "text": "<b>16%</b>"}, {"role": "image", "url": "https://x/y.png", "aspectRatio": 2.0},
                     {"role": "button", "text": "Открыть", "actionType": "externalLink", "link": {"web": "https://x"}}])
        self.assertEqual(V.validate_content("p", "PROMO", c), [])

    def test_rules(self):
        c = self.ok([{"role": "text", "text": "без формата"}, {"role": "image"}, {"role": "video"}])
        c["component"]["axis"] = "h"
        self.assertTrue({"CONTENT_TEXT_FORMAT_REQUIRED", "CONTENT_IMAGE_URL_REQUIRED", "CONTENT_ROLE_INVALID", "CONTENT_AXIS_INVALID"} <= codes(V.validate_content("p", "PROMO", c)))
        self.assertIn("CONTENT_COMPONENTS_COUNT", codes(V.validate_content("p", "PROMO", self.ok([]))))


class HeaderTest(unittest.TestCase):
    D = {"topics": [{"value": "SALES"}], "tags": [{"id": 5, "name": "Вклад"}], "places": [{"id": 1}]}

    def test_valid(self):
        c = {"name": "x", "startDate": "2026-11-05", "startTime": "00:00", "endDate": "2026-12-31", "endTime": "23:59",
             "topic": "SALES", "audienceType": "SEGMENTED", "tags": [5], "places": [1]}
        self.assertEqual(V.validate_header(c, self.D), [])

    def test_errors(self):
        c = {"name": "", "startDate": "2026-11-05", "startTime": "10:00", "endDate": "2026-11-05", "endTime": "09:00",
             "topic": "PROMO", "audienceType": "ALL", "tags": [99], "places": [7]}
        self.assertTrue({"NAME_REQUIRED", "DATE_RANGE_INVALID", "TOPIC_INVALID", "AUDIENCE_TYPE_INVALID", "ENTITY_NOT_FOUND"} <= codes(V.validate_header(c, self.D)))


class SegmentsTest(unittest.TestCase):
    D = {"segments": [{"code": "CITY_MSK", "state": "ACTIVE", "count": 1}, {"code": "SEG_DRAFT_WINTER", "state": "NEW", "count": 0}]}

    def test_rules(self):
        self.assertIn("SEGMENTS_FORBIDDEN_FOR_ALL_USERS", codes(V.validate_segments("ALL_USERS", ["CITY_MSK"], [], self.D)))
        self.assertIn("SEGMENT_NOT_ACTIVE", codes(V.validate_segments("SEGMENTED", ["SEG_DRAFT_WINTER"], [], self.D)))
        self.assertIn("SEGMENT_NOT_FOUND", codes(V.validate_segments("SEGMENTED", ["AGE_100"], [], self.D)))


if __name__ == "__main__":
    unittest.main()
