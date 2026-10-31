import type { AgentState, Campaign } from "../types";

const AGENT_URL = import.meta.env.VITE_AGENT_URL ?? "http://localhost:8000";
const API_URL = import.meta.env.VITE_API_URL ?? "http://localhost:8080";

async function req<T>(url: string, init?: RequestInit): Promise<T> {
  const r = await fetch(url, {
    ...init,
    headers: { "Content-Type": "application/json", ...(init?.headers ?? {}) },
  });
  const body = await r.json().catch(() => ({}));
  if (!r.ok) throw new Error(body.error ?? body.detail ?? `HTTP ${r.status}`);
  return body as T;
}

export const agent = {
  chat: (session_id: string | null, message: string) =>
    req<AgentState>(`${AGENT_URL}/chat`, { method: "POST", body: JSON.stringify({ session_id, message }) }),
  confirm: (session_id: string, action_id: string, approved: boolean) =>
    req<AgentState>(`${AGENT_URL}/confirm`, { method: "POST", body: JSON.stringify({ session_id, action_id, approved }) }),
};

export interface Ref { id: string; name: string; [k: string]: unknown }

export const api = {
  campaigns: () => req<Campaign[]>(`${API_URL}/api/campaigns`),
  updateCampaign: (c: Campaign) =>
    req<{ campaign: Campaign; problems: { field: string; message: string }[] }>(
      `${API_URL}/api/campaigns/${c.id}`, { method: "PUT", body: JSON.stringify(c) }),
  setStatus: (id: string, status: string) =>
    req<Campaign>(`${API_URL}/api/campaigns/${id}/status`, { method: "POST", body: JSON.stringify({ status }) }),
  segments: () => req<Ref[]>(`${API_URL}/api/segments`),
  placements: () => req<Ref[]>(`${API_URL}/api/placements`),
  advertisers: () => req<Ref[]>(`${API_URL}/api/advertisers`),
};
