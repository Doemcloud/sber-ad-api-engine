export type FieldSource = "request" | "ai" | "asked" | "system";

export interface Creative {
  id?: string;
  placement_id: string;
  type: "smart_banner" | "feed_banner" | "promo_banner" | "stories" | "push";
  variant?: string;
  title: string;
  text?: string;
  button?: string;
  image_url?: string;
  issues?: string[];
}

export interface Campaign {
  id?: string;
  status?: string;
  name?: string;
  advertiser_id?: string;
  goal?: string;
  object?: string;
  offer?: string;
  target_client?: string;
  segment_ids?: string[];
  placement_ids?: string[];
  budget_rub?: number;
  start_date?: string;
  end_date?: string;
  show_hours?: string;
  frequency_cap_per_day?: number;
  landing_url?: string;
  creatives?: Creative[];
  field_sources?: Record<string, FieldSource>;
  stats?: { impressions?: number; clicks?: number; conversions?: number };
  [key: string]: unknown;
}

export interface PendingAction {
  id: string;
  kind: "create_segment" | "create_advertiser" | "save_campaign";
  title: string;
  payload: Record<string, unknown>;
}

export interface AgentState {
  session_id: string;
  reply: string;
  draft: Campaign;
  missing: string[];
  pending_actions: PendingAction[];
}

export interface ChatMessage {
  role: "user" | "assistant" | "system";
  text: string;
}
