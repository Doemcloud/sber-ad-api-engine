import type {
  AgentState, AuditEntry, HistoryItem, BannerType, CampaignDetails, CampaignListItem,
  Dicts, Place, Role, Segment, Tag, Topic, Validation,
} from "./types";

const env = (import.meta as unknown as { env: Record<string, string | undefined> }).env ?? {};
export const AGENT_URL = env.VITE_AGENT_URL ?? "http://localhost:8000";
export const API_URL = env.VITE_API_URL ?? "http://localhost:8080";

async function req<T>(url: string, init?: RequestInit): Promise<T> {
  const r = await fetch(url, { ...init, headers: { "Content-Type": "application/json", ...(init?.headers ?? {}) } });
  const text = await r.text();
  const body = text ? JSON.parse(text) : null;
  if (!r.ok) {
    const msg = body?.errors?.map((e: { message: string }) => e.message).join("; ") ?? body?.detail ?? `HTTP ${r.status}`;
    throw new Error(msg);
  }
  return body as T;
}

const post = (body: unknown): RequestInit => ({ method: "POST", body: JSON.stringify(body) });

export const agent = {
  chat: (session_id: string | null, message: string, user: string, role: Role) =>
    req<AgentState>(`${AGENT_URL}/chat`, post({ session_id, message, user, role })),
  confirm: (session_id: string, action_id: string, approved: boolean) =>
    req<AgentState>(`${AGENT_URL}/confirm`, post({ session_id, action_id, approved })),
  setRole: (session_id: string, user: string, role: Role) =>
    req<AgentState>(`${AGENT_URL}/sessions/${session_id}/role`, post({ user, role })),
  openCampaign: (session_id: string, id: number) =>
    req<AgentState>(`${AGENT_URL}/sessions/${session_id}/campaign/${id}`, { method: "POST" }),
  // История диалогов: список, восстановление, удаление.
  sessions: (user?: string) => req<HistoryItem[]>(`${AGENT_URL}/sessions${user ? `?user=${encodeURIComponent(user)}` : ""}`),
  session: (session_id: string) => req<AgentState>(`${AGENT_URL}/sessions/${session_id}`),
  deleteSession: (session_id: string) => req<{ deleted: string }>(`${AGENT_URL}/sessions/${session_id}`, { method: "DELETE" }),
};

export const api = {
  campaigns: () => req<CampaignListItem[]>(`${API_URL}/campaigns`),
  campaign: (id: number) => req<CampaignDetails>(`${API_URL}/campaigns/${id}`),
  warnings: (id: number) => req<Validation>(`${API_URL}/campaigns/${id}/warnings`),
  audit: (id: number) => req<AuditEntry[]>(`${API_URL}/campaigns/${id}/audit`),
  dicts: async (): Promise<Dicts> => {
    const [topics, tags, bannerTypes, segments, places] = await Promise.all([
      req<Topic[]>(`${API_URL}/topics`), req<Tag[]>(`${API_URL}/tags`), req<BannerType[]>(`${API_URL}/banner-types`),
      req<Segment[]>(`${API_URL}/segments`), req<Place[]>(`${API_URL}/places`),
    ]);
    return { topics, tags, bannerTypes, segments, places };
  },
};

// Прямые действия человека на экране проверки (каждое — явный клик).
// Роль и пользователь идут в X-Role / X-User: бэкенд проверяет права и пишет аудит.
export interface Who { user: string; role: Role }

const as = (w: Who, init: RequestInit = {}): RequestInit => ({ ...init, headers: { "X-User": w.user, "X-Role": w.role } });

export const actions = {
  transition: (id: number, action: "to-moderation" | "approve" | "activate" | "stop", w: Who) =>
    req<CampaignDetails>(`${API_URL}/campaigns/${id}/${action}`, as(w, post({}))),
  decline: (id: number, comment: string, w: Who) =>
    req<CampaignDetails>(`${API_URL}/campaigns/${id}/decline`, as(w, post({ comment }))),
  // PUT — полная замена шапки: GET → слияние → PUT, словарные поля как {value, label}.
  updateHeader: async (c: CampaignDetails, patch: Partial<CampaignDetails>, d: Dicts, w: Who) => {
    const m = { ...c, ...patch };
    const body = {
      name: m.name, marketingName: m.marketingName, startDate: m.startDate, startTime: m.startTime,
      endDate: m.endDate, endTime: m.endTime, keywords: m.keywords, audienceType: m.audienceType,
      weight: m.weight, initialCtr: m.initialCtr,
      topic: { value: m.topic, label: d.topics.find((t) => t.value === m.topic)?.label ?? m.topic },
      tags: m.tags.map((t) => ({ value: t, label: d.tags.find((x) => x.id === t)?.name ?? String(t) })),
      places: m.places.map((p) => ({ value: p, label: d.places.find((x) => x.id === p)?.code ?? String(p) })),
    };
    return req<CampaignDetails>(`${API_URL}/campaigns/${c.id}`, as(w, { method: "PUT", body: JSON.stringify(body) }));
  },
};
