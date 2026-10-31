"""Клиент Go API. Агент читает справочники свободно, а пишет только через
confirm_action — после явного подтверждения менеджера."""
import os

import httpx

API_URL = os.getenv("API_URL", "http://localhost:8080")


class Backend:
    def __init__(self, base: str = API_URL):
        self.c = httpx.Client(base_url=base, timeout=15)

    def _get(self, path: str, **params):
        r = self.c.get(path, params={k: v for k, v in params.items() if v})
        r.raise_for_status()
        return r.json()

    def segments(self):
        return self._get("/api/segments")

    def placements(self):
        return self._get("/api/placements")

    def advertisers(self):
        return self._get("/api/advertisers")

    def campaigns(self, **filters):
        return self._get("/api/campaigns", **filters)

    def campaign(self, cid: str):
        return self._get(f"/api/campaigns/{cid}")

    def validate(self, draft: dict):
        r = self.c.post("/api/campaigns/validate", json=draft)
        r.raise_for_status()
        return r.json()

    # --- запись: вызывается только из confirm_action ---
    def create_segment(self, seg: dict):
        r = self.c.post("/api/segments", json=seg)
        r.raise_for_status()
        return r.json()

    def create_advertiser(self, adv: dict):
        r = self.c.post("/api/advertisers", json=adv)
        r.raise_for_status()
        return r.json()

    def save_campaign(self, draft: dict):
        if draft.get("id"):
            r = self.c.put(f"/api/campaigns/{draft['id']}", json=draft)
        else:
            r = self.c.post("/api/campaigns", json=draft)
        r.raise_for_status()
        return r.json()
